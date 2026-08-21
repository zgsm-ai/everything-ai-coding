#!/usr/bin/env python3
"""Build the repository-granular registry manifest for downstream discovery.

The catalog is item-granular, but the downstream registry discovers capabilities
from repository roots. Entries are therefore grouped by their original GitHub
repository. A repository is emitted only when the catalog proves a root capability
identity; nested items are folded into that repository entry and aggregator-only
repositories are omitted.

Usage:
    python scripts/build_registry_manifest.py
    python scripts/build_registry_manifest.py --output dist/registry-manifest.json
    python scripts/build_registry_manifest.py --verify
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

SCHEMA_VERSION = 1
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = REPO_ROOT / "dist" / "registry-manifest.json"
CATALOG_INDEX = REPO_ROOT / "catalog" / "index.json"

SUPPORTED_TYPES = frozenset(
    {"plugin", "skill", "mcp", "rule", "prompt", "command", "subagent", "template"}
)
SECURITY_VERDICT_MAP = {"safe": "pass", "caution": "warn", "reject": "reject"}
CONTRACT_VERDICTS = frozenset((*SECURITY_VERDICT_MAP.values(), "unscanned"))
GIT_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?$")
GITHUB_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

# Must be compared with costrict-web rootManifestPrecedence before merge. The
# ordering is the contract: the first root manifest found determines repo type.
ROOT_MANIFEST_PRECEDENCE = (
    (".claude-plugin/plugin.json", "plugin"),
    ("plugin.json", "plugin"),
    ("SKILL.md", "skill"),
    (".mcp.json", "mcp"),
    ("RULE.md", "rule"),
    ("PROMPT.md", "prompt"),
    ("COMMAND.md", "command"),
    ("AGENT.md", "subagent"),
    ("TEMPLATE.md", "template"),
)
ROOT_MANIFEST_RANK = {path: rank for rank, (path, _) in enumerate(ROOT_MANIFEST_PRECEDENCE)}
ROOT_MANIFEST_TYPES = {path: entry_type for path, entry_type in ROOT_MANIFEST_PRECEDENCE}
DEFAULT_ROOT_MANIFEST = {
    "plugin": ".claude-plugin/plugin.json",
    "skill": "SKILL.md",
    "mcp": ".mcp.json",
    "rule": "RULE.md",
    "prompt": "PROMPT.md",
    "command": "COMMAND.md",
    "subagent": "AGENT.md",
    "template": "TEMPLATE.md",
}
KNOWN_ENTRY_FILES = frozenset(ROOT_MANIFEST_TYPES)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_catalog(index_path: Path = CATALOG_INDEX) -> list[dict]:
    if not index_path.is_file():
        sys.exit(f"missing {index_path}")
    try:
        value = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        sys.exit(f"failed to read {index_path}: {exc}")
    if not isinstance(value, list):
        sys.exit(f"invalid {index_path}: expected a JSON array")
    return value


def _score(value: object, field: str) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric or null")
    if not 0 <= value <= 100:
        raise ValueError(f"{field} must be between 0 and 100")
    return value


def _clean_ref(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip().strip("/")
    return value if value and value.upper() != "HEAD" else None


def _clean_path(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    value = unquote(value).replace("\\", "/").strip()
    while value.startswith("./"):
        value = value[2:]
    value = value.strip("/")
    return value or None


def _subdir(value: object, *, file_path: bool = False) -> str | None:
    value = _clean_path(value)
    if value is None:
        return None
    path = PurePosixPath(value)
    if file_path or path.name in KNOWN_ENTRY_FILES:
        parent = str(path.parent)
        return None if parent == "." else parent
    return str(path)


def _is_forbidden_source(url: str) -> bool:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    path = parsed.path.lower()
    return host == "gitea.costrict.ai" or "costrict-plugin-marketplace" in path


def _github_coordinates(
    url: str, branch_hint: str | None
) -> tuple[str, str | None, str | None, str | None, bool] | None:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    if host not in {
        "github.com",
        "www.github.com",
        "github.com.mcas.ms",
        "raw.githubusercontent.com",
    }:
        return None

    parts = [unquote(part) for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        return None
    owner, repo = parts[0], parts[1].removesuffix(".git")
    if not owner or not repo:
        return None
    root = f"https://github.com/{owner}/{repo}"
    if _is_forbidden_source(root):
        return None

    tail = parts[2:]
    ref = _clean_ref(branch_hint)
    artifact_path = None
    file_path = False

    if host == "raw.githubusercontent.com" and tail:
        raw_ref = tail.pop(0)
        ref = ref or _clean_ref(raw_ref)
        artifact_path = _clean_path("/".join(tail))
        file_path = True
    elif tail and tail[0] in {"tree", "blob"}:
        marker = tail.pop(0)
        if branch_hint:
            hint_parts = [part for part in branch_hint.strip("/").split("/") if part]
            if hint_parts and tail[: len(hint_parts)] == hint_parts:
                tail = tail[len(hint_parts) :]
            elif tail:
                tail.pop(0)
        elif tail:
            ref = _clean_ref(tail.pop(0))
        artifact_path = _clean_path("/".join(tail))
        file_path = marker == "blob"

    subdir = _subdir(artifact_path, file_path=file_path)
    fragment = parsed.fragment.strip() or None
    return root, subdir, ref, artifact_path, file_path or fragment is not None


def _repo_candidate(entry: dict) -> tuple[str, str | None] | None:
    install = entry.get("install")
    bundle = entry.get("bundle")
    candidates: list[object] = []
    if isinstance(install, dict):
        candidates.append(install.get("repo"))
    if isinstance(bundle, dict):
        candidates.append(bundle.get("source_repo"))
    if isinstance(install, dict):
        candidates.append(install.get("marketplace_repo"))

    branch = None
    if isinstance(install, dict):
        branch = install.get("branch")
    if branch is None and isinstance(bundle, dict):
        branch = bundle.get("source_ref")

    for candidate in candidates:
        if not isinstance(candidate, str) or not candidate.strip():
            continue
        candidate = candidate.strip().removesuffix(".git")
        repo_url = (
            f"https://github.com/{candidate}"
            if GITHUB_REPO_RE.fullmatch(candidate)
            else candidate
        )
        coordinates = _github_coordinates(repo_url, branch if isinstance(branch, str) else None)
        if coordinates is not None:
            return coordinates[0], coordinates[2]
    return None


def _explicit_entry_path(entry: dict) -> tuple[str | None, bool]:
    bundle = entry.get("bundle")
    if entry.get("type") == "plugin" and isinstance(bundle, dict):
        plugin_root = bundle.get("plugin_root")
        if isinstance(plugin_root, str):
            return _clean_path(plugin_root), False

    source_path = entry.get("source_path")
    if isinstance(source_path, str) and source_path.strip():
        return _clean_path(source_path), True

    install = entry.get("install")
    if not isinstance(install, dict):
        return None, False
    path = install.get("path")
    if isinstance(path, str):
        if not path.strip():
            return None, False
        clean = _clean_path(path)
        is_file = bool(clean and (PurePosixPath(clean).suffix or clean in KNOWN_ENTRY_FILES))
        return clean, is_file

    files = install.get("files")
    if isinstance(files, list) and len(files) == 1 and isinstance(files[0], str):
        file_value = files[0]
        if urlsplit(file_value).scheme:
            return None, False
        clean = _clean_path(file_value)
        is_file = bool(
            clean
            and not file_value.rstrip().endswith("/")
            and (PurePosixPath(clean).suffix or clean in KNOWN_ENTRY_FILES)
        )
        return clean, is_file
    return None, False


def _source_coordinates(entry: dict) -> dict:
    install = entry.get("install")
    branch_hint = install.get("branch") if isinstance(install, dict) else None
    source_url = entry.get("source_url")

    coordinates = None
    if isinstance(source_url, str) and source_url.strip() and not _is_forbidden_source(source_url):
        coordinates = _github_coordinates(source_url.strip(), branch_hint)

    if coordinates is None:
        repo_candidate = _repo_candidate(entry)
        if repo_candidate is None:
            root, url_subdir, ref, artifact_path, file_evidence = None, None, None, None, False
        else:
            root, ref = repo_candidate
            url_subdir, artifact_path, file_evidence = None, None, False
    else:
        root, url_subdir, ref, artifact_path, file_evidence = coordinates

    explicit_path, explicit_is_file = _explicit_entry_path(entry)
    if explicit_path is not None:
        subdir = _subdir(explicit_path, file_path=explicit_is_file)
        artifact_path = explicit_path
        file_evidence = explicit_is_file
    else:
        subdir = url_subdir

    if isinstance(source_url, str) and urlsplit(source_url).fragment:
        subdir = subdir or f"#{urlsplit(source_url).fragment}"
        file_evidence = True

    evaluation = entry.get("evaluation")
    evaluated_source_sha = evaluation.get("source_sha") if isinstance(evaluation, dict) else None
    sha = None
    for candidate in (entry.get("source_sha"), evaluated_source_sha):
        if isinstance(candidate, str) and GIT_SHA_RE.fullmatch(candidate.strip()):
            sha = candidate.strip().lower()
            break

    evaluated_at = evaluation.get("evaluated_at") if isinstance(evaluation, dict) else None
    if not isinstance(evaluated_at, str) or not evaluated_at.strip():
        evaluated_at = None

    return {
        "url": root,
        "sha": sha,
        "subdir": subdir,
        "ref": ref,
        "evaluated_at": evaluated_at,
        "_artifact_path": artifact_path,
        "_file_evidence": file_evidence,
    }


def _root_manifest_path(entry: dict, source: dict) -> str | None:
    if source.get("subdir") is not None:
        return None

    entry_type = entry.get("type")
    bundle = entry.get("bundle")
    if entry_type == "plugin" and isinstance(bundle, dict):
        if bundle.get("is_marketplace_repo") is True:
            return None
        plugin_path = _clean_path(bundle.get("plugin_json_path"))
        if plugin_path in {".claude-plugin/plugin.json", "plugin.json"}:
            return plugin_path
        if plugin_path is not None:
            return None
        if bundle.get("plugin_root") == "":
            return ".claude-plugin/plugin.json"

    if entry_type == "plugin":
        install = entry.get("install")
        if not isinstance(install, dict) or install.get("marketplace_verified") is not True:
            return None

    artifact_path = _clean_path(source.get("_artifact_path"))
    if source.get("_file_evidence") and artifact_path is not None:
        if PurePosixPath(artifact_path).parent != PurePosixPath("."):
            return None
        if ROOT_MANIFEST_TYPES.get(artifact_path) == entry_type:
            return artifact_path
        return None

    return DEFAULT_ROOT_MANIFEST.get(entry_type)


def _security(entry: dict) -> dict:
    security = entry.get("security")
    if not isinstance(security, dict) or not security.get("verdict"):
        return {"verdict": "unscanned", "scanned_at": None, "reasons": []}

    upstream_verdict = security.get("verdict")
    verdict = SECURITY_VERDICT_MAP.get(upstream_verdict)
    if verdict is None:
        raise ValueError(f"unsupported security verdict {upstream_verdict!r}")
    red_flags = security.get("red_flags")
    reasons = (
        [reason for reason in red_flags if isinstance(reason, str)]
        if isinstance(red_flags, list)
        else []
    )
    scanned_at = security.get("scanned_at")
    if not isinstance(scanned_at, str) or not scanned_at.strip():
        scanned_at = None
    return {"verdict": verdict, "scanned_at": scanned_at, "reasons": reasons}


def _manifest_entry(entry: dict, position: int, source: dict) -> dict:
    catalog_id = entry.get("id")
    entry_type = entry.get("type")
    if not isinstance(catalog_id, str) or not catalog_id.strip():
        raise ValueError(f"catalog entry #{position} has no stable id")
    if entry_type not in SUPPORTED_TYPES:
        raise ValueError(f"catalog entry {catalog_id!r} has unsupported type {entry_type!r}")

    slug = entry.get("slug")
    if not isinstance(slug, str) or not slug.strip():
        slug = catalog_id
    evaluation = entry.get("evaluation") if isinstance(entry.get("evaluation"), dict) else {}
    health = entry.get("health") if isinstance(entry.get("health"), dict) else {}
    health_value = health.get("effective_score", health.get("score"))

    public_source = {
        key: source.get(key) for key in ("url", "sha", "subdir", "ref", "evaluated_at")
    }
    public_source["subdir"] = None
    return {
        "catalog_id": catalog_id,
        "type": entry_type,
        "slug": slug,
        "source": public_source,
        "eval": {
            "final_score": _score(entry.get("final_score"), f"{catalog_id}.final_score"),
            "llm_score": _score(evaluation.get("content_quality"), f"{catalog_id}.llm_score"),
            "health_score": _score(health_value, f"{catalog_id}.health_score"),
            "security": _security(entry),
        },
    }


def _entry_scores(entry: dict) -> dict[str, object]:
    evaluation = entry.get("evaluation") if isinstance(entry.get("evaluation"), dict) else {}
    health = entry.get("health") if isinstance(entry.get("health"), dict) else {}
    return {
        "final_score": entry.get("final_score"),
        "llm_score": evaluation.get("content_quality"),
        "health_score": health.get("effective_score", health.get("score")),
    }


def _root_candidate_key(record: dict) -> tuple[int, int, str, int]:
    entry = record["entry"]
    priority = entry.get("source_priority")
    if isinstance(priority, bool) or not isinstance(priority, (int, float)):
        priority = 0
    catalog_id = entry.get("id")
    return (
        ROOT_MANIFEST_RANK[record["root_manifest"]],
        -int(priority),
        catalog_id if isinstance(catalog_id, str) else "",
        record["position"],
    )


def _group_catalog(catalog_entries: list[dict]) -> tuple[list[dict], dict]:
    groups: dict[str, list[dict]] = {}
    ungroupable: list[dict] = []
    for position, entry in enumerate(catalog_entries):
        if not isinstance(entry, dict):
            raise ValueError(f"catalog entry #{position} is not an object")
        source = _source_coordinates(entry)
        record = {"entry": entry, "position": position, "source": source}
        if source["url"] is None:
            ungroupable.append(record)
            continue
        record["root_manifest"] = _root_manifest_path(entry, source)
        groups.setdefault(source["url"].casefold(), []).append(record)

    included_groups = []
    discarded_groups = []
    for records in groups.values():
        candidates = [record for record in records if record["root_manifest"] is not None]
        if not candidates:
            discarded_groups.append(records)
            continue
        representative = min(candidates, key=_root_candidate_key)
        included_groups.append((records, representative))

    manifest_entries = [
        _manifest_entry(representative["entry"], representative["position"], representative["source"])
        for _, representative in included_groups
    ]
    duplicate_ids = [
        catalog_id
        for catalog_id, count in Counter(entry["catalog_id"] for entry in manifest_entries).items()
        if count > 1
    ]
    if duplicate_ids:
        raise ValueError(f"repository grouping left duplicate catalog_id values: {duplicate_ids[:5]}")

    child_only_score_fields = Counter()
    child_only_score_groups = 0
    for records, representative in included_groups:
        root_scores = _entry_scores(representative["entry"])
        affected = False
        for field, root_value in root_scores.items():
            if root_value is not None:
                continue
            if any(
                _entry_scores(record["entry"])[field] is not None
                for record in records
                if record is not representative
            ):
                child_only_score_fields[field] += 1
                affected = True
        child_only_score_groups += affected

    reconciliation = {
        "input_entries": len(catalog_entries),
        "repository_groups": len(groups),
        "included_repositories": len(included_groups),
        "collapsed_catalog_items": sum(len(records) - 1 for records, _ in included_groups),
        "discarded_repository_groups": len(discarded_groups),
        "discarded_catalog_items": sum(len(records) for records in discarded_groups),
        "ungroupable_catalog_items": len(ungroupable),
        "old_type_counts": Counter(entry.get("type") for entry in catalog_entries),
        "new_type_counts": Counter(entry["type"] for entry in manifest_entries),
        "root_manifest_counts": Counter(
            representative["root_manifest"] for _, representative in included_groups
        ),
        "score_aggregation_entries": 0,
        "child_only_score_groups_kept_null": child_only_score_groups,
        "child_only_score_fields_kept_null": child_only_score_fields,
        "included_groups": included_groups,
        "discarded_groups": discarded_groups,
        "ungroupable": ungroupable,
    }
    denominator = len(included_groups) + len(discarded_groups)
    reconciliation["repository_coverage"] = (
        len(included_groups) / denominator * 100 if denominator else 0.0
    )
    return manifest_entries, reconciliation


def build(output: Path) -> dict:
    catalog_entries = _load_catalog()
    try:
        entries, reconciliation = _group_catalog(catalog_entries)
    except ValueError as exc:
        sys.exit(f"cannot build registry manifest: {exc}")

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "entries": entries,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"
    output.write_bytes(payload)

    print(
        f"index.json: {len(catalog_entries)} catalog items -> "
        f"{reconciliation['included_repositories']} repository entries"
    )
    print(f"wrote {output}")
    print(f"  size:        {output.stat().st_size:,} bytes")
    print(f"  entries:     {len(entries)}")
    print(f"  sha256:      {hashlib.sha256(payload).hexdigest()[:16]}...")
    return manifest


def _verify_entry(position: int, entry: object) -> None:
    if not isinstance(entry, dict):
        sys.exit(f"verification failed: entry #{position} is not an object")
    source = entry.get("source")
    evaluation = entry.get("eval")
    if not isinstance(source, dict):
        sys.exit(f"verification failed: entry #{position} has no source object")
    if not isinstance(evaluation, dict):
        sys.exit(f"verification failed: entry #{position} has no eval object")
    if set(source) != {"url", "sha", "subdir", "ref", "evaluated_at"}:
        sys.exit(f"verification failed: invalid source fields for {entry.get('catalog_id')}")
    source_url = source.get("url")
    if not isinstance(source_url, str) or _is_forbidden_source(source_url):
        sys.exit(f"verification failed: invalid source URL for {entry.get('catalog_id')}")
    if source.get("sha") is not None and not GIT_SHA_RE.fullmatch(str(source["sha"])):
        sys.exit(f"verification failed: invalid source sha for {entry.get('catalog_id')}")
    if source.get("subdir") is not None:
        sys.exit(f"verification failed: repository entry has subdir for {entry.get('catalog_id')}")
    for field in ("final_score", "llm_score", "health_score"):
        try:
            _score(evaluation.get(field), f"{entry.get('catalog_id')}.{field}")
        except ValueError as exc:
            sys.exit(f"verification failed: {exc}")
    security = evaluation.get("security")
    if not isinstance(security, dict) or security.get("verdict") not in CONTRACT_VERDICTS:
        sys.exit(f"verification failed: invalid security verdict for {entry.get('catalog_id')}")
    if set(security) != {"verdict", "scanned_at", "reasons"}:
        sys.exit(f"verification failed: invalid security fields for {entry.get('catalog_id')}")
    if security["verdict"] == "unscanned" and (
        security["scanned_at"] is not None or security["reasons"] != []
    ):
        sys.exit(f"verification failed: invalid unscanned security for {entry.get('catalog_id')}")


def verify(output: Path) -> dict:
    catalog_entries = _load_catalog()
    try:
        manifest = json.loads(output.read_text(encoding="utf-8"))
    except FileNotFoundError:
        sys.exit(f"missing {output} - build the registry manifest first")
    except (OSError, json.JSONDecodeError) as exc:
        sys.exit(f"failed to read {output}: {exc}")

    if manifest.get("schema_version") != SCHEMA_VERSION:
        sys.exit(f"verification failed: schema_version must be {SCHEMA_VERSION}")
    entries = manifest.get("entries")
    if not isinstance(entries, list):
        sys.exit("verification failed: entries must be an array")
    try:
        expected_entries, reconciliation = _group_catalog(catalog_entries)
    except ValueError as exc:
        sys.exit(f"verification failed: {exc}")
    if entries != expected_entries:
        sys.exit("verification failed: entries differ from repository-grouped catalog projection")

    for position, entry in enumerate(entries):
        _verify_entry(position, entry)

    type_counts = Counter(entry.get("type") for entry in entries)
    verdict_counts = Counter(entry["eval"]["security"]["verdict"] for entry in entries)
    missing_source_url = sum(not entry["source"].get("url") for entry in entries)
    missing_source_sha = sum(not entry["source"].get("sha") for entry in entries)
    missing_evaluated_at = sum(not entry["source"].get("evaluated_at") for entry in entries)
    subdir_count = sum(entry["source"].get("subdir") is not None for entry in entries)
    missing_scanned_at = sum(
        entry["eval"]["security"]["verdict"] != "unscanned"
        and not entry["eval"]["security"].get("scanned_at")
        for entry in entries
    )
    stats = {
        **{key: value for key, value in reconciliation.items() if not isinstance(value, list)},
        "total_entries": len(entries),
        "type_counts": dict(sorted(type_counts.items())),
        "missing_source_url": missing_source_url,
        "missing_source_sha": missing_source_sha,
        "missing_evaluated_at": missing_evaluated_at,
        "subdir_entries": subdir_count,
        "verdict_counts": dict(sorted(verdict_counts.items())),
        "missing_scanned_at": missing_scanned_at,
        "duplicate_catalog_ids": 0,
        "sha256": sha256_file(output),
    }

    print("verification passed")
    print(f"  input catalog items:        {stats['input_entries']}")
    print(f"  included repositories (N): {stats['included_repositories']}")
    print(f"  collapsed catalog items (M): {stats['collapsed_catalog_items']}")
    print(f"  discarded awesome groups (K): {stats['discarded_repository_groups']}")
    print(f"  discarded group items:     {stats['discarded_catalog_items']}")
    print(f"  ungroupable catalog items: {stats['ungroupable_catalog_items']}")
    print(f"  repository coverage:       {stats['repository_coverage']:.2f}%")
    print(
        "  old by type:               "
        + " ".join(
            f"{key}={value}" for key, value in sorted(reconciliation["old_type_counts"].items())
        )
    )
    print(
        "  new by type:               "
        + " ".join(f"{key}={value}" for key, value in stats["type_counts"].items())
    )
    print(f"  missing source.url:        {missing_source_url}")
    print(f"  missing source.sha:        {missing_source_sha}")
    print(f"  missing evaluated_at:      {missing_evaluated_at}")
    print(f"  subdir != null:            {subdir_count}")
    print(
        "  verdicts:                  "
        + " ".join(f"{key}={value}" for key, value in stats["verdict_counts"].items())
    )
    print(f"  scanned verdict missing scanned_at: {missing_scanned_at}")
    print(f"  score aggregation entries: {stats['score_aggregation_entries']}")
    print(
        "  child-only scores kept null: "
        f"groups={stats['child_only_score_groups_kept_null']} "
        + " ".join(
            f"{key}={value}"
            for key, value in sorted(stats["child_only_score_fields_kept_null"].items())
        )
    )
    print(f"  duplicate catalog_id:      {stats['duplicate_catalog_ids']}")
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--verify",
        action="store_true",
        help="verify the generated manifest against the repository-grouped catalog",
    )
    args = parser.parse_args()

    build(args.output)
    if args.verify:
        verify(args.output)


if __name__ == "__main__":
    main()
