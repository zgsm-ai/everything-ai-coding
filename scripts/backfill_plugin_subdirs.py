#!/usr/bin/env python3
"""Backfill subdirectory source_urls for monorepo plugins.

``sync_plugins_dev.py`` sets ``source_url`` to the repo root for every plugin,
ignoring the per-plugin ``source`` subdirectory declared in the repo's
``.claude-plugin/marketplace.json``. For multi-plugin monorepos (ruvnet/ruflo
has 33, wshobson/agents 84, …) this makes every entry point at the whole
monorepo, so the marketplace build re-bundles the entire repo once per plugin
(e.g. 33 × 17 MB ≈ 561 MB just for ruflo). ``sync_plugins_official.py`` already
resolves these subdirs correctly; this script applies the same resolution as a
catalog-wide backfill so dev-synced entries match.

For each plugin entry whose ``source_url`` is a bare repo root, we fetch the
repo's ``.claude-plugin/marketplace.json``, find the plugin by name, and rewrite
``source_url`` to ``.../tree/<branch>/<subdir>`` when the marketplace declares a
subdirectory ``source``. Entries already carrying a ``/tree/`` subdir (e.g.
official) or whose repo has no marketplace.json / a root ``.`` source are left
untouched. Idempotent — safe to run as a sync.yml step.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from .utils import load_index, save_index  # type: ignore
    from .sync_plugins_official import _http_get_json, _resolve_source_url  # type: ignore
except ImportError:  # pragma: no cover - script-style invocation
    from utils import load_index, save_index  # type: ignore
    from sync_plugins_official import _http_get_json, _resolve_source_url  # type: ignore

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
PLUGINS_INDEX = os.path.join(REPO_ROOT, "catalog", "plugins", "index.json")
TOP_INDEX = os.path.join(REPO_ROOT, "catalog", "index.json")

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("backfill_plugin_subdirs")

# repo_slug -> (plugins_by_name: dict, branch: str) | None  (None = no marketplace.json)
_repo_cache: dict = {}


def _load_marketplace(repo_slug: str):
    """Fetch <repo>/.claude-plugin/marketplace.json, trying main then master.

    Returns (name->plugin_entry dict, branch) or None when absent.
    """
    if repo_slug in _repo_cache:
        return _repo_cache[repo_slug]
    result = None
    for branch in ("main", "master"):
        url = f"https://raw.githubusercontent.com/{repo_slug}/{branch}/.claude-plugin/marketplace.json"
        data = _http_get_json(url)
        if isinstance(data, dict) and isinstance(data.get("plugins"), list):
            by_name = {}
            for p in data["plugins"]:
                if isinstance(p, dict) and p.get("name"):
                    by_name[str(p["name"]).strip().lower()] = p
            result = (by_name, branch)
            break
    _repo_cache[repo_slug] = result
    return result


def _resolved_subdir_url(entry: dict) -> str | None:
    """Return a corrected subdir source_url for `entry`, or None to leave as-is.

    Always re-resolves from the repo's marketplace.json so a previously
    mis-resolved subdir (e.g. a dropped hidden-dir dot) self-corrects on re-run;
    only returns a value when the freshly-resolved subdir URL actually differs.
    """
    src_url = entry.get("source_url") or ""
    install = entry.get("install", {})
    repo_slug = install.get("marketplace_repo")
    if not repo_slug:
        return None
    mp = _load_marketplace(repo_slug)
    if not mp:
        return None
    by_name, branch = mp
    key = str(install.get("plugin_name") or entry.get("name") or "").strip().lower()
    mp_entry = by_name.get(key)
    if not mp_entry:
        return None
    new_url = _resolve_source_url(mp_entry, repo_slug, branch)
    # Only rewrite when resolution points into a subdirectory and changed.
    if "/tree/" in new_url and new_url != src_url:
        return new_url
    return None


def backfill(plugins_path: str, top_path: str) -> int:
    plugins = load_index(plugins_path)
    changes: dict[str, str] = {}  # id -> new source_url
    for e in plugins:
        if e.get("type") != "plugin":
            continue
        new_url = _resolved_subdir_url(e)
        if new_url:
            changes[e.get("id", "")] = new_url
            e["source_url"] = new_url

    if not changes:
        logger.info("No monorepo source_urls needed backfilling.")
        return 0

    save_index(plugins, plugins_path)
    logger.info("Rewrote %d plugin source_urls in %s", len(changes), plugins_path)

    # Apply the same source_url corrections to the top-level catalog/index.json
    # (the bundle + marketplace build read it). Surgical: only source_url changes.
    if os.path.exists(top_path):
        top = load_index(top_path)
        applied = 0
        for e in top:
            nu = changes.get(e.get("id", ""))
            if nu and e.get("source_url") != nu:
                e["source_url"] = nu
                applied += 1
        save_index(top, top_path)
        logger.info("Applied %d corrections to %s", applied, top_path)

    # Report the worst offenders for visibility.
    by_repo: dict[str, int] = {}
    for e in plugins:
        if e.get("id") in changes:
            repo = e.get("install", {}).get("marketplace_repo", "?")
            by_repo[repo] = by_repo.get(repo, 0) + 1
    for repo, n in sorted(by_repo.items(), key=lambda x: -x[1])[:10]:
        logger.info("  %3d plugins → subdirs under %s", n, repo)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Backfill monorepo plugin subdir source_urls.")
    p.add_argument("--plugins-index", default=PLUGINS_INDEX)
    p.add_argument("--top-index", default=TOP_INDEX)
    args = p.parse_args(argv)
    return backfill(args.plugins_index, args.top_index)


if __name__ == "__main__":
    sys.exit(main())
