#!/usr/bin/env python3
"""Build a self-contained catalog bundle for downstream consumers (e.g. costrict-web).

Layout produced (inside the tarball):

    manifest.json            - bundle metadata (schema_version, entry_count, index_sha256, ...)
    index.json               - copy of catalog/index.json (per-entry metadata + content_hash)
    catalog-download/
        mcp/<id>/.mcp.json
        skills/<id>/SKILL.md
        plugins/<id>/.plugin.json
        prompts/<id>/PROMPT.md
        rules/<id>/RULE.md
        ...                  - all bundled content files, untouched

Why this shape:
- `index.json` IS the canonical manifest (every entry has `security.content_hash`).
  Downstream can diff against the DB without opening any file.
- `catalog-download/` is the per-file payload, only needed when content_hash differs.
- One tarball, one HTTP request, no git protocol overhead.

Usage:
    python scripts/build_catalog_bundle.py
    python scripts/build_catalog_bundle.py --output dist/catalog-bundle.tar.gz
    python scripts/build_catalog_bundle.py --no-compress  # build .tar without gzip (faster locally)
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import tarfile
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = REPO_ROOT / "dist" / "catalog-bundle.tar.gz"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# Per-type primary file under catalog-download/. MUST stay aligned with
# download_catalog._PRIMARY_FILE_BY_TYPE and the merge _SOURCE_TO_TYPE_DIR table
# — a type missing here is silently dropped from the bundle as ``unknown_type``
# even when its file exists on disk.
TYPE_DIR_AND_FILE = {
    "mcp":      ("mcp",       ".mcp.json"),
    "skill":    ("skills",    "SKILL.md"),
    "plugin":   ("plugins",   ".plugin.json"),
    "prompt":   ("prompts",   "PROMPT.md"),
    "rule":     ("rules",     "RULE.md"),
    "command":  ("commands",  "COMMAND.md"),
    "subagent": ("subagents", "AGENT.md"),
    "template": ("templates", "TEMPLATE.md"),
}


def _entry_file(entry: dict) -> Path | None:
    """Return the canonical file path under catalog-download/ for an entry,
    or None if the entry's type is unknown."""
    spec = TYPE_DIR_AND_FILE.get(entry.get("type") or "")
    if spec is None:
        return None
    type_dir, filename = spec
    return REPO_ROOT / "catalog-download" / type_dir / entry["id"] / filename


def _mcp_is_empty_stub(path: Path) -> bool:
    """Return True when the .mcp.json contains only placeholder server configs
    with no install information. Pattern: ``mcpServers.<name>: {}`` (also
    treats command='' as empty since downstream NormalizeMCPMetadata trims).
    """
    try:
        with path.open("rb") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):
        # Malformed JSON is its own failure mode; let downstream report it
        # rather than silently dropping here.
        return False
    servers = data.get("mcpServers")
    if not isinstance(servers, dict) or not servers:
        return True
    for cfg in servers.values():
        if not isinstance(cfg, dict):
            return True
        command = cfg.get("command")
        url = cfg.get("url")
        has_command = isinstance(command, str) and command.strip()
        has_url = isinstance(url, str) and url.strip()
        if has_command or has_url:
            return False
    return True


try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover - PyYAML always present in repo's venv
    yaml = None  # heuristic fallback enabled when missing


