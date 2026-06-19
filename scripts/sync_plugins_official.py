#!/usr/bin/env python3
"""Official Claude Code plugin marketplace sync.

Fetches `.claude-plugin/marketplace.json` from:
  - anthropics/claude-plugins-official  (source_priority=1000)
  - obra/superpowers-marketplace        (source_priority=950)
  - affaan-m/everything-claude-code     (source_priority=900)

Parses each plugin entry, optionally fetches the per-plugin `plugin.json`
manifest to compute `manifest_completeness`, and writes the resulting
catalog entries to `catalog/plugins/index.json`.

Failure isolation (task 2.4):
  - Each marketplace source is wrapped in its own try/except block.
  - A parse / fetch failure for one source logs an ERROR and continues
    to the next source.
  - Non-zero exit status is returned ONLY if zero plugins were synced
    overall across both sources.

Implementation notes:
  - Standard library only (urllib, json) — matches the conventions of
    sync_mcp_registry.py / sync_skills.py.
  - Honors GITHUB_TOKEN for raw.githubusercontent.com requests.
  - source_trust is intentionally NOT written here; it's a derived
    health signal computed by the eval pipeline (task 5.x) based on the
    `source` field.
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

# Allow running both as `python scripts/sync_plugins_official.py` and as a module.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from .utils import (  # type: ignore
        categorize,
        extract_tags,
        is_plugin_blacklisted,
        load_index,
        load_plugin_blacklist,
        save_index,
    )
    from . import marketplace_verifier  # type: ignore
except ImportError:  # pragma: no cover - script-style invocation
    from utils import (  # type: ignore
        categorize,
        extract_tags,
        is_plugin_blacklisted,
        load_index,
        load_plugin_blacklist,
        save_index,
    )
    import marketplace_verifier  # type: ignore

# PluginContentFetcher comes from the (pip install -e'd) ai-resource-eval
# package. Importing lazily inside helpers would force every test to wire it
# up; module-level import keeps things simple and matches eval_bridge.py.
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
CACHE_DIR = os.path.join(REPO_ROOT, ".plugins_official_cache")
MARKETPLACE_CACHE_PATH = os.path.join(CACHE_DIR, "marketplace_manifests.json")

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
USER_AGENT = "everything-ai-coding-plugins-sync"

# Per-source config. `id` is the catalog `source` field value;
# `repo_slug` is the GitHub <owner>/<repo> hosting the marketplace.json;
# `branch` is the branch from which to fetch (defaults to "main").
SOURCES: list[dict] = [
    {
        "id": "claude-plugins-official",
        "repo_slug": "anthropics/claude-plugins-official",
        "branch": "main",
        "source_priority": 1000,
    },
    {
        "id": "superpowers-marketplace",
        "repo_slug": "obra/superpowers-marketplace",
        "branch": "main",
        "source_priority": 950,
    },
    {
        "id": "everything-claude-code",
        "repo_slug": "affaan-m/ECC",
        "branch": "main",
        "source_priority": 900,
    },
]

# manifest_completeness scoring (task 2.2).
MANIFEST_FULL_FIELDS = ("name", "version", "description", "author")
MANIFEST_COMPLETENESS_FULL = 1.0
MANIFEST_COMPLETENESS_PARTIAL = 0.7
MANIFEST_COMPLETENESS_NONE = 0.3


logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("sync_plugins_official")


# ---------------------------------------------------------------------------
# active-discovery (github-trending + 促升 slug) 域识别
# ---------------------------------------------------------------------------
# triage_github_trending.py 是 catalog/plugins/index.json 的最后写入者，但它跑在
# sync_plugins_official 之后；CI 顺序是 official → dev → csc → trending → triage。
# official 是唯一对 plugins index 做 blanket save_index 覆盖的脚本（dev/csc 都 merge-
# preserve，只 prune 各自 SOURCE_ID），所以只要 official 保留上一轮 triage 写入的
# active-discovery plugin entry，下游 dev/csc 就会原样保留。否则 known_repos 跳过已
# 入库仓后，被抹掉的 github-trending/促升 plugin 永远补不回来。

def _load_promoted_slugs() -> set:
    """促升清单的 source_slug 集，文件缺失/损坏 → 空集（不崩，促升是可选增强）。

    ``load_promoted_repos`` 走 **延迟 import**：sync_github_trending 在模块加载期
    会 ``import sync_plugins_official``，若此处在 top-level import 它就会形成循环
    import；放进函数体内只在调用时解析，断开环。
    """
    try:
        try:
            from sync_github_trending import load_promoted_repos  # type: ignore
        except ImportError:  # pragma: no cover - module-style invocation
            from .sync_github_trending import load_promoted_repos  # type: ignore
        return {r["source_slug"] for r in load_promoted_repos()}
    except Exception as e:  # noqa: BLE001 - 促升加载失败不该卡死 sync
        logger.warning(
            "加载促升清单失败，active-discovery 保留退回仅 github-trending：%s", e
        )
        return set()


def _is_trending_owned(entry: dict, promoted_slugs: set) -> bool:
    """entry 是否属于 active-discovery 域（triage 唯一写入的 source 集）。"""
    s = entry.get("source")
    return s == "github-trending" or (s is not None and s in promoted_slugs)


def _merge_keep_foreign(primary: list, foreign: list) -> list:
    """把 foreign 中不与 primary 撞 id 的 entry 并入（primary 优先）。

    plugins 仅按 id 去重——同 monorepo 多 plugin 合法共享 source_url，绝不能按 url
    去重（对齐 merge_preserve(dedup_url=False) 与 _merge_into_existing 的 id-only 语义）。
    """
    seen_ids = {e["id"] for e in primary if e.get("id")}
    result = list(primary)
    for e in foreign:
        eid = e.get("id") or ""
        if eid and eid in seen_ids:
            continue
        if eid:
            seen_ids.add(eid)
        result.append(e)
    return result


# ---------------------------------------------------------------------------
# HTTP helpers (stdlib only)
# ---------------------------------------------------------------------------

def _http_get(url: str, timeout: int = 30) -> Optional[bytes]:
    """GET `url` with GITHUB_TOKEN auth (when targeting GitHub) and a UA header.

    Returns the response body bytes, or None on any error / non-2xx status.
    Errors are logged at WARNING level — caller decides if that's fatal.
    """
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


# ---------------------------------------------------------------------------
# GitHub repo metadata fetcher (stars + pushed_at)
# ---------------------------------------------------------------------------

# In-memory cache: 同一 marketplace 里多个 plugin 常共享 owner/repo（subfolder
# 形态），避免重复打 API 浪费 rate limit。
_repo_meta_cache: dict[str, dict] = {}


def _parse_github_owner_repo(url: str) -> Optional[tuple[str, str]]:
    """从各种 GitHub URL 形态里提取 (owner, repo)。

    支持形态：
      - https://github.com/owner/repo
      - https://github.com/owner/repo.git
      - https://github.com/owner/repo/tree/main/...
      - https://github.com/owner/repo/blob/main/...
    """
    m = re.match(
        r"https?://github\.com/([^/]+)/([^/?#.]+?)(?:\.git)?(?:[/?#]|$)",
        url,
    )
    if not m:
        return None
    return m.group(1), m.group(2)


def _fetch_repo_meta(source_url: str) -> dict:
    """通过 GitHub API 抓 stars + pushed_at，缺省返回空 dict（不阻塞 entry 生成）。

    rate limit：authenticated 5,000 calls/h，190 个 official plugin 单 sync 跑下
    来远不到上限。同 owner/repo 跨 plugin 复用 cache。
    """
    parsed = _parse_github_owner_repo(source_url)
    if not parsed:
        return {}
    owner, repo = parsed
    key = f"{owner.lower()}/{repo.lower()}"
    if key in _repo_meta_cache:
        return _repo_meta_cache[key]
    api_url = f"https://api.github.com/repos/{owner}/{repo}"
    data = _http_get_json(api_url)
    if not isinstance(data, dict):
        _repo_meta_cache[key] = {}
        return {}
    meta = {
        "stars": data.get("stargazers_count"),
        "pushed_at": data.get("pushed_at"),
    }
    _repo_meta_cache[key] = meta
    return meta


# ---------------------------------------------------------------------------
# URL builders
# ---------------------------------------------------------------------------

def _marketplace_url(repo_slug: str) -> str:
    """User-facing GitHub URL of the marketplace repo (used for marketplace_url field)."""
    return f"https://github.com/{repo_slug}"


def _marketplace_json_url(repo_slug: str, branch: str) -> str:
    """raw.githubusercontent URL of the marketplace.json file."""
    return (
        f"https://raw.githubusercontent.com/{repo_slug}/{branch}"
        f"/.claude-plugin/marketplace.json"
    )


def _resolve_source_url(plugin_entry: dict, marketplace_repo: str, branch: str) -> str:
    """Determine the canonical `source_url` for a plugin entry.

    Marketplace `source` field can be:
      - "./plugins/foo"          → subfolder of marketplace repo
      - "github:owner/repo"      → external GitHub repo
      - "git+https://..."        → arbitrary git URL
      - "https://github.com/..." → direct GitHub URL
      - missing                  → fall back to marketplace repo URL
    """
    src = plugin_entry.get("source")
    if isinstance(src, dict):
        # Some marketplaces use {source: "github", repo: "owner/repo"} style.
        if src.get("source") == "github" and src.get("repo"):
            return f"https://github.com/{src['repo']}"
        if src.get("url"):
            src = src.get("url")
        else:
            src = ""

    if isinstance(src, str) and src:
        if src.startswith("github:"):
            return f"https://github.com/{src[len('github:'):]}"
        if src.startswith("https://") or src.startswith("http://"):
            return src
        if src.startswith("git+"):
            return src[len("git+"):]
        if src.startswith("./") or src.startswith("/"):
            # Strip ONLY the leading "./" or "/" — not as a character set, so a
            # hidden-dir subdir like "./.claude/plugins/x" keeps its ".claude"
            # dot (lstrip("./") would eat it → wrong path → 404).
            sub = (src[2:] if src.startswith("./") else src.lstrip("/")).strip("/")
            return f"https://github.com/{marketplace_repo}/tree/{branch}/{sub}"
    # Fallback: the marketplace repo itself.
    return _marketplace_url(marketplace_repo)


def _plugin_manifest_candidate_urls(
    plugin_entry: dict, marketplace_repo: str, branch: str
) -> list[str]:
    """Return raw URLs to try for fetching the plugin's plugin.json.

    Returns an empty list when the source is external (we don't follow
    cross-repo URLs in this task — manifest_completeness falls back to
    whatever the marketplace entry itself supplies).
    """
    src = plugin_entry.get("source")
    if isinstance(src, dict):
        src = src.get("url") or ""
    if not isinstance(src, str):
        return []

    # Only inspect manifest when the plugin lives in the marketplace repo itself.
    if src.startswith("./") or src.startswith("/"):
        sub = src.lstrip("./").lstrip("/").rstrip("/")
        return [
            f"https://raw.githubusercontent.com/{marketplace_repo}/{branch}"
            f"/{sub}/.claude-plugin/plugin.json",
            f"https://raw.githubusercontent.com/{marketplace_repo}/{branch}"
            f"/{sub}/plugin.json",
        ]
    return []


# ---------------------------------------------------------------------------
# manifest_completeness
# ---------------------------------------------------------------------------

def compute_manifest_completeness(manifest: Optional[dict]) -> float:
    """Score manifest completeness per task 2.2.

    - 1.0 if manifest contains all of name / version / description / author
    - 0.7 if the manifest is missing exactly one of `description` or `version`
          (other "partial" shapes also collapse to 0.7 conservatively)
    - 0.3 if no manifest is available at all
    """
    if not manifest or not isinstance(manifest, dict):
        return MANIFEST_COMPLETENESS_NONE

    def _present(key: str) -> bool:
        v = manifest.get(key)
        if v is None:
            return False
        if isinstance(v, str):
            return v.strip() != ""
        if isinstance(v, (list, dict)):
            return len(v) > 0
        return True

    have = {k: _present(k) for k in MANIFEST_FULL_FIELDS}
    if all(have.values()):
        return MANIFEST_COMPLETENESS_FULL

    # If only `description` or `version` (one of them) is missing → 0.7.
    # Anything else (e.g. missing name/author, or missing both desc+version) is
    # also weaker than full but treated as 0.7 per the spec's "missing one"
    # bucket — the rubric only enumerates two strata above the no-manifest
    # floor, so non-trivial partials still belong here.
    return MANIFEST_COMPLETENESS_PARTIAL


# ---------------------------------------------------------------------------
# Bundle counting
# ---------------------------------------------------------------------------

def _resolve_layout_repo_and_root(
    plugin_entry: dict, marketplace_repo: str
) -> Optional[tuple[str, str, str]]:
    """Return ``(repo, ref, plugin_root)`` for layout detection.

    Mirrors the matrix handled by ``_resolve_source_url``:

      * ``"./plugins/foo"`` → marketplace repo, plugin_root="plugins/foo", ref="HEAD"
      * ``"github:owner/repo"`` → external repo, plugin_root="", ref="HEAD"
      * ``"https://github.com/owner/repo[/tree/<ref>/sub]"`` → owner/repo, ref=<ref> or "HEAD", sub
      * dict with ``{source: "github", repo: "owner/repo"}`` → that repo, ref="HEAD", root=""
      * missing → marketplace repo root, ref="HEAD"

    Returns ``None`` when the source is non-GitHub (we can't run Tree API on it).
    """
    src = plugin_entry.get("source")
    if isinstance(src, dict):
        if src.get("source") == "github" and src.get("repo"):
            return (str(src["repo"]).strip(), "HEAD", "")
        url = src.get("url")
        if isinstance(url, str):
            src = url
        else:
            src = ""

    if isinstance(src, str) and src:
        if src.startswith("./") or src.startswith("/"):
            sub = src.lstrip("./").lstrip("/").rstrip("/")
            return (marketplace_repo, "HEAD", sub)
        if src.startswith("github:"):
            return (src[len("github:"):].strip(), "HEAD", "")
        if src.startswith("git+"):
            src = src[len("git+"):]
        if src.startswith("https://github.com/") or src.startswith(
            "http://github.com/"
        ):
            m = re.match(
                r"https?://github\.com/([^/]+)/([^/?#.]+?)(?:\.git)?"
                r"(?:/(?:tree|blob)/([^/]+)(?:/(.+))?)?(?:[/?#]|$)",
                src,
            )
            if m:
                owner, repo = m.group(1), m.group(2)
                ref = (m.group(3) or "HEAD").strip() or "HEAD"
                sub = (m.group(4) or "").strip("/")
                return (f"{owner}/{repo}", ref, sub)
            return None
        # Unknown scheme.
        return None
    # No source field → marketplace repo root.
    return (marketplace_repo, "HEAD", "")


def _namespace_prefix_from_layout(layout, fallback_name: str) -> str:
    """Pick the ``<plugin>`` prefix used in ``<plugin>:<name>`` namespaces.

    ``layout.skills_namespaces`` is built by the layout detector with its OWN
    derived plugin name (``_derive_plugin_name``), which may differ from the
    marketplace-supplied ``plugin_name``. To keep command/agent namespaces
    consistent with skills_namespaces (so the merge stage groups them under the
    same plugin), reuse that exact prefix when any skill namespace exists; else
    fall back to ``fallback_name``.
    """
    for ns in getattr(layout, "skills_namespaces", None) or []:
        if isinstance(ns, str) and ":" in ns:
            return ns.split(":", 1)[0]
    return fallback_name


def _component_namespaces(paths: list[str], plugin_root: str, prefix: str) -> list[str]:
    """Build ``<prefix>:<name>`` namespaces position-aligned with ``paths``.

    ``<name>`` is the repo-relative path under the component dir
    (``commands/`` / ``.commands/`` / ``agents/`` / ``.agents/``) with the
    plugin_root prefix and the component-dir segment stripped and the trailing
    ``.md`` removed — mirroring sync_plugins_csc.compute_bundle so both sync
    paths feed merge_index identically. Falls back to the file stem when the
    expected component dir isn't found (robust to nested/odd layouts).
    """
    component_dirs = ("commands", ".commands", "agents", ".agents")
    namespaces: list[str] = []
    for p in paths:
        rel = (
            p[len(plugin_root) + 1:]
            if plugin_root and p.startswith(plugin_root + "/")
            else p
        )
        name = None
        segs = rel.split("/")
        for i, seg in enumerate(segs[:-1]):
            if seg in component_dirs:
                # everything AFTER the component dir, minus a trailing .md
                tail = "/".join(segs[i + 1:])
                name = tail[:-3] if tail.endswith(".md") else tail
                break
        if not name:
            # Fallback: file stem (drop dir + .md).
            stem = segs[-1]
            name = stem[:-3] if stem.endswith(".md") else stem
        namespaces.append(f"{prefix}:{name}")
    return namespaces


def _build_bundle_from_layout(
    fetcher,
    repo: Optional[str],
    plugin_root: str,
    manifest: Optional[dict],
    plugin_name: str,
    ref: str = "HEAD",
) -> dict:
    """Layout-detector-first bundle builder with manifest fallback.

    Strategy:

      1. If a fetcher + repo are available, call
         ``detect_plugin_layout(repo, plugin_root, ref)``. When ``is_plugin`` is
         True, use the path counts as the source of truth (most accurate).
      2. When the layout detector reports a ``fetch_error`` (Tree API 4xx/5xx /
         network exception), keep the bundle at zeros so the next sync retries
         instead of publishing manifest-derived counts that may be stale or
         contradict reality (task 4.4 — failure path stays zero).
      3. When the target legitimately lacks ``.claude-plugin/plugin.json`` (no
         fetch error, just no marker file) and the manifest carries explicit
         counts, fall back to ``_build_bundle(manifest, …)`` so legacy
         README-only plugin shells still get manifest-derived counts.
      4. On any exception, log WARNING and return zeros.
    """
    zero_bundle = {
        "skills_count": 0,
        "commands_count": 0,
        "agents_count": 0,
        "mcp_servers_count": 0,
        "skills_namespaces": [],
        # New extension fields (defaults — no signals available)
        "hooks_count": 0,
        "hook_events": [],
        "mcp_server_names": [],
        "mcp_server_configs": {},
        "is_marketplace_repo": False,
    }

    if fetcher is not None and repo:
        try:
            layout = fetcher.detect_plugin_layout(repo, plugin_root, ref=ref)
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "detect_plugin_layout failed for %s/%s@%s (plugin=%s): %s",
                repo,
                plugin_root or "<root>",
                ref,
                plugin_name,
                e,
            )
            return zero_bundle

        if layout.is_plugin:
            # Marketplace shells return zeroed counts plus the flag so callers
            # can short-circuit entry creation.
            if getattr(layout, "is_marketplace_repo", False):
                bundle = dict(zero_bundle)
                bundle["is_marketplace_repo"] = True
                return bundle
            ns_prefix = _namespace_prefix_from_layout(layout, plugin_name)
            return {
                "skills_count": len(layout.skill_paths),
                "commands_count": len(layout.command_paths),
                "agents_count": len(layout.agent_paths),
                "mcp_servers_count": len(layout.mcp_server_names),
                "skills_namespaces": list(layout.skills_namespaces),
                # Repo-relative SKILL.md paths, position-aligned with
                # ``skills_namespaces``. Carried through so the merge stage can
                # synthesize standalone ``type=skill`` entries for orphan
                # sub-skills (no matching catalog skill) and build a working
                # ``install.git_clone`` block pointing at the skill directory.
                # See merge_index._apply_bundled_in_annotations orphan branch.
                "skill_paths": list(layout.skill_paths),
                # Commands / agents path arrays + position-aligned namespaces.
                # The layout detector already classified these (it counts them);
                # carrying the PATHS through lets merge_index synthesize
                # standalone type=command / type=subagent children for official
                # plugins too (not just cospowers). Field names/shape mirror
                # sync_plugins_csc.compute_bundle and merge_index's
                # _BUNDLED_CHILD_KINDS consumption contract
                # (commands_namespaces↔command_paths, agents_namespaces↔agent_paths).
                "command_paths": list(layout.command_paths),
                "agent_paths": list(layout.agent_paths),
                "commands_namespaces": _component_namespaces(
                    layout.command_paths, layout.plugin_root, ns_prefix
                ),
                "agents_namespaces": _component_namespaces(
                    layout.agent_paths, layout.plugin_root, ns_prefix
                ),
                # Source coordinates used to construct the orphan skill's
                # install block (repo + branch). ``ref`` may be "HEAD"; the
                # downloader defaults to "main" when no usable branch is given.
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
            logger.warning(
                "Tree API failure detecting layout for %s/%s@%s (plugin=%s): %s. "
                "Keeping zero bundle for retry on next sync.",
                repo,
                plugin_root or "<root>",
                ref,
                plugin_name,
                layout.fetch_error,
            )
            return zero_bundle

        logger.info(
            "Layout detector found no plugin.json at %s/%s@%s (plugin=%s); "
            "falling back to manifest counts.",
            repo,
            plugin_root or "<root>",
            ref,
            plugin_name,
        )

    # Final fallback: manifest-derived counts (existing behaviour).
    return _build_bundle(manifest, plugin_name)


def _count_manifest_value(value) -> int:
    """Helper used by ``_build_bundle_from_layout`` for non-skill counts."""
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        return len(value)
    if isinstance(value, int):
        return value
    return 0


def _build_bundle(manifest: Optional[dict], plugin_name: str) -> dict:
    """Best-effort bundle stats from plugin.json.

    Counts default to 0 when the manifest doesn't expose them; this matches
    the schema (`bundle` always present, integer counts, `skills_namespaces`
    array possibly empty).
    """
    bundle = {
        "skills_count": 0,
        "commands_count": 0,
        "agents_count": 0,
        "mcp_servers_count": 0,
        "skills_namespaces": [],
        "hooks_count": 0,
        "hook_events": [],
        "mcp_server_names": [],
        "mcp_server_configs": {},
        "is_marketplace_repo": False,
    }
    if not isinstance(manifest, dict):
        return bundle

    def _count(value) -> int:
        if isinstance(value, list):
            return len(value)
        if isinstance(value, dict):
            return len(value)
        if isinstance(value, int):
            return value
        return 0

    bundle["skills_count"] = _count(manifest.get("skills"))
    bundle["commands_count"] = _count(manifest.get("commands"))
    bundle["agents_count"] = _count(manifest.get("agents"))
    mcp_field = manifest.get("mcpServers") or manifest.get("mcp_servers")
    bundle["mcp_servers_count"] = _count(mcp_field)
    if isinstance(mcp_field, dict):
        bundle["mcp_server_names"] = sorted(
            k for k in mcp_field.keys() if isinstance(k, str)
        )
        bundle["mcp_servers_count"] = len(bundle["mcp_server_names"])
        configs = {}
        for k, cfg in mcp_field.items():
            if not isinstance(k, str) or not isinstance(cfg, dict):
                continue
            command = cfg.get("command")
            url = cfg.get("url")
            has_command = isinstance(command, str) and command.strip()
            has_url = isinstance(url, str) and url.strip()
            if has_command or has_url:
                configs[k] = cfg
        bundle["mcp_server_configs"] = configs

    skills = manifest.get("skills")
    namespaces: list[str] = []
    if isinstance(skills, list):
        for s in skills:
            if isinstance(s, str) and s:
                namespaces.append(f"{plugin_name}:{s}")
            elif isinstance(s, dict):
                sn = s.get("name") or s.get("id")
                if sn:
                    namespaces.append(f"{plugin_name}:{sn}")
    elif isinstance(skills, dict):
        for sn in skills.keys():
            if sn:
                namespaces.append(f"{plugin_name}:{sn}")
    bundle["skills_namespaces"] = namespaces
    return bundle


# ---------------------------------------------------------------------------
# Slug / id helpers
# ---------------------------------------------------------------------------

_SLUG_RE = re.compile(r"[^a-z0-9-]+")


def _slugify(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[\s_./]+", "-", s)
    s = _SLUG_RE.sub("-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s


def _build_id(source_id: str, plugin_name: str) -> str:
    # Use a per-source prefix to avoid collisions when two marketplaces ship
    # plugins with the same name. Prefix is intentionally short and stable.
    prefix = {
        "claude-plugins-official": "anthropic",
        "superpowers-marketplace": "obra",
        "everything-claude-code": "ecc",
    }.get(source_id, _slugify(source_id))
    return _slugify(f"{prefix}-{plugin_name}")


# ---------------------------------------------------------------------------
# Per-plugin entry construction
# ---------------------------------------------------------------------------

def _author_string(author) -> str:
    if isinstance(author, str):
        return author
    if isinstance(author, dict):
        return author.get("name") or author.get("email") or ""
    return ""


def _entry_from_plugin(
    plugin_entry: dict,
    source_cfg: dict,
    last_synced_iso: str,
    layout_fetcher=None,
    plugin_blacklist: Optional[list] = None,
    marketplace_cache: Optional[dict] = None,
) -> Optional[dict]:
    """Convert one marketplace plugin definition into a catalog entry.

    Returns None if the plugin definition is too malformed to produce a
    usable entry (e.g. missing name) or if ``(source, name)`` matches the
    plugin-level blacklist loaded from ``plugin_sources.json``.
    """
    name = (plugin_entry.get("name") or "").strip()
    if not name:
        logger.warning(
            "Skipping plugin without a name in source=%s: %r",
            source_cfg["id"],
            plugin_entry,
        )
        return None

    if is_plugin_blacklisted(source_cfg["id"], name, plugin_blacklist):
        logger.debug(
            "Skipping plugin (source=%s, name=%s): in plugin_sources.json "
            "plugins blacklist",
            source_cfg["id"],
            name,
        )
        return None

    repo_slug = source_cfg["repo_slug"]
    branch = source_cfg["branch"]
    description = (plugin_entry.get("description") or "").strip()
    version = (plugin_entry.get("version") or "").strip()
    author_str = _author_string(plugin_entry.get("author"))
    upstream_category = (plugin_entry.get("category") or "").strip()
    upstream_tags = plugin_entry.get("tags")
    if not isinstance(upstream_tags, list):
        upstream_tags = []

    # Try fetching plugin.json for richer manifest data + bundle stats.
    manifest: Optional[dict] = None
    for url in _plugin_manifest_candidate_urls(plugin_entry, repo_slug, branch):
        candidate = _http_get_json(url)
        if isinstance(candidate, dict):
            manifest = candidate
            break

    # If we couldn't fetch a manifest but the marketplace entry itself supplies
    # name+version+description+author, treat the entry as its own manifest for
    # the purposes of completeness scoring (per task spec wording).
    if manifest is None and (description or version or author_str):
        synthetic_manifest = {
            "name": name,
            "version": version,
            "description": description,
            "author": author_str,
        }
        manifest_for_score = synthetic_manifest
    else:
        manifest_for_score = manifest

    completeness = compute_manifest_completeness(manifest_for_score)
    layout_target = _resolve_layout_repo_and_root(plugin_entry, repo_slug)
    if layout_target is None:
        layout_repo, layout_ref, layout_plugin_root = None, "HEAD", ""
    else:
        layout_repo, layout_ref, layout_plugin_root = layout_target
    bundle = _build_bundle_from_layout(
        layout_fetcher,
        layout_repo,
        layout_plugin_root,
        manifest,
        name,
        ref=layout_ref,
    )

    # Marketplace shells SHALL NOT be written as plugin entries.  The sync
    # layer is expected to iterate plugins/<name>/ subdirectories separately
    # (existing behaviour for nested-plugin marketplace flows).
    if bundle.get("is_marketplace_repo"):
        logger.info(
            "Skipping marketplace shell at %s/%s@%s (plugin=%s) — nested plugins "
            "will be enumerated via sub-paths instead.",
            layout_repo,
            layout_plugin_root or "<root>",
            layout_ref,
            name,
        )
        return None

    # Description fallback: marketplace > manifest > "".
    if not description and isinstance(manifest, dict):
        description = (manifest.get("description") or "").strip()

    # Version fallback similarly.
    if not version and isinstance(manifest, dict):
        version = (manifest.get("version") or "").strip()

    source_url = _resolve_source_url(plugin_entry, repo_slug, branch)
    marketplace_url = _marketplace_url(repo_slug)

    # 补抓 GitHub repo stars + pushed_at（marketplace.json 不提供，但 evaluation
    # 的 popularity / freshness 信号需要）。同 owner/repo 跨 plugin 复用 cache。
    repo_meta = _fetch_repo_meta(source_url)

    # Tags / category — pass marketplace-supplied values through `categorize`
    # / `extract_tags` so plugin entries follow the same enrichment heuristics
    # as the existing types. Upstream tags are preserved verbatim.
    derived_tags = extract_tags(name, description)
    tags: list[str] = []
    seen_tags: set[str] = set()
    for t in list(upstream_tags) + derived_tags:
        if not isinstance(t, str):
            continue

        tl = t.strip().lower()
        if tl and tl not in seen_tags:
            seen_tags.add(tl)
            tags.append(tl)

    category = categorize(
        name=name,
        description=description,
        tags=tags,
        upstream_category=upstream_category,
    )

    # Marketplace verification: official sources already point at canonical
    # GitHub repo slugs, but we still fetch the manifest's `name` field so
    # `enabledPlugins` can be keyed correctly. Cache shared across the sync run.
    #
    # When marketplace_cache is None the caller opted out of marketplace
    # verification entirely (e.g., unit tests that mock just the marketplace.json
    # fetch). Skip the verifier — the resulting entry will have
    # marketplace_verified=False, which downstream treats as "needs catalog
    # refresh / unverified" exactly like a real fetch failure.
    if marketplace_cache is not None:
        marketplace_name, marketplace_verified = marketplace_verifier.verify_marketplace(
            repo_slug, name, marketplace_cache,
        )
    else:
        marketplace_name, marketplace_verified = (None, False)

    entry: dict = {
        "id": _build_id(source_cfg["id"], name),
        "name": name,
        "type": "plugin",
        "description": description,
        "source_url": source_url,
        "category": category,
        "tags": tags,
        "tech_stack": [],
        "source": source_cfg["id"],
        "source_priority": source_cfg["source_priority"],
        "marketplace_url": marketplace_url,
        "platforms": ["claude-code"],
        "install": {
            "method": "plugin_marketplace",
            "plugin_name": name,
            "marketplace_repo": repo_slug,
            "marketplace_name": marketplace_name,
            "marketplace_verified": marketplace_verified,
            "marketplace": repo_slug,  # display-only; retained for UI back-compat
        },
        "bundle": bundle,
        "manifest_completeness": completeness,
        "last_synced": last_synced_iso,
        # Health pipeline reads these; stars / pushed_at 由 GitHub API 补抓
        # （marketplace.json 不提供）。失败时为 None，evaluation 走 excluded
        # 信号路径不拖累分数。
        "stars": repo_meta.get("stars"),
        "pushed_at": repo_meta.get("pushed_at"),
        "version": version,
    }
    return entry


# ---------------------------------------------------------------------------
# Per-source sync (with isolation)
# ---------------------------------------------------------------------------

def sync_one_source(
    source_cfg: dict,
    last_synced_iso: str,
    layout_fetcher=None,
    plugin_blacklist: Optional[list] = None,
    marketplace_cache: Optional[dict] = None,
) -> list[dict]:
    """Sync a single marketplace source.

    Returns the list of catalog entries from this source. On any failure
    logs ERROR and returns []; the caller (main) decides whether the
    overall script exits non-zero.
    """
    repo_slug = source_cfg["repo_slug"]
    branch = source_cfg["branch"]
    src_id = source_cfg["id"]
    url = _marketplace_json_url(repo_slug, branch)
    logger.info("Fetching marketplace.json: source=%s url=%s", src_id, url)

    try:
        body = _http_get(url)
        if body is None:
            logger.error(
                "Failed to fetch marketplace.json for source=%s (network/HTTP error)",
                src_id,
            )
            return []
        try:
            data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            logger.error(
                "Failed to parse marketplace.json for source=%s: %s",
                src_id,
                e,
            )
            return []

        if not isinstance(data, dict):
            logger.error(
                "Unexpected marketplace.json shape for source=%s: top-level is %s",
                src_id,
                type(data).__name__,
            )
            return []

        plugins = data.get("plugins")
        if not isinstance(plugins, list):
            logger.error(
                "marketplace.json for source=%s has no `plugins` array (got %s)",
                src_id,
                type(plugins).__name__,
            )
            return []

        entries: list[dict] = []
        for raw in plugins:
            if not isinstance(raw, dict):
                logger.warning(
                    "Skipping non-dict plugin entry in source=%s: %r",
                    src_id,
                    raw,
                )
                continue
            try:
                entry = _entry_from_plugin(
                    raw,
                    source_cfg,
                    last_synced_iso,
                    layout_fetcher,
                    plugin_blacklist=plugin_blacklist,
                    marketplace_cache=marketplace_cache,
                )
            except Exception as e:  # noqa: BLE001 - never let one entry kill the source
                logger.warning(
                    "Failed to build entry for plugin %r in source=%s: %s",
                    raw.get("name"),
                    src_id,
                    e,
                )
                continue
            if entry is not None:
                entries.append(entry)

        logger.info(
            "Source=%s yielded %d plugin entries (from %d raw)",
            src_id,
            len(entries),
            len(plugins),
        )
        return entries
    except Exception as e:  # noqa: BLE001 - guarantee failure isolation
        logger.error(
            "Unhandled error syncing source=%s: %s",
            src_id,
            e,
        )
        return []


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    """Current UTC timestamp in `YYYY-MM-DDTHH:MM:SSZ` form."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Sync the official Claude Code plugin marketplaces "
            "(anthropics/claude-plugins-official + obra/superpowers-marketplace "
            "+ affaan-m/ECC) "
            "into catalog/plugins/index.json."
        ),
    )
    parser.add_argument(
        "--output",
        default=OUTPUT_PATH,
        help=f"Output index.json path (default: {OUTPUT_PATH})",
    )
    args = parser.parse_args(argv)

    # Catalog schema declares `last_synced` as `format: date` (YYYY-MM-DD),
    # matching sync_mcp_registry.py / sync_skills.py / sync_windsurfrules.py.
    last_synced_iso = date.today().isoformat()
    all_entries: list[dict] = []
    failed_sources: list[str] = []

    # One fetcher per sync run — its tree cache lets the entire marketplace
    # monorepo (50+ plugins) share a single GitHub Tree API call (Decision 5).
    if PluginContentFetcher is not None:
        layout_fetcher = PluginContentFetcher()
    else:  # pragma: no cover - package always installed in CI
        logger.warning(
            "ai-resource-eval not importable; bundle fields will be zeros."
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
        for source_cfg in SOURCES:
            entries = sync_one_source(
                source_cfg,
                last_synced_iso,
                layout_fetcher,
                plugin_blacklist=plugin_blacklist,
                marketplace_cache=marketplace_cache,
            )
            if not entries:
                failed_sources.append(source_cfg["id"])
            all_entries.extend(entries)
    finally:
        if layout_fetcher is not None:
            try:
                layout_fetcher.close()
            except Exception:  # noqa: BLE001
                pass
        marketplace_verifier.save_cache(MARKETPLACE_CACHE_PATH, marketplace_cache)

    # Stable ordering: by id, so diffs in git remain readable.
    all_entries.sort(key=lambda e: e.get("id", ""))

    if not all_entries:
        logger.error(
            "Zero plugins synced overall (failed sources: %s); exiting non-zero.",
            ", ".join(failed_sources) or "<none>",
        )
        return 1

    # Preserve active-discovery (github-trending + 促升 slug) plugin entries
    # written by triage_github_trending.py last cycle. sync_plugins_official is the
    # only blanket-overwrite writer of the per-type plugins index (dev/csc both
    # merge-preserve), so without this the foreign entries get erased every cycle
    # and known_repos prevents triage from re-discovering them. Merge by id only —
    # same-monorepo plugins legitimately share a source_url.
    existing_entries = load_index(args.output)
    promoted_slugs = _load_promoted_slugs()
    preserved_foreign = [
        e for e in existing_entries if _is_trending_owned(e, promoted_slugs)
    ]
    if preserved_foreign:
        before = len(all_entries)
        all_entries = _merge_keep_foreign(all_entries, preserved_foreign)
        # Keep the by-id ordering stable after the merge for readable git diffs.
        all_entries.sort(key=lambda e: e.get("id", ""))
        logger.info(
            "Preserved %d active-discovery plugin entries from existing index "
            "(github-trending + 促升 slug); added %d after id dedup",
            len(preserved_foreign),
            len(all_entries) - before,
        )

    save_index(all_entries, args.output)
    logger.info(
        "Wrote %d plugin entries to %s (failed sources: %s)",
        len(all_entries),
        args.output,
        ", ".join(failed_sources) or "<none>",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
