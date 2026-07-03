#!/usr/bin/env python3
"""First-party cos-graph catalog entry (xixingde/cos-graph @ csc-plugin).

Emits the web-hub CATALOG ENTRY for the ``graphify`` plugin. The repo CONTENT is
published separately as a FULL-REPO MIRROR (see below) — this script only makes
graphify listed & scored in the hub:

    catalog/plugins/index.json  (this script; entry carries external_mirror=true)
      → merge_index.py        → catalog/index.json
      → download_catalog.py   → catalog-download/plugins/graphify/.plugin.json
      → build_catalog_bundle  → catalog-bundle.tar.gz
      → costrict-web migrate ingest-upstream
                              → capability_items (web hub: graphify listed, scored)

The plugin's marketplace repo (``costrict-plugins-repo/graphify``) is NOT built
by ``costrict-plugin-marketplace/build.py`` for this entry. cos-graph's substance
(the ``graphify/`` Python package, docs, tests) lives OUTSIDE the
``graphify-plugin/`` subdir, so it is published as a FULL mirror of the whole
``csc-plugin`` branch by the dedicated git-mirror step in
``.github/workflows/sync-cosgraph-plugins.yml``. The ``external_mirror=true`` flag
(set on the entry below) makes build.py SKIP extracting/publishing this plugin's
bare repo — otherwise ``find_plugin_root`` would rglob to ``graphify-plugin/`` and
the pushed 11-file wrapper would clobber the full mirror.

Sibling of ``sync_plugins_csc.py`` (cospowers, yhangf/csc-plugins): same
first-party CATALOG recipe (fixed ``marketplace_verified=true`` + perfect
``final_score``, bypassing ai-resource-eval), different source and publish model
(cospowers = subdir extraction; cos-graph = full-repo mirror). A dedicated script
per first-party source matches the existing per-source convention
(``sync_plugins_official`` / ``sync_plugins_dev`` / ``sync_plugins_csc``).

Why a dedicated first-party script instead of ``sync_plugins_official``:

  - First-party (curated): fixed ``marketplace_verified=true`` + perfect
    ``final_score`` instead of the upstream ai-resource-eval scoring pipeline.
  - The plugin lives on a non-default branch (``csc-plugin``) of a repo whose
    default branch is unrelated product code; the official sync would not target
    it. Discovery here is subdir-driven (scan ``<subdir>/.claude-plugin/
    plugin.json`` → ``graphify-plugin``) purely to derive the hub METADATA
    (name/version/bundle counts); the repo content comes from the full mirror.

Idempotency / "manual re-sync": this script **merge-preserves** —
it loads the existing ``catalog/plugins/index.json``, drops any prior entries it
owns (``source == "cos-graph"``), re-derives the entries from the *live*
cos-graph tree (so version / description / bundle-count changes are picked up),
and writes the union back. Re-running it == syncing the latest cos-graph.

Run order: must run **after** ``sync_plugins_official.py`` (which overwrites the
whole index) and may run before/after ``sync_plugins_dev.py`` /
``sync_plugins_csc.py`` (all merge-preserve). See ``.github/workflows/sync.yml``
/ ``sync-cosgraph-plugins.yml``.

Implementation notes:
  - Standard library only (urllib, json) — matches sync_plugins_official.py.
  - Honors GITHUB_TOKEN for github.com / api.github.com / raw requests.
  - Bundle counts (skills/commands/agents/hooks/mcp) are derived from a single
    recursive Git Tree API call so they stay accurate across upstream changes.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import urllib.error
import urllib.request
from datetime import date
from typing import Optional

# Allow running both as `python scripts/sync_plugins_cosgraph.py` and as a module.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from .utils import categorize, extract_tags, load_index, save_index  # type: ignore
except ImportError:  # pragma: no cover - script-style invocation
    from utils import categorize, extract_tags, load_index, save_index  # type: ignore


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
OUTPUT_PATH = os.path.join(REPO_ROOT, "catalog", "plugins", "index.json")
CATALOG_INDEX_PATH = os.path.join(REPO_ROOT, "catalog", "index.json")

# The first-party source we own. Entries with this `source` are replaced
# wholesale on every run (idempotent re-sync). `source_priority` sits at the
# top so a (marketplace_repo, plugin_name) collision could never demote us.
SOURCE_ID = "cos-graph"
SOURCE_PRIORITY = 1000

SOURCE_REPO = "xixingde/cos-graph"       # <owner>/<repo> — upstream mirror source (not user-facing)
SOURCE_BRANCH_DEFAULT = "csc-plugin"     # DEFAULT (canonical) ref; override per-run via --branch / $SOURCE_BRANCH

# User-facing home: the full-repo mirror is published under our org as
# costrict-plugins-repo/<name>, which is what `csc plugin install
# <name>@costrict-plugins` clones. install.marketplace_repo points here so the web
# hub's "Upstream Source" link shows our repo, not the upstream product repo.
# (source_url below stays on SOURCE_REPO/<subdir> — used only to derive the hub
# METADATA counts; the actual repo content is the full mirror, not this subdir.)
COSTRICT_ORG = "costrict-plugins-repo"

# Self-own: first-party plugins get a fixed perfect score instead of the
# upstream ai-resource-eval pipeline. 0-100 scale (web ingest maps
# final_score -> capability_items.experience_score verbatim).
FINAL_SCORE = 100

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
USER_AGENT = "everything-ai-coding-plugins-sync"

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("sync_plugins_cosgraph")


# ---------------------------------------------------------------------------
# HTTP helpers (stdlib only) — mirror sync_plugins_official.py
# ---------------------------------------------------------------------------

def _http_get(url: str, timeout: int = 30) -> Optional[bytes]:
    headers = {"User-Agent": USER_AGENT}
    is_github = (
        "raw.githubusercontent.com" in url
        or url.startswith("https://api.github.com/")
        or "github.com" in url
    )
    if GITHUB_TOKEN and is_github:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            logger.debug("404 Not Found: %s", url)
        else:
            logger.warning("HTTP %s for %s: %s", e.code, url, e.reason)
        return None
    except (urllib.error.URLError, TimeoutError) as e:
        logger.warning("Network error for %s: %s", url, e)
        return None
    except Exception as e:  # noqa: BLE001 - keep the script robust
        logger.warning("Unexpected error fetching %s: %s", url, e)
        return None


def _http_get_json(url: str, timeout: int = 30) -> Optional[dict | list]:
    body = _http_get(url, timeout=timeout)
    if body is None:
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        logger.warning("JSON decode error for %s: %s", url, e)
        return None


def _raw_url(repo: str, branch: str, path: str) -> str:
    return f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"


# ---------------------------------------------------------------------------
# Discovery + bundle counting from the recursive Git Tree
# ---------------------------------------------------------------------------

def fetch_repo_meta(repo: str) -> dict:
    """Fetch stars + pushed_at for the source repo (shared by all its plugins)."""
    data = _http_get_json(f"https://api.github.com/repos/{repo}")
    if not isinstance(data, dict):
        return {"stars": 0, "pushed_at": None}
    return {
        "stars": data.get("stargazers_count") or 0,
        "pushed_at": data.get("pushed_at"),
    }


def fetch_tree_paths(repo: str, branch: str) -> list[str]:
    """Return every blob path in the repo via one recursive Git Tree API call."""
    data = _http_get_json(
        f"https://api.github.com/repos/{repo}/git/trees/{branch}?recursive=1"
    )
    if not isinstance(data, dict):
        return []
    if data.get("truncated"):
        logger.warning("Git tree for %s@%s was truncated; counts may be partial", repo, branch)
    return [
        item["path"]
        for item in data.get("tree", [])
        if isinstance(item, dict) and item.get("type") == "blob" and item.get("path")
    ]


def resolve_branch_sha(repo: str, branch: str) -> Optional[str]:
    """Resolve a branch name (which may contain ``/``) to its commit SHA.

    ``git/trees`` and the ``raw.githubusercontent.com`` path both take the ref
    as a single path segment, so a slash-containing branch like ``feat/x``
    404s there. The ``git/ref/heads/<branch>`` endpoint captures the full ref
    path, so resolve once and read content by the unambiguous SHA. Returns None
    if the branch does not resolve to a single exact ref.
    """
    data = _http_get_json(f"https://api.github.com/repos/{repo}/git/ref/heads/{branch}")
    # An exact match yields one ref object; a prefix match yields a list (reject).
    if isinstance(data, dict):
        sha = (data.get("object") or {}).get("sha")
        if sha:
            return sha
    return None


def discover_plugin_subdirs(tree_paths: list[str]) -> list[str]:
    """Top-level subdirs that carry a `.claude-plugin/plugin.json` (sorted)."""
    subdirs = set()
    for path in tree_paths:
        parts = path.split("/")
        if len(parts) >= 3 and parts[1] == ".claude-plugin" and parts[2] == "plugin.json":
            subdirs.add(parts[0])
    return sorted(subdirs)


def _empty_bundle() -> dict:
    return {
        "skills_count": 0,
        "commands_count": 0,
        "agents_count": 0,
        "evaluators_count": 0,
        "rules_count": 0,
        "templates_count": 0,
        "mcp_servers_count": 0,
        "skills_namespaces": [],
        "hooks_count": 0,
        "hook_events": [],
        "mcp_server_names": [],
        "is_marketplace_repo": False,
    }


def _strip_md(rel: str) -> str:
    """Drop a trailing ``.md`` from a repo-relative path used as a child name.

    Single-file components (commands/agents/rules/templates) name themselves
    after their repo-relative path; stripping the extension keeps the name
    readable while preserving any nested group prefix (e.g. ``dfx/安全``).
    """
    return rel[:-3] if rel.endswith(".md") else rel


def compute_bundle(tree_paths: list[str], subdir: str, plugin_name: str, branch: str = SOURCE_BRANCH_DEFAULT) -> dict:
    """Derive bundle counts + child paths for one plugin subdir from the repo tree.

    Every functional component directory is captured as a position-aligned
    ``(<kind>_namespaces, <kind>_paths)`` pair so ``merge_index`` can synthesize
    a standalone, path-faithful catalog entry per file/dir (``bundled_in`` →
    this plugin):

    - skills:     ``<subdir>/skills/<name>/SKILL.md``        DIRECTORY → type=skill
    - evaluators: ``<subdir>/evaluators/<name>/SKILL.md``    DIRECTORY → type=skill
    - commands:   ``<subdir>/commands/<file>``               FILE      → type=command
    - agents:     ``<subdir>/agents/<file>.md``              FILE      → type=subagent
    - rules:      ``<subdir>/rules/<group>/<file>.md`` (nested!) FILE  → type=rule
    - templates:  ``<subdir>/templates/<file>.md``           FILE      → type=template

    ``*_paths`` are repo-relative and verbatim (path-faithful — the web hub's
    work tree mirrors the real on-disk layout). ``*_namespaces`` are
    ``<plugin>:<name>`` where ``<name>`` is a stable per-component identifier
    (directory name for dir-type, repo-relative-minus-extension for files;
    rules keep their ``<group>/<file>`` shape so nested groups round-trip).
    Both lists share the same sorted order so ``element[i]`` align.
    """
    bundle = _empty_bundle()
    # name -> repo-relative SKILL.md path. merge_index orphan synthesis needs
    # the path (position-aligned with skills_namespaces) plus source_repo/ref
    # to materialize each bundled skill as a standalone catalog entry; without
    # them the children silently stay un-synthesized (warn + None).
    skill_paths_by_name: dict[str, str] = {}
    evaluator_paths_by_name: dict[str, str] = {}
    command_paths_by_name: dict[str, str] = {}
    agent_paths_by_name: dict[str, str] = {}
    rule_paths_by_name: dict[str, str] = {}
    template_paths_by_name: dict[str, str] = {}
    skills_prefix = f"{subdir}/skills/"
    evaluators_prefix = f"{subdir}/evaluators/"
    commands_prefix = f"{subdir}/commands/"
    agents_prefix = f"{subdir}/agents/"
    rules_prefix = f"{subdir}/rules/"
    templates_prefix = f"{subdir}/templates/"

    for path in tree_paths:
        if path.startswith(skills_prefix) and path.endswith("/SKILL.md"):
            # Directory-type child: name = first segment under skills/.
            rel = path[len(skills_prefix):]
            name = rel.split("/", 1)[0]
            if name:
                skill_paths_by_name.setdefault(name, path)
        elif path.startswith(evaluators_prefix) and path.endswith("/SKILL.md"):
            # Directory-type child (same shape as a skill, different dir).
            rel = path[len(evaluators_prefix):]
            name = rel.split("/", 1)[0]
            if name:
                evaluator_paths_by_name.setdefault(name, path)
        elif path.startswith(commands_prefix):
            # Single-file child: name = repo-relative path under commands/
            # minus a trailing .md (keeps nested command groups distinct).
            rel = path[len(commands_prefix):]
            if rel and not rel.endswith("/"):
                command_paths_by_name.setdefault(_strip_md(rel), path)
        elif path.startswith(agents_prefix) and path.endswith(".md"):
            rel = path[len(agents_prefix):]
            if rel:
                agent_paths_by_name.setdefault(_strip_md(rel), path)
        elif path.startswith(rules_prefix) and path.endswith(".md"):
            # Nested: rules/<group>/<file>.md — keep <group>/<file> so the id
            # carries the group and stays collision-free across groups.
            rel = path[len(rules_prefix):]
            if rel:
                rule_paths_by_name.setdefault(_strip_md(rel), path)
        elif path.startswith(templates_prefix) and path.endswith(".md"):
            rel = path[len(templates_prefix):]
            if rel:
                template_paths_by_name.setdefault(_strip_md(rel), path)

    def _emit(kind_count: str, kind_ns: str, kind_paths: str, by_name: dict[str, str]) -> None:
        names = sorted(by_name)
        bundle[kind_count] = len(names)
        bundle[kind_ns] = [f"{plugin_name}:{n}" for n in names]
        bundle[kind_paths] = [by_name[n] for n in names]

    _emit("skills_count", "skills_namespaces", "skill_paths", skill_paths_by_name)
    _emit("evaluators_count", "evaluators_namespaces", "evaluator_paths", evaluator_paths_by_name)
    _emit("commands_count", "commands_namespaces", "command_paths", command_paths_by_name)
    _emit("agents_count", "agents_namespaces", "agent_paths", agent_paths_by_name)
    _emit("rules_count", "rules_namespaces", "rule_paths", rule_paths_by_name)
    _emit("templates_count", "templates_namespaces", "template_paths", template_paths_by_name)

    bundle["source_repo"] = SOURCE_REPO
    bundle["source_ref"] = branch
    bundle["plugin_root"] = subdir
    return bundle


# ---------------------------------------------------------------------------
# Per-plugin entry construction
# ---------------------------------------------------------------------------

def build_entry(
    subdir: str,
    tree_paths: list[str],
    repo_meta: dict,
    last_synced_iso: str,
    branch: str = SOURCE_BRANCH_DEFAULT,
    read_ref: Optional[str] = None,
) -> Optional[dict]:
    """Build a catalog entry for one cos-graph plugin subdir.

    Reads the subdir's `plugin.json` (canonical name/description/version) and
    `marketplace.json` (marketplace_name). Returns None if plugin.json is
    unreadable or nameless.

    `read_ref` is the ref used for the raw content reads (a commit SHA when the
    branch contains a slash); `branch` stays the human-readable ref baked into
    source_url / source_ref. They denote the same commit.
    """
    read_ref = read_ref or branch
    plugin_json = _http_get_json(
        _raw_url(SOURCE_REPO, read_ref, f"{subdir}/.claude-plugin/plugin.json")
    )
    if not isinstance(plugin_json, dict):
        logger.warning("Skipping %s: cannot read .claude-plugin/plugin.json", subdir)
        return None

    name = (plugin_json.get("name") or "").strip()
    if not name:
        logger.warning("Skipping %s: plugin.json has no name", subdir)
        return None

    description = (plugin_json.get("description") or "").strip()
    version = (plugin_json.get("version") or "").strip() or "0.0.0"

    marketplace_json = _http_get_json(
        _raw_url(SOURCE_REPO, read_ref, f"{subdir}/.claude-plugin/marketplace.json")
    )
    marketplace_name = None
    if isinstance(marketplace_json, dict):
        marketplace_name = (marketplace_json.get("name") or "").strip() or None
    # download_catalog._download_plugin requires marketplace_name; fall back to
    # the plugin name so the gate never trips for a first-party plugin. cos-graph
    # keeps its marketplace.json at the repo root (not the subdir), so the subdir
    # read above 404s and this fallback is the normal path here.
    if not marketplace_name:
        marketplace_name = name

    # id == plugin name: clean first-party marketplace repo name
    # (costrict-plugins-repo/graphify.git) and the same token the user types in
    # `csc plugin install <name>@costrict-plugins`.
    plugin_id = name

    source_url = f"https://github.com/{SOURCE_REPO}/tree/{branch}/{subdir}"
    tags = ["cos-graph", "knowledge-graph"] + extract_tags(name, description)
    seen: set[str] = set()
    tags = [t for t in tags if not (t in seen or seen.add(t))]
    category = categorize(name=name, description=description, tags=tags)

    bundle = compute_bundle(tree_paths, subdir, name, branch)

    return {
        "id": plugin_id,
        "name": name,
        "type": "plugin",
        "description": description,
        "source_url": source_url,
        "category": category,
        "tags": tags,
        "tech_stack": [],
        "source": SOURCE_ID,
        "source_priority": SOURCE_PRIORITY,
        "marketplace_url": f"https://github.com/{COSTRICT_ORG}/{plugin_id}",
        "platforms": ["claude-code"],
        "install": {
            "method": "plugin_marketplace",
            "plugin_name": name,
            # Our own published repo (what csc actually installs from) — keeps the
            # upstream product monorepo out of the hub's Upstream Source link.
            "marketplace_repo": f"{COSTRICT_ORG}/{plugin_id}",
            "marketplace_name": marketplace_name,
            "marketplace_verified": True,
            "marketplace": f"{COSTRICT_ORG}/{plugin_id}",
        },
        "bundle": bundle,
        "manifest_completeness": 1.0,
        "last_synced": last_synced_iso,
        "stars": repo_meta.get("stars") or 0,
        "pushed_at": repo_meta.get("pushed_at"),
        "version": version,
        # First-party: fixed perfect score + matching health, bypassing the
        # ai-resource-eval pipeline (these never run through scoring).
        "final_score": FINAL_SCORE,
        "health": {
            # freshness_label enum per catalog/schema.json: active|stale|abandoned
            "score": FINAL_SCORE,
            "freshness_label": "active",
            "signals": {},
        },
        "verified": True,
        # Mirror the source subdir verbatim in the marketplace (rules/, templates/,
        # evaluators/, examples/, CLAUDE.md, …). costrict-plugin-marketplace/build.py
        # reads this and skips its size-pruning for these entries.
        "prune_content": False,
        # cos-graph is published as a FULL-REPO mirror (the entire csc-plugin branch,
        # incl. the graphify/ package, docs, tests that live OUTSIDE graphify-plugin/),
        # maintained by the dedicated mirror step in sync-cosgraph-plugins.yml — NOT by
        # build.py's subdir extraction. This flag tells costrict-plugin-marketplace's
        # build.py to SKIP building/publishing this plugin's bare repo (its find_plugin_root
        # would otherwise rglob to graphify-plugin/ and clobber the full mirror with the
        # 11-file thin wrapper). The entry still flows into the catalog-bundle so graphify
        # stays listed & scored in the web hub; install.marketplace_repo points at the
        # externally-mirrored repo.
        "external_mirror": True,
    }


# ---------------------------------------------------------------------------
# Merge-preserve into catalog/plugins/index.json
# ---------------------------------------------------------------------------

def merge_into_index(existing: list[dict], fresh: list[dict], sort: bool = True) -> list[dict]:
    """Replace all prior `source == SOURCE_ID` entries with `fresh`, keep rest.

    sort=True  → sort by id (readable diffs for the small per-type index).
    sort=False → preserve the existing entries' order and append `fresh` at the
                 end. Used for the 33MB top-level catalog/index.json so a re-sync
                 produces a small diff instead of re-sorting the whole file.
    """
    kept = [e for e in existing if e.get("source") != SOURCE_ID]
    merged = kept + fresh
    if sort:
        merged.sort(key=lambda e: e.get("id", ""))
    return merged


def collect_entries(branch: str = SOURCE_BRANCH_DEFAULT) -> list[dict]:
    """Fetch the live cos-graph tree at `branch` and build all plugin entries."""
    last_synced_iso = date.today().isoformat()
    repo_meta = fetch_repo_meta(SOURCE_REPO)
    # A slash-containing branch (feat/x) can't be read directly via git/trees or
    # raw (single path segment), so resolve it to a commit SHA once and read all
    # content by SHA, while keeping the human-readable `branch` for source_url /
    # source_ref. Non-slash refs read directly (zero extra call, no regression).
    read_ref = branch
    if "/" in branch:
        sha = resolve_branch_sha(SOURCE_REPO, branch)
        if not sha:
            logger.error("Cannot resolve branch %s@%s to a SHA — aborting", SOURCE_REPO, branch)
            return []
        logger.info("Resolved %s@%s → %s for content reads", SOURCE_REPO, branch, sha[:12])
        read_ref = sha
    tree_paths = fetch_tree_paths(SOURCE_REPO, read_ref)
    if not tree_paths:
        logger.error("Empty/failed git tree for %s@%s — aborting", SOURCE_REPO, branch)
        return []
    subdirs = discover_plugin_subdirs(tree_paths)
    logger.info("Discovered %d plugin subdir(s): %s", len(subdirs), ", ".join(subdirs))

    entries: list[dict] = []
    for subdir in subdirs:
        try:
            entry = build_entry(subdir, tree_paths, repo_meta, last_synced_iso, branch, read_ref)
        except Exception as e:  # noqa: BLE001 - never let one plugin kill the run
            logger.warning("Failed to build entry for %s: %s", subdir, e)
            continue
        if entry is not None:
            entries.append(entry)
    return entries


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sync xixingde/cos-graph (graphify) into catalog/plugins/index.json.",
    )
    parser.add_argument(
        "--output",
        default=OUTPUT_PATH,
        help=f"Per-type plugins index.json path (default: {OUTPUT_PATH})",
    )
    parser.add_argument(
        "--overlay-catalog-index",
        action="store_true",
        help=(
            "Also surgically overlay the entries into the top-level "
            "catalog/index.json (drop prior source=cos-graph, append fresh), "
            "preserving every other entry's enrichment. Use this in the manual "
            "sync workflow so the bundle picks them up WITHOUT a full "
            "merge_index --skip-enrichment (which would wipe all scores). The "
            "weekly sync omits this flag and lets merge_index rebuild instead."
        ),
    )
    parser.add_argument(
        "--catalog-index",
        default=CATALOG_INDEX_PATH,
        help=f"Top-level catalog index for --overlay-catalog-index (default: {CATALOG_INDEX_PATH})",
    )
    parser.add_argument(
        "--branch",
        default=os.environ.get("SOURCE_BRANCH", "").strip() or SOURCE_BRANCH_DEFAULT,
        help=(
            f"cos-graph ref (branch/tag) to sync from (default: ${{SOURCE_BRANCH}} or "
            f"{SOURCE_BRANCH_DEFAULT!r}). A non-default ref pulls that branch's content into "
            "every entry's source_url / source_ref so the marketplace build clones it; "
            "use it to preview a branch before it merges to csc-plugin."
        ),
    )
    args = parser.parse_args(argv)

    # A present-but-blank --branch (e.g. an empty manual workflow input) must not
    # become an empty ref — fall back to the default branch.
    branch = (args.branch or "").strip() or SOURCE_BRANCH_DEFAULT
    logger.info("Syncing cos-graph from %s@%s", SOURCE_REPO, branch)
    fresh = collect_entries(branch)
    if not fresh:
        logger.error("Zero cos-graph plugins collected; exiting non-zero.")
        return 1

    existing = load_index(args.output)
    merged = merge_into_index(existing, fresh)
    save_index(merged, args.output)
    logger.info(
        "Synced %d cos-graph plugin(s) into %s (total entries now %d)",
        len(fresh),
        args.output,
        len(merged),
    )

    if args.overlay_catalog_index:
        top = load_index(args.catalog_index)
        if not top:
            logger.error(
                "Top-level catalog index %s is empty/missing — cannot overlay.",
                args.catalog_index,
            )
            return 1
        # Preserve the huge top-level index's existing order; only the cos-graph
        # entries move/append → small, reviewable diff per re-sync.
        top_merged = merge_into_index(top, fresh, sort=False)
        save_index(top_merged, args.catalog_index)
        logger.info(
            "Overlaid %d cos-graph plugin(s) into %s (total entries now %d, "
            "other entries' enrichment preserved)",
            len(fresh),
            args.catalog_index,
            len(top_merged),
        )
    for e in fresh:
        logger.info(
            "  %s  (skills=%d agents=%d, score=%d, source_url=%s)",
            e["id"],
            e["bundle"]["skills_count"],
            e["bundle"]["agents_count"],
            e["final_score"],
            e["source_url"],
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
