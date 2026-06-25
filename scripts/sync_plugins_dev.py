#!/usr/bin/env python3
"""claude-plugins.dev community registry sync (Tasks 7.2–7.5).

Fetches the public claude-plugins.dev API
(``https://claude-plugins.dev/api/plugins?limit=200&offset=N``), filters out
plugins with fewer than 5 stars, and merges results into
``catalog/plugins/index.json`` while preserving any entries previously written
by ``sync_plugins_official.py`` (official entries always win on
``source_url`` collision because they have a higher ``source_priority``).

Per-task mapping:

  * 7.2 — Paginated fetch loop (``offset += 200``) with a defensive page cap;
          plugins below the star threshold are dropped.
  * 7.3 — Source-aware dedup against the existing on-disk index by normalized
          ``source_url``; existing entries (e.g. official marketplaces) are
          kept verbatim, so this script only ever adds claude-plugins.dev
          entries that are not already represented by a higher-priority source.
  * 7.4 — Every emitted entry carries ``source_priority = 700`` and
          ``source = "claude-plugins-dev"``; the eval pipeline maps that
          ``source`` to ``source_trust`` base ``70`` separately.
  * 7.5 — Failure isolation: network / parse / unexpected errors log a
          WARNING/ERROR, persist whatever has been collected so far, and
          exit ``0``. The CI pipeline must continue to the next stage even
          when this registry is unreachable.

Implementation notes:
  * Standard library only (``urllib`` + ``json``) — matches the conventions of
    ``sync_plugins_official.py`` / ``sync_skills_sh.py``.
  * Honors ``GITHUB_TOKEN`` only when the API host is on GitHub; the
    claude-plugins.dev endpoint itself is anonymous.
  * Persists each successful page to a local fallback cache
    (``.plugins_dev_cache/``) so a transient outage doesn't lose progress
    between CI runs (mirrors the cache pattern used by ``sync_skills_sh.py``).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from typing import Optional

# Allow running both as `python scripts/sync_plugins_dev.py` and as a module.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from .utils import (  # type: ignore
        _normalize_plugin_url,
        categorize,
        extract_tags,
        is_plugin_source,
        is_plugin_blacklisted,
        load_index,
        load_plugin_blacklist,
        save_index,
    )
    from . import marketplace_verifier  # type: ignore
except ImportError:  # pragma: no cover - script-style invocation
    from utils import (  # type: ignore
        _normalize_plugin_url,
        categorize,
        extract_tags,
        is_plugin_source,
        is_plugin_blacklisted,
        load_index,
        load_plugin_blacklist,
        save_index,
    )
    import marketplace_verifier  # type: ignore

try:
    from ai_resource_eval.fetcher import PluginContentFetcher  # type: ignore
except Exception:  # noqa: BLE001 - keep sync resilient if package missing
    PluginContentFetcher = None  # type: ignore


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
OUTPUT_PATH = os.path.join(REPO_ROOT, "catalog", "plugins", "index.json")
CACHE_DIR = os.path.join(REPO_ROOT, ".plugins_dev_cache")
MARKETPLACE_CACHE_PATH = os.path.join(CACHE_DIR, "marketplace_manifests.json")

API_BASE = "https://claude-plugins.dev/api/plugins"
# Requested page size. The upstream API currently caps responses at 100
# regardless of what we ask for (verified empirically: ``limit=200`` returns
# ``"limit": 100`` and 100 plugins). We still ask for 200 in case the cap is
# raised later, and rely on the server's actual returned limit (echoed in the
# response body as ``limit``) to drive the offset increment.
PAGE_SIZE = 200
SERVER_LIMIT_FALLBACK = 100  # observed cap as of the SPIKE (task 7.1)
DEFAULT_MAX_PAGES = 200  # Safety cap → up to 20,000 plugins at 100/page.
# 实测：API 把热门 plugin 都塞前 ~100 页，stars≥5000 的 plugin 全部位于前 100 页内。
# max_pages=200 留缓冲，未来高星新 plugin 不会漏；继续提高对收录无增益（后段都是 stars<5）。
MIN_STARS = 5000
# 实测全量 stars 分布：≥5 共 11,369 / ≥1000 共 1,573 / ≥3000 共 823 / ≥5000 共 711。
# 目标"~1000 条最终入选"，stars≥5000 + official 190 = 901 条（下限）。
# 提高阈值是质量门槛：一个 plugin 装载的 marketplace repo 至少 5k 星才算头部精选。

SOURCE_ID = "claude-plugins-dev"
SOURCE_PRIORITY = 700

USER_AGENT = "everything-ai-coding-plugins-dev-sync"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()

# manifest_completeness scoring (mirrors sync_plugins_official.py).
MANIFEST_FULL_FIELDS = ("name", "version", "description", "author")
MANIFEST_COMPLETENESS_FULL = 1.0
MANIFEST_COMPLETENESS_PARTIAL = 0.7
MANIFEST_COMPLETENESS_NONE = 0.3


logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("sync_plugins_dev")


# ---------------------------------------------------------------------------
# HTTP helpers (stdlib only)
# ---------------------------------------------------------------------------

def _http_get_json(url: str, timeout: int = 30) -> Optional[dict]:
    """GET ``url`` and return decoded JSON, or ``None`` on any failure.

    Errors are logged at WARNING level so the caller can decide whether to
    stop pagination or continue. We never raise — task 7.5 mandates that
    CI must not be blocked by this script.
    """
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if GITHUB_TOKEN and "github.com" in url:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
    except urllib.error.HTTPError as e:
        logger.warning("HTTP %s for %s: %s", e.code, url, e.reason)
        return None
    except (urllib.error.URLError, TimeoutError) as e:
        logger.warning("Network error for %s: %s", url, e)
        return None
    except Exception as e:  # noqa: BLE001 - keep the script robust
        logger.warning("Unexpected error fetching %s: %s", url, e)
        return None

    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        logger.warning("JSON decode error for %s: %s", url, e)
        return None

    if not isinstance(data, dict):
        logger.warning("Unexpected JSON shape for %s: top-level is %s",
                       url, type(data).__name__)
        return None
    return data


# ---------------------------------------------------------------------------
# Slug / id helpers
# ---------------------------------------------------------------------------

_SLUG_RE = re.compile(r"[^a-z0-9-]+")


def _slugify(s: str) -> str:
    s = (s or "").strip().lower()
    # Strip an "@scope/" prefix common in the namespace field.
    if s.startswith("@"):
        s = s[1:]
    s = re.sub(r"[\s_./]+", "-", s)
    s = _SLUG_RE.sub("-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s


def _build_id(namespace: str, name: str) -> str:
    """Stable id of the form ``<slugified-namespace>-<plugin-name>``.

    Falls back to ``claude-plugins-dev-<name>`` when no namespace is set,
    to keep the ``id`` namespace distinct from the official-marketplace
    prefixes (``anthropic-...`` / ``obra-...``).
    """
    ns_slug = _slugify(namespace)
    nm_slug = _slugify(name) or "plugin"
    if not ns_slug:
        ns_slug = SOURCE_ID
    if ns_slug == nm_slug:
        return ns_slug
    return f"{ns_slug}-{nm_slug}"


# ---------------------------------------------------------------------------
# manifest_completeness (lightweight — derived from the API payload alone,
# we don't fetch the per-plugin plugin.json since claude-plugins.dev already
# normalizes the upstream metadata).
# ---------------------------------------------------------------------------

def _compute_manifest_completeness(plugin: dict) -> float:
    def _present(key: str) -> bool:
        v = plugin.get(key)
        if v is None:
            return False
        if isinstance(v, str):
            return v.strip() != ""
        if isinstance(v, (list, dict)):
            return len(v) > 0
        return True

    have = [_present(k) for k in MANIFEST_FULL_FIELDS]
    if all(have):
        return MANIFEST_COMPLETENESS_FULL
    if any(have):
        return MANIFEST_COMPLETENESS_PARTIAL
    return MANIFEST_COMPLETENESS_NONE


# ---------------------------------------------------------------------------
# Per-plugin entry construction
# ---------------------------------------------------------------------------

def _normalize_pushed_at(value) -> Optional[str]:
    """dev API 的 updatedAt 形态多变（空格分隔 / 已带 Z / null），统一成 ISO 8601 带 Z。

    runner._compute_freshness 会做 ``.replace("Z", "+00:00")``，所以只要返回
    形如 ``2026-02-08T01:48:36Z`` 即可。失败时返回 None（freshness 信号自动
    走 excluded 路径）。
    """
    if not value or not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    # 把空格分隔形态（"2026-02-08 01:48:36"）转成 T 分隔；保留已经是 ISO 的。
    if " " in s and "T" not in s:
        s = s.replace(" ", "T", 1)
    if not s.endswith("Z") and "+" not in s and "T" in s:
        s = s + "Z"
    return s


def _parse_git_url_for_layout(git_url: str) -> Optional[tuple[str, str, str]]:
    """Extract ``(repo, ref, plugin_root)`` from the dev API's ``gitUrl`` field.

    Most ``gitUrl`` values look like ``https://github.com/owner/repo`` (root
    plugin); some include a ``/tree/<ref>/<sub>`` segment for monorepo
    sub-paths. Non-GitHub values return ``None``.
    """
    if not isinstance(git_url, str) or not git_url:
        return None
    m = re.match(
        r"https?://github\.com/([^/]+)/([^/?#.]+?)(?:\.git)?"
        r"(?:/(?:tree|blob)/([^/]+)(?:/(.+))?)?(?:[/?#]|$)",
        git_url,
    )
    if not m:
        return None
    owner, repo = m.group(1), m.group(2)
    ref = (m.group(3) or "HEAD").strip() or "HEAD"
    sub = (m.group(4) or "").strip("/")
    return (f"{owner}/{repo}", ref, sub)


def _build_bundle_from_layout_dev(
    fetcher,
    git_url: str,
    api_skills: list,
    plugin_name: str,
) -> dict:
    """Layout-detector-first bundle builder; trust API skills only as fallback.

    The dev API's ``skills`` array is a coarse hint (often missing commands /
    agents and sometimes stale on skill counts). When the layout detector
    succeeds we use its counts as the source of truth. When the detector hits
    a Tree API failure we keep zeros (no false-positive bundles). Only the
    legitimate "no plugin.json" path falls back to the API hint (Task 4.2).
    """
    fallback_namespaces = [
        f"{plugin_name}:{s}" for s in api_skills if isinstance(s, str) and s
    ]
    # New extension fields default to empty/zero everywhere — populated only
    # by the layout-detector branch below.
    _extension_defaults = {
        "hooks_count": 0,
        "hook_events": [],
        "mcp_server_names": [],
        "is_marketplace_repo": False,
    }
    fallback_bundle = {
        "skills_count": len(fallback_namespaces),
        "commands_count": 0,
        "agents_count": 0,
        "mcp_servers_count": 0,
        "skills_namespaces": fallback_namespaces,
        **_extension_defaults,
        "mcp_server_configs": {},
    }
    zero_bundle = {
        "skills_count": 0,
        "commands_count": 0,
        "agents_count": 0,
        "mcp_servers_count": 0,
        "skills_namespaces": [],
        **_extension_defaults,
        "mcp_server_configs": {},
    }

    if fetcher is None:
        return fallback_bundle

    target = _parse_git_url_for_layout(git_url)
    if target is None:
        return fallback_bundle
    repo, ref, plugin_root = target

    try:
        layout = fetcher.detect_plugin_layout(repo, plugin_root, ref=ref)
    except Exception as e:  # noqa: BLE001 - Task 4.4: never block sync.
        logger.warning(
            "detect_plugin_layout failed for %s/%s@%s (plugin=%s): %s",
            repo, plugin_root or "<root>", ref, plugin_name, e,
        )
        return zero_bundle

    if layout.is_plugin:
        # Marketplace shell — return zeroed bundle plus the marker. Caller
        # SHALL skip writing an entry for the marketplace itself.
        if getattr(layout, "is_marketplace_repo", False):
            marketplace_bundle = dict(zero_bundle)
            marketplace_bundle["is_marketplace_repo"] = True
            return marketplace_bundle
        return {
            "skills_count": len(layout.skill_paths),
            "commands_count": len(layout.command_paths),
            "agents_count": len(layout.agent_paths),
            "mcp_servers_count": len(layout.mcp_server_names),
            "skills_namespaces": list(layout.skills_namespaces),
            # Repo-relative SKILL.md paths (position-aligned with
            # skills_namespaces) + source coordinates, carried through so
            # merge_index can synthesize standalone skill entries for orphan
            # sub-skills. See sync_plugins_official._build_bundle_from_layout.
            "skill_paths": list(layout.skill_paths),
            "source_repo": repo,
            "source_ref": ref,
            "plugin_root": layout.plugin_root,
            "plugin_json_path": layout.plugin_json_path,
            "hooks_count": layout.hooks_count,
            "hook_events": list(layout.hook_events),
            "mcp_server_names": list(layout.mcp_server_names),
            "mcp_server_configs": dict(getattr(layout, "mcp_server_configs", {}) or {}),
            "is_marketplace_repo": False,
        }

    if layout.fetch_error is not None:
        # Transient Tree API failure — don't publish API-hint bundles that may
        # contradict reality. Next sync will retry.
        logger.warning(
            "Tree API failure for %s/%s@%s (plugin=%s): %s. "
            "Keeping zero bundle for retry.",
            repo, plugin_root or "<root>", ref, plugin_name, layout.fetch_error,
        )
        return zero_bundle

    # Legitimate "no plugin.json": the layout detector ran cleanly (no Tree API
    # error) and found no .claude-plugin/plugin.json anywhere in the repo. The
    # dev registry lists it as a "plugin", but with no installable manifest the
    # downstream marketplace build (build.py) marks it invalid — it would become
    # a phantom catalog entry: visible in the store, un-installable from the
    # marketplace mirror. Mark it so the caller drops the entry entirely.
    return {**fallback_bundle, "no_plugin_manifest": True}


def _entry_from_plugin(
    plugin: dict,
    last_synced_iso: str,
    layout_fetcher=None,
    plugin_blacklist: Optional[list] = None,
    marketplace_cache: Optional[dict] = None,
) -> Optional[dict]:
    """Convert one claude-plugins.dev API plugin into a catalog entry.

    Returns ``None`` if the plugin is too malformed (missing name), below
    the star threshold to be useful, or matches the plugin-level blacklist
    from ``plugin_sources.json`` — callers filter on the return value.
    """
    name = (plugin.get("name") or "").strip()
    if not name:
        logger.debug("Skipping plugin without name: %r", plugin)
        return None

    if is_plugin_blacklisted(SOURCE_ID, name, plugin_blacklist):
        logger.debug(
            "Skipping plugin (source=%s, name=%s): in plugin_sources.json "
            "plugins blacklist",
            SOURCE_ID,
            name,
        )
        return None

    description = (plugin.get("description") or "").strip()
    namespace = (plugin.get("namespace") or "").strip()
    git_url = (plugin.get("gitUrl") or "").strip().rstrip("/")
    if git_url.endswith(".git"):
        # Keep the .git suffix off the catalog source_url for consistency
        # with the existing official entries, which mostly point at HTML
        # repo URLs (a few do retain `.git` — we leave those as-is in the
        # existing index and only normalize newly-added ones here).
        pass  # Intentional no-op; preserve as-is to maximize dedup.
    if is_plugin_source(git_url):
        logger.info(
            "Skipping plugin source repo %s (plugin=%s): represented by "
            "plugin marketplace sync.",
            git_url, name,
        )
        return None
    version = (plugin.get("version") or "").strip()
    upstream_keywords = plugin.get("keywords")
    if not isinstance(upstream_keywords, list):
        upstream_keywords = []
    upstream_category = (plugin.get("category") or "").strip()
    skills_arr = plugin.get("skills")
    if not isinstance(skills_arr, list):
        skills_arr = []
    stars = plugin.get("stars")
    try:
        stars_int = int(stars) if stars is not None else None
    except (TypeError, ValueError):
        stars_int = None

    # Tags: keep upstream keywords, then derive from name/description.
    derived = extract_tags(name, description)
    tags: list[str] = []
    seen: set[str] = set()
    for t in list(upstream_keywords) + derived:
        if not isinstance(t, str):
            continue
        tl = t.strip().lower()
        if tl and tl not in seen:
            seen.add(tl)
            tags.append(tl)

    category = categorize(
        name=name,
        description=description,
        tags=tags,
        upstream_category=upstream_category,
    )

    bundle = _build_bundle_from_layout_dev(
        layout_fetcher, git_url, skills_arr, name
    )

    # Marketplace shell — skip writing this as a plugin entry. Nested plugins
    # under the same repo (if any) are surfaced via separate upstream feed
    # entries, not by enumerating from this row.
    if bundle.get("is_marketplace_repo"):
        logger.info(
            "Skipping marketplace shell %s (plugin=%s) — nested plugins must "
            "come through separate upstream entries.",
            git_url, name,
        )
        return None

    # No .claude-plugin/plugin.json anywhere in the repo — the layout detector
    # confirmed this (distinct from a transient Tree API failure, which keeps a
    # zero bundle for retry). The dev registry lists it as a "plugin", but it
    # has no installable manifest, so it cannot be served by the marketplace
    # mirror. Emitting it would create a phantom entry (visible in the store,
    # un-installable). Drop it; skills shipped by such repos belong in the
    # skills catalog, not here.
    if bundle.get("no_plugin_manifest"):
        logger.info(
            "Skipping plugin %s (plugin=%s): no .claude-plugin/plugin.json in "
            "repo — not an installable plugin.",
            git_url, name,
        )
        return None

    completeness = _compute_manifest_completeness(plugin)

    # Reverse-engineer marketplace_repo from gitUrl (canonical GitHub slug).
    # Falls back to None when source_url isn't a parseable GitHub URL — the
    # entry is still written, but with marketplace_verified=False.
    parsed_layout = _parse_git_url_for_layout(git_url)
    marketplace_repo = parsed_layout[0] if parsed_layout else None

    # When marketplace_cache is None the caller opted out of marketplace
    # verification entirely (e.g., unit tests that mock just the registry
    # layer). Skip the verifier — the resulting entry will have
    # marketplace_verified=False, which downstream treats as "needs catalog
    # refresh / unverified" exactly like a real fetch failure.
    if marketplace_cache is not None and marketplace_repo:
        marketplace_name, marketplace_verified = marketplace_verifier.verify_marketplace(
            marketplace_repo, name, marketplace_cache,
        )
    else:
        marketplace_name, marketplace_verified = (None, False)

    entry: dict = {
        "id": _build_id(namespace, name),
        "name": name,
        "type": "plugin",
        "description": description,
        "source_url": git_url,
        "category": category,
        "tags": tags,
        "tech_stack": [],
        "source": SOURCE_ID,
        "source_priority": SOURCE_PRIORITY,
        # claude-plugins.dev is a community registry, not a marketplace
        # endpoint that ships an installable manifest of its own.
        "marketplace_url": None,
        "platforms": ["claude-code"],
        "install": {
            "method": "plugin_marketplace",
            "plugin_name": name,
            "marketplace_repo": marketplace_repo,
            "marketplace_name": marketplace_name,
            "marketplace_verified": marketplace_verified,
            # Preserved as display-only string (npm-style namespace from upstream).
            "marketplace": namespace or "",
        },
        "bundle": bundle,
        "manifest_completeness": completeness,
        "last_synced": last_synced_iso,
        "stars": stars_int,
        "pushed_at": _normalize_pushed_at(plugin.get("updatedAt")),
        "version": version,
        # Extra signals useful for downstream health/popularity ranking.
        # Intentionally additive — schema in catalog/plugins/index.json
        # tolerates extra keys (existing official entries never set them).
        "downloads": plugin.get("downloads"),
        "verified": bool(plugin.get("verified", False)),
    }
    return entry


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

def _page_url(offset: int, limit: int = PAGE_SIZE) -> str:
    qs = urllib.parse.urlencode({"limit": limit, "offset": offset})
    return f"{API_BASE}?{qs}"


def fetch_all_plugins(max_pages: int = DEFAULT_MAX_PAGES) -> list[dict]:
    """Walk the claude-plugins.dev pagination until exhausted or capped.

    Returns the raw list of plugin dicts that pass the star threshold.
    Logs and stops gracefully on any page failure — the partial list
    collected so far is still returned.
    """
    collected: list[dict] = []
    seen_ids: set[str] = set()
    offset = 0
    pages = 0
    expected_total: Optional[int] = None
    # Effective page size — starts at our request, then is overridden by
    # whatever the server actually returns (the upstream API caps at 100).
    effective_limit = PAGE_SIZE

    while pages < max_pages:
        url = _page_url(offset, limit=PAGE_SIZE)
        logger.info("Fetching page %d (offset=%d): %s", pages + 1, offset, url)
        data = _http_get_json(url)
        if data is None:
            logger.warning(
                "Aborting pagination after %d pages due to fetch error", pages
            )
            break

        plugins = data.get("plugins")
        if not isinstance(plugins, list):
            logger.warning(
                "Page %d returned no `plugins` array (got %s); stopping",
                pages + 1, type(plugins).__name__,
            )
            break

        if expected_total is None:
            t = data.get("total")
            if isinstance(t, int):
                expected_total = t

        # Honor the server-reported limit (it caps at 100 today). Fall back
        # to the SPIKE-observed value if the field is missing/zero.
        server_limit = data.get("limit")
        if isinstance(server_limit, int) and server_limit > 0:
            effective_limit = server_limit
        elif effective_limit == PAGE_SIZE:
            effective_limit = SERVER_LIMIT_FALLBACK

        kept_this_page = 0
        for raw in plugins:
            if not isinstance(raw, dict):
                continue
            stars = raw.get("stars")
            try:
                stars_int = int(stars) if stars is not None else 0
            except (TypeError, ValueError):
                stars_int = 0
            if stars_int < MIN_STARS:
                continue
            # Defensive de-dup against API-side duplicates by plugin uuid /
            # namespace+name. Note: many distinct plugins share the same
            # ``gitUrl`` (different plugins inside one monorepo), so we
            # MUST NOT dedup on gitUrl here — that's done at merge time
            # only against the existing official-marketplace index.
            uid = raw.get("id") or f"{raw.get('namespace')}::{raw.get('name')}"
            if uid in seen_ids:
                continue
            seen_ids.add(uid)
            collected.append(raw)
            kept_this_page += 1

        logger.info(
            "Page %d: %d plugins received (server limit=%d), %d kept "
            "(stars>=%d) — running total=%d",
            pages + 1, len(plugins), effective_limit, kept_this_page,
            MIN_STARS, len(collected),
        )

        # Persist this page to the on-disk fallback cache so a later page
        # failure doesn't lose progress (mirrors sync_skills_sh.py).
        _write_page_cache(pages + 1, plugins)

        # Stop conditions: short page → registry exhausted.
        if len(plugins) < effective_limit:
            logger.info("Short page received (%d < %d); reached end of registry",
                        len(plugins), effective_limit)
            break

        offset += effective_limit
        pages += 1

    if pages >= max_pages:
        logger.warning(
            "Hit max_pages=%d cap; stopping (offset=%d, expected_total=%s)",
            max_pages, offset, expected_total,
        )

    if expected_total is not None:
        logger.info(
            "Pagination complete: collected=%d, registry total=%s",
            len(collected), expected_total,
        )
    return collected


def _write_page_cache(page_num: int, plugins: list) -> None:
    """Best-effort cache write; never fails the sync."""
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        path = os.path.join(CACHE_DIR, f"page_{page_num:04d}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(plugins, f, ensure_ascii=False)
    except OSError as e:
        logger.debug("Failed to write page cache %d: %s", page_num, e)


# ---------------------------------------------------------------------------
# Merge with existing index (task 7.3 — official entries win)
# ---------------------------------------------------------------------------

def _merge_into_existing(new_entries: list[dict],
                         existing_entries: list[dict]) -> list[dict]:
    """Combine claude-plugins.dev entries with whatever is already on disk.

    Strategy (task 7.3):
      * Build a lookup of existing entries by normalized ``source_url`` —
        these are typically official-marketplace plugins with higher
        ``source_priority`` and must always win on collision.
      * For each new entry:
          - Skip if its normalized ``source_url`` already appears among
            *existing* entries (official wins).
          - Skip if its ``id`` collides with an existing or already-accepted
            entry (id-level dedup, not source_url-level — many distinct
            community plugins legitimately share a ``gitUrl`` because they
            live in the same monorepo).
      * Return ``existing + accepted-new``, sorted by id.
    """
    existing_urls: set[str] = set()
    existing_ids: set[str] = set()
    for e in existing_entries:
        url = e.get("source_url") or ""
        norm = _normalize_plugin_url(url)
        if norm:
            existing_urls.add(norm)
        eid = e.get("id")
        if eid:
            existing_ids.add(eid)

    accepted: list[dict] = []
    skipped_url_collision = 0
    skipped_id_collision = 0
    seen_ids: set[str] = set(existing_ids)
    for e in new_entries:
        url = e.get("source_url") or ""
        norm = _normalize_plugin_url(url)
        if norm and norm in existing_urls:
            # Official marketplace already covers this repo — drop the
            # community-registry duplicate (official has source_priority=1000
            # vs community's 700, so it wins per design.md decision 4).
            skipped_url_collision += 1
            continue
        eid = e.get("id") or ""
        if eid and eid in seen_ids:
            skipped_id_collision += 1
            continue
        if eid:
            seen_ids.add(eid)
        accepted.append(e)

    logger.info(
        "Merge: %d new accepted, %d skipped (source_url already in index "
        "from a higher-priority source), %d skipped (id collision)",
        len(accepted), skipped_url_collision, skipped_id_collision,
    )

    combined = list(existing_entries) + accepted
    combined.sort(key=lambda e: e.get("id", ""))
    return combined


def _prune_existing_plugin_source_entries(
    existing_entries: list[dict],
) -> tuple[list[dict], int]:
    """Drop stale claude-plugins.dev rows now covered by marketplace sync."""
    kept: list[dict] = []
    pruned = 0
    for entry in existing_entries:
        if (
            entry.get("source") == SOURCE_ID
            and is_plugin_source(entry.get("source_url", ""))
        ):
            pruned += 1
            continue
        kept.append(entry)
    return kept, pruned


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _now_iso_date() -> str:
    return date.today().isoformat()


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Sync claude-plugins.dev community registry into "
            "catalog/plugins/index.json (preserves existing entries)."
        ),
    )
    parser.add_argument(
        "--output",
        default=OUTPUT_PATH,
        help=f"Output index.json path (default: {OUTPUT_PATH})",
    )
    parser.add_argument(
        "--limit-pages",
        type=int,
        default=DEFAULT_MAX_PAGES,
        help=(
            f"Max pages to fetch from claude-plugins.dev "
            f"(default: {DEFAULT_MAX_PAGES}, page size: {PAGE_SIZE})."
        ),
    )
    args = parser.parse_args(argv)

    last_synced = _now_iso_date()
    started_at = datetime.now(timezone.utc).isoformat()
    logger.info(
        "Starting claude-plugins.dev sync at %s (max_pages=%d, page_size=%d, "
        "min_stars=%d)",
        started_at, args.limit_pages, PAGE_SIZE, MIN_STARS,
    )

    # 1. Pagination — wrapped so any unexpected exception still leaves the
    #    existing on-disk index untouched and exits 0.
    try:
        raw_plugins = fetch_all_plugins(max_pages=args.limit_pages)
    except Exception as e:  # noqa: BLE001 - task 7.5: never block CI
        logger.error("Unhandled error during pagination: %s", e)
        raw_plugins = []

    if not raw_plugins:
        logger.warning(
            "claude-plugins-dev sync produced 0 entries; leaving "
            "existing %s untouched and exiting 0 (task 7.5).", args.output,
        )
        return 0

    # 2. Convert to catalog entries.
    # One PluginContentFetcher per sync run; instance tree cache is shared
    # across plugins that live in the same repo (e.g., multiple plugins
    # inside one monorepo trigger only one Tree API call total — Task 4.3).
    if PluginContentFetcher is not None:
        layout_fetcher = PluginContentFetcher()
    else:  # pragma: no cover - package always installed in CI
        logger.warning(
            "ai-resource-eval not importable; bundle fields will use API "
            "skills hint only."
        )
        layout_fetcher = None

    plugin_blacklist = load_plugin_blacklist()
    if plugin_blacklist:
        logger.info(
            "Loaded plugin-level blacklist with %d entries from plugin_sources.json",
            len(plugin_blacklist),
        )

    marketplace_cache = marketplace_verifier.load_cache(MARKETPLACE_CACHE_PATH)
    if marketplace_cache:
        logger.info(
            "Loaded marketplace manifest cache with %d entries from %s",
            len(marketplace_cache), MARKETPLACE_CACHE_PATH,
        )

    try:
        new_entries: list[dict] = []
        for raw in raw_plugins:
            try:
                entry = _entry_from_plugin(
                    raw,
                    last_synced,
                    layout_fetcher,
                    plugin_blacklist=plugin_blacklist,
                    marketplace_cache=marketplace_cache,
                )
            except Exception as e:  # noqa: BLE001 - one bad row mustn't kill all
                logger.warning(
                    "Failed to build entry for plugin name=%r: %s",
                    raw.get("name"), e,
                )
                continue
            if entry is not None:
                new_entries.append(entry)
    finally:
        if layout_fetcher is not None:
            try:
                layout_fetcher.close()
            except Exception:  # noqa: BLE001
                pass
        marketplace_verifier.save_cache(MARKETPLACE_CACHE_PATH, marketplace_cache)
    logger.info(
        "Built %d catalog entries from %d raw plugins",
        len(new_entries), len(raw_plugins),
    )

    # 3. Merge with existing on-disk index (official entries win on
    #    source_url collision because of higher source_priority — they are
    #    already present in `existing` and we skip new dupes).
    existing_raw = load_index(args.output)
    existing, pruned_existing = _prune_existing_plugin_source_entries(existing_raw)
    logger.info("Loaded %d existing entries from %s", len(existing_raw), args.output)
    if pruned_existing:
        logger.info(
            "Pruned %d stale claude-plugins-dev entries covered by "
            "plugin_sources.json",
            pruned_existing,
        )

    combined = _merge_into_existing(new_entries, existing)

    if len(combined) == len(existing_raw) and not new_entries and not pruned_existing:
        logger.warning(
            "No new claude-plugins-dev entries to add; output unchanged."
        )
        return 0

    # 4. Persist.
    save_index(combined, args.output)
    logger.info(
        "Wrote %d total entries to %s "
        "(existing=%d, claude-plugins-dev added=%d)",
        len(combined), args.output, len(existing_raw),
        len(combined) - len(existing),
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001 - task 7.5: never block CI
        logger.error("Unhandled top-level error: %s", e)
        sys.exit(0)
