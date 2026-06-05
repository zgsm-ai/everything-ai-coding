#!/usr/bin/env python3
"""First-party cospowers plugin sync (yhangf/csc-plugins).

Pulls the cospowers plugin family out of the monorepo
``https://github.com/yhangf/csc-plugins`` and merges them into
``catalog/plugins/index.json`` as **first-party, marketplace-verified** plugin
entries so they flow through the canonical pipeline:

    catalog/plugins/index.json
      → merge_index.py        → catalog/index.json
      → download_catalog.py   → catalog-download/plugins/<id>/.plugin.json
      → build_catalog_bundle  → catalog-bundle.tar.gz
      → costrict-plugin-marketplace build.py --publish
                              → costrict-plugins-repo/<id>.git + marketplace.git
      → costrict-web migrate ingest-upstream
                              → capability_items (web hub)

Why a dedicated script instead of adding csc-plugins to ``sync_plugins_official``:

  - csc-plugins has **no repo-root** ``.claude-plugin/marketplace.json`` — each of
    the 6 plugins lives in its own top-level subdir with its own per-plugin
    ``plugin.json`` + ``marketplace.json``. The official sync expects a single
    root marketplace.json listing all plugins; this layout doesn't fit.
  - These are *our own* (Sangfor / cospowers) plugins: they get a fixed
    ``marketplace_verified=true`` and a fixed perfect ``final_score`` rather
    than going through the upstream ai-resource-eval scoring pipeline.

Idempotency / "manual re-sync": this script **merge-preserves** —
it loads the existing ``catalog/plugins/index.json``, drops any prior entries it
owns (``source == "csc-plugins"``), re-derives the 6 entries from the *live*
csc-plugins tree (so version / description / bundle-count changes are picked up),
and writes the union back. Re-running it == syncing the latest csc-plugins.

Run order: must run **after** ``sync_plugins_official.py`` (which overwrites the
whole index) and may run before/after ``sync_plugins_dev.py`` (both
merge-preserve). See ``.github/workflows/sync.yml`` / ``sync-csc-plugins.yml``.

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

# Allow running both as `python scripts/sync_plugins_csc.py` and as a module.
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
SOURCE_ID = "csc-plugins"
SOURCE_PRIORITY = 1000

CSC_REPO = "yhangf/csc-plugins"          # <owner>/<repo> — build/content source (not user-facing)
CSC_BRANCH = "main"

# User-facing home: each cospowers plugin is published as its own standard repo
# under our org, which is what `csc plugin install <name>@costrict-plugins`
# actually clones. install.marketplace_repo points here so the web hub's
# "Upstream Source" link shows our repo, not the non-standard yhangf monorepo.
# (source_url stays on CSC_REPO — it's the build clone source and is never
# returned to the hub UI.)
COSTRICT_ORG = "costrict-plugins-repo"

# Self-own: first-party plugins get a fixed perfect score instead of the
# upstream ai-resource-eval pipeline. 0-100 scale (web ingest maps
# final_score -> capability_items.experience_score verbatim).
FINAL_SCORE = 100

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
USER_AGENT = "everything-ai-coding-plugins-sync"

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("sync_plugins_csc")


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
    """Fetch stars + pushed_at for the monorepo (shared by all 6 plugins)."""
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
        "mcp_servers_count": 0,
        "skills_namespaces": [],
        "hooks_count": 0,
        "hook_events": [],
        "mcp_server_names": [],
        "is_marketplace_repo": False,
    }


def compute_bundle(tree_paths: list[str], subdir: str, plugin_name: str) -> dict:
    """Derive bundle counts for one plugin subdir from the repo tree.

    - skills:   `<subdir>/skills/<name>/SKILL.md`  → count + `<plugin>:<name>` namespaces
    - commands: `<subdir>/commands/<file>`         → count
    - agents:   `<subdir>/agents/<file>.md`        → count
    """
    bundle = _empty_bundle()
    skill_names: list[str] = []
    command_files: set[str] = set()
    agent_files: set[str] = set()
    skills_prefix = f"{subdir}/skills/"
    commands_prefix = f"{subdir}/commands/"
    agents_prefix = f"{subdir}/agents/"

    for path in tree_paths:
        if path.startswith(skills_prefix) and path.endswith("/SKILL.md"):
            rel = path[len(skills_prefix):]
            name = rel.split("/", 1)[0]
            if name:
                skill_names.append(name)
        elif path.startswith(commands_prefix):
            rel = path[len(commands_prefix):]
            top = rel.split("/", 1)[0]
            if top:
                command_files.add(top)
        elif path.startswith(agents_prefix) and path.endswith(".md"):
            rel = path[len(agents_prefix):]
            top = rel.split("/", 1)[0]
            if top:
                agent_files.add(top)

    skill_names = sorted(set(skill_names))
    bundle["skills_count"] = len(skill_names)
    bundle["skills_namespaces"] = [f"{plugin_name}:{s}" for s in skill_names]
    bundle["commands_count"] = len(command_files)
    bundle["agents_count"] = len(agent_files)
    return bundle


# ---------------------------------------------------------------------------
# Per-plugin entry construction
# ---------------------------------------------------------------------------

def build_entry(
    subdir: str,
    tree_paths: list[str],
    repo_meta: dict,
    last_synced_iso: str,
) -> Optional[dict]:
    """Build a catalog entry for one cospowers plugin subdir.

    Reads the subdir's `plugin.json` (canonical name/description/version) and
    `marketplace.json` (marketplace_name). Returns None if plugin.json is
    unreadable or nameless.
    """
    plugin_json = _http_get_json(
        _raw_url(CSC_REPO, CSC_BRANCH, f"{subdir}/.claude-plugin/plugin.json")
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
        _raw_url(CSC_REPO, CSC_BRANCH, f"{subdir}/.claude-plugin/marketplace.json")
    )
    marketplace_name = None
    if isinstance(marketplace_json, dict):
        marketplace_name = (marketplace_json.get("name") or "").strip() or None
    # download_catalog._download_plugin requires marketplace_name; fall back to
    # the plugin name so the gate never trips for a first-party plugin.
    if not marketplace_name:
        marketplace_name = name

    # id == plugin name: clean first-party marketplace repo names
    # (costrict-plugins-repo/cospowers-requirements.git) and the same token the
    # user types in `csc plugin install <name>@costrict-plugins`. The cospowers-
    # prefix already guarantees catalog-wide uniqueness.
    plugin_id = name

    source_url = f"https://github.com/{CSC_REPO}/tree/{CSC_BRANCH}/{subdir}"
    tags = ["cospowers", "ai-workers"] + extract_tags(name, description)
    seen: set[str] = set()
    tags = [t for t in tags if not (t in seen or seen.add(t))]
    category = categorize(name=name, description=description, tags=tags)

    bundle = compute_bundle(tree_paths, subdir, name)

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
            # non-standard yhangf monorepo out of the hub's Upstream Source link.
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
    }


# ---------------------------------------------------------------------------
# Merge-preserve into catalog/plugins/index.json
# ---------------------------------------------------------------------------

def merge_into_index(existing: list[dict], fresh: list[dict], sort: bool = True) -> list[dict]:
    """Replace all prior `source == SOURCE_ID` entries with `fresh`, keep rest.

    sort=True  → sort by id (readable diffs for the small per-type index).
    sort=False → preserve the existing entries' order and append `fresh` at the
                 end. Used for the 33MB top-level catalog/index.json so a re-sync
                 produces a ~6-entry diff instead of re-sorting the whole file.
    """
    kept = [e for e in existing if e.get("source") != SOURCE_ID]
    merged = kept + fresh
    if sort:
        merged.sort(key=lambda e: e.get("id", ""))
    return merged


def collect_entries() -> list[dict]:
    """Fetch the live csc-plugins tree and build all cospowers entries."""
    last_synced_iso = date.today().isoformat()
    repo_meta = fetch_repo_meta(CSC_REPO)
    tree_paths = fetch_tree_paths(CSC_REPO, CSC_BRANCH)
    if not tree_paths:
        logger.error("Empty/failed git tree for %s@%s — aborting", CSC_REPO, CSC_BRANCH)
        return []
    subdirs = discover_plugin_subdirs(tree_paths)
    logger.info("Discovered %d plugin subdir(s): %s", len(subdirs), ", ".join(subdirs))

    entries: list[dict] = []
    for subdir in subdirs:
        try:
            entry = build_entry(subdir, tree_paths, repo_meta, last_synced_iso)
        except Exception as e:  # noqa: BLE001 - never let one plugin kill the run
            logger.warning("Failed to build entry for %s: %s", subdir, e)
            continue
        if entry is not None:
            entries.append(entry)
    return entries


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sync yhangf/csc-plugins (cospowers) into catalog/plugins/index.json.",
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
            "Also surgically overlay the 6 entries into the top-level "
            "catalog/index.json (drop prior source=csc-plugins, append fresh), "
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
    args = parser.parse_args(argv)

    fresh = collect_entries()
    if not fresh:
        logger.error("Zero cospowers plugins collected; exiting non-zero.")
        return 1

    existing = load_index(args.output)
    merged = merge_into_index(existing, fresh)
    save_index(merged, args.output)
    logger.info(
        "Synced %d cospowers plugin(s) into %s (total entries now %d)",
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
        # Preserve the huge top-level index's existing order; only the 6 csc
        # entries move/append → small, reviewable diff per re-sync.
        top_merged = merge_into_index(top, fresh, sort=False)
        save_index(top_merged, args.catalog_index)
        logger.info(
            "Overlaid %d cospowers plugin(s) into %s (total entries now %d, "
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