def _has_broken_md_frontmatter(path: Path) -> bool:
    """Return True when the PROMPT.md frontmatter cannot be YAML-parsed.

    Strategy: if PyYAML is available, actually try to parse the frontmatter
    block — that catches every variant of YAML breakage (unquoted ':', EOF
    mid-quote, control chars in identifiers, …). When PyYAML isn't
    importable, fall back to a coarse heuristic that catches the common
    ``description: text: with: colons`` shape only.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    if not text.startswith("---"):
        return False
    end = text.find("\n---", 3)
    if end < 0:
        return False
    block = text[3:end]

    if yaml is not None:
        try:
            yaml.safe_load(block)
            return False
        except yaml.YAMLError:
            return True

    # Heuristic fallback — only the leading-':' shape.
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        first_colon = line.find(":")
        if first_colon < 0:
            continue
        value = line[first_colon + 1:].strip()
        if not value:
            continue
        if (value.startswith("'") and value.endswith("'")) or (value.startswith('"') and value.endswith('"')):
            continue
        if value in ("|", ">", "|-", ">-", "|+", ">+"):
            continue
        if ": " in value:
            return True
    return False


def build(output: Path, *, compress: bool = True) -> dict:
    index_path = REPO_ROOT / "catalog" / "index.json"
    download_dir = REPO_ROOT / "catalog-download"

    if not index_path.is_file():
        sys.exit(f"missing {index_path} - run download_catalog.py first")
    if not download_dir.is_dir():
        sys.exit(f"missing {download_dir} - run download_catalog.py first")

    full_entries = json.loads(index_path.read_text(encoding="utf-8"))

    # Filter the index in three passes — each pass drops a category of
    # entries that the downstream ingest cannot use, and reports the count
    # so upstream maintainers can see exactly what data is being shed.
    #
    #   1. unknown_type   — `type` not in TYPE_DIR_AND_FILE
    #   2. orphan_no_file — `download_catalog.py` produced no on-disk file
    #   3. unusable_*     — file exists but content is a known-empty stub:
    #        • mcp .mcp.json with mcpServers.<name>: {} (no command/url) —
    #          registry.modelcontextprotocol.io listed the server but did
    #          not yield install info. ~63% of mcp/ today.
    #        • PROMPT.md with description containing an unquoted ':' in
    #          the YAML frontmatter (mapping parser barfs). ~33% of
    #          prompts/ today.
    #
    # Both unusable_* cases are upstream data-generator bugs. Filtering at
    # bundle time means downstream's `incomplete` counter only fires when a
    # new variant slips through.
    entries: list[dict] = []
    orphan_count = 0
    unknown_type_count = 0
    unusable_mcp_stub = 0
    unusable_yaml = 0
    for entry in full_entries:
        target = _entry_file(entry)
        if target is None:
            unknown_type_count += 1
            continue
        if not target.is_file():
            orphan_count += 1
            continue
        # Per-type usability checks
        if entry["type"] == "mcp" and _mcp_is_empty_stub(target):
            unusable_mcp_stub += 1
            continue
        # PROMPT.md / SKILL.md / RULE.md all share the same SKILLMD-style
        # YAML frontmatter parser downstream; any of them with broken
        # frontmatter will fail at ingest.
        if entry["type"] in ("prompt", "skill", "rule") and _has_broken_md_frontmatter(target):
            unusable_yaml += 1
            continue
        entries.append(entry)

    entries, missing_parent_child_count, stale_reverse_ref_count = (
        _prune_plugin_child_parent_consistency(entries)
    )
    print(f"index.json: {len(full_entries)} entries → bundled {len(entries)}")
    print(f"  dropped: orphan_no_file={orphan_count} unknown_type={unknown_type_count} "
          f"mcp_empty_stub={unusable_mcp_stub} md_yaml_broken={unusable_yaml}")
    print(
        "  plugin child consistency: "
        f"missing_parent={missing_parent_child_count} "
        f"stale_reverse_refs={stale_reverse_ref_count}"
    )

    # Write a filtered index.json to a tempfile inside dist/ so we hash and
    # ship the SAME bytes that downstream will diff against.
    filtered_index_path = output.parent / "index.filtered.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    filtered_bytes = json.dumps(entries, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"
    filtered_index_path.write_bytes(filtered_bytes)
    index_sha256 = hashlib.sha256(filtered_bytes).hexdigest()

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "entry_count": len(entries),
        "index_sha256": index_sha256,
        "type_counts": _type_counts(entries),
        "filtered_from": len(full_entries),
        "orphan_dropped": orphan_count,
        "unknown_type_dropped": unknown_type_count,
        "plugin_child_missing_parent_dropped": missing_parent_child_count,
        "plugin_child_stale_reverse_refs_dropped": stale_reverse_ref_count,
    }
    manifest_bytes = json.dumps(manifest, indent=2, sort_keys=False).encode("utf-8") + b"\n"

    mode = "w:gz" if compress else "w"
    with tarfile.open(output, mode, format=tarfile.PAX_FORMAT) as tar:
        _add_bytes(tar, "manifest.json", manifest_bytes)
        _add_bytes(tar, "index.json", filtered_bytes)
        # catalog-download tree, preserved relative path. We deliberately
        # include the entire tree (not just per-entry files) so that
        # SKILL.md siblings like references/, scripts/ also travel with us
        # — downstream asset sync needs them.
        #
        # `filter=_normalize_member` re-encodes every tar entry name in
        # Unicode NFC so that downstream Go (which compares index.json
        # entry IDs — which are NFC because Python's json defaults to
        # NFC — against on-disk paths) can find files whose source
        # filenames were stored as NFD on macOS-built bundles. Without
        # this, names like "görsel" / "için" / "sporsmaç" fail to open
        # on the consumer side with ENOENT despite being inside the tar.
        tar.add(
            download_dir,
            arcname="catalog-download",
            recursive=True,
            filter=_normalize_member,
        )

    # Tidy up the staging file once it has been folded into the tarball.
    filtered_index_path.unlink(missing_ok=True)

    bundle_sha256 = sha256_file(output)
    print(f"wrote {output}")
    print(f"  size:        {output.stat().st_size:,} bytes")
    print(f"  entries:     {manifest['entry_count']}")
    print(f"  index_sha:   {index_sha256[:16]}...")
    print(f"  bundle_sha:  {bundle_sha256[:16]}...")
    return {**manifest, "bundle_sha256": bundle_sha256, "output_path": str(output)}


def _prune_plugin_child_parent_consistency(entries: list[dict]) -> tuple[list[dict], int, int]:
    """Keep bundled plugin children only when their parent plugin is present.

    Earlier build passes can legitimately remove parent plugin entries (for
    example no downloaded plugin payload) or child entries (for example broken
    SKILL.md frontmatter). The bundle index is the final downstream contract, so
    parent/child references must be internally consistent at this point.
    """
    plugin_ids = {
        entry.get("id")
        for entry in entries
        if entry.get("type") == "plugin" and isinstance(entry.get("id"), str)
    }

    pruned: list[dict] = []
    missing_parent_count = 0
    for entry in entries:
        bundled_in = entry.get("bundled_in")
        if isinstance(bundled_in, str) and bundled_in.strip():
            if bundled_in not in plugin_ids:
                missing_parent_count += 1
                continue
        pruned.append(entry)

    present_ids = {
        entry.get("id")
        for entry in pruned
        if isinstance(entry.get("id"), str)
    }
    stale_reverse_ref_count = 0
    for entry in pruned:
        if entry.get("type") != "plugin":
            continue
        bundle = entry.get("bundle")
        if not isinstance(bundle, dict):
            continue
        for key in ("bundled_skill_ids", "bundled_mcp_ids"):
            ids = bundle.get(key)
            if not isinstance(ids, list):
                continue
            cleaned = []
            for child_id in ids:
                if isinstance(child_id, str) and child_id not in present_ids:
                    stale_reverse_ref_count += 1
                    cleaned.append(None)
                else:
                    cleaned.append(child_id)
            bundle[key] = cleaned

    return pruned, missing_parent_count, stale_reverse_ref_count


def _type_counts(entries: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for e in entries:
        t = e.get("type") or "unknown"
        counts[t] = counts.get(t, 0) + 1
    return counts


def _add_bytes(tar: tarfile.TarFile, arcname: str, payload: bytes) -> None:
    info = tarfile.TarInfo(name=arcname)
    info.size = len(payload)
    info.mtime = int(datetime.now(timezone.utc).timestamp())
    info.mode = 0o644
    tar.addfile(info, io.BytesIO(payload))


def _add_file(tar: tarfile.TarFile, src: Path, arcname: str) -> None:
    info = tar.gettarinfo(str(src), arcname=arcname)
    if info is None:
        sys.exit(f"failed to stat {src}")
    with src.open("rb") as fh:
        tar.addfile(info, fh)


def _normalize_member(info: tarfile.TarInfo) -> tarfile.TarInfo:
    """Rewrite the entry's name (and link target, if any) to Unicode NFC.

    macOS's HFS+/APFS report directory names in NFD form (combining marks
    are separate codepoints), so `Path.iterdir()` yields strings whose
    bytes do not match index.json — which is written by upstream Python
    pipelines that default to NFC. Forcing NFC at pack time keeps the
    tar contents byte-stable across the macOS-build → Linux-consume hop.
    """
    info.name = unicodedata.normalize("NFC", info.name)
    if info.linkname:
        info.linkname = unicodedata.normalize("NFC", info.linkname)
    return info


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--no-compress", action="store_true", help="build .tar (no gzip)")
    args = parser.parse_args()

    output = args.output
    if args.no_compress and output.suffix == ".gz":
        output = output.with_suffix("")  # strip .gz when not compressing

    build(output, compress=not args.no_compress)


if __name__ == "__main__":
    main()
