#!/usr/bin/env python3
"""GitHub Search 主动发现源 —— 把"按 stars 从 GitHub 搜索发现热门 skill/plugin 仓"
固化成一个 sync 源，补上"发现完全依赖上游 curated 白名单/registry 先收录"的盲区。

数据流：
    GitHub Search (repo) 按 stars 召回候选仓
      → known_repos 预过滤（扫描/构造之前就挡掉已存在于任意 type/source 的仓）
      → 一次 Tree API 同时判定结构：含 .claude-plugin/marketplace.json → plugin；
        含 SKILL.md → skill；都没有 → 丢弃（天然剔除越界工具）
      → skill 复用 skill_registry.scan_repo_via_api + hard_filter
        plugin 复用 sync_plugins_official.sync_one_source（_entry_from_plugin）
      → merge-preserve 写 catalog/{skills,plugins}/index.json
      → 由 merge_index 的 deduplicate() 作正确性兜底

去重设计：repo 级 known_repos 预过滤是主防线（既省 API/LLM，又物理杜绝
deduplicate() 因 type 分命名空间而抓不住的跨类型重复）；merge 阶段 deduplicate() 兜底。
详见 .trellis/tasks/06-16-.../research/dedup-analysis.md。

依赖：仅标准库 + 本仓 utils/skill_registry/sync_plugins_official（后者的 plugin
bundle 字段依赖可选的 ai-resource-eval，未装时 bundle 置零，不阻塞）。
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils import (  # noqa: E402
    github_api,
    list_repo_files,
    load_index,
    save_index,
    normalize_source_url,
    to_kebab_case,
    categorize,
    extract_tags,
)
import skill_registry  # noqa: E402  scan_repo_via_api, hard_filter
import sync_plugins_official as spo  # noqa: E402  sync_one_source 等

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("sync_github_trending")

# --- 路径常量 -------------------------------------------------------------
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPTS_DIR, ".."))
CATALOG_DIR = os.path.join(REPO_ROOT, "catalog")
SKILLS_INDEX = os.path.join(CATALOG_DIR, "skills", "index.json")
PLUGINS_INDEX = os.path.join(CATALOG_DIR, "plugins", "index.json")
CACHE_DIR = os.path.join(REPO_ROOT, ".github_trending_cache")
VERIFY_CACHE_PATH = os.path.join(CACHE_DIR, "verify_cache.json")

# 预过滤要覆盖的现有索引（全 type/source）。catalog/index.json 是上周全量超集；
# 各 per-type index.json 是本周新鲜产物（CI 中 skills/plugins sync 先于本源）。
KNOWN_INDEX_PATHS = [
    os.path.join(CATALOG_DIR, "index.json"),
    SKILLS_INDEX,
    PLUGINS_INDEX,
    os.path.join(CATALOG_DIR, "mcp", "index.json"),
    os.path.join(CATALOG_DIR, "rules", "index.json"),
    os.path.join(CATALOG_DIR, "prompts", "index.json"),
]

# 已知镜像归一（与 utils._KNOWN_MIRRORS 对齐）：镜像仓视同 canonical，避免把镜像当新仓。
_KNOWN_MIRRORS = {"sickn33/antigravity-awesome-skills": "anthropics/skills"}

# --- 发现参数（可由环境变量覆盖）-----------------------------------------
MIN_STARS = int(os.environ.get("TRENDING_MIN_STARS", "50"))
MAX_PAGES = int(os.environ.get("TRENDING_MAX_PAGES", "3"))          # 每查询翻几页（按 stars 排序，尾部价值低）
SEARCH_THROTTLE = float(os.environ.get("TRENDING_THROTTLE", "2.0"))  # search 桶 authed 30/min ≈ 1 次/2s
RECENCY_DAYS = int(os.environ.get("TRENDING_RECENCY_DAYS", "90"))    # trending 切片：近 N 天新仓
SOURCE_ID = "github-trending"
PLUGIN_SOURCE_PRIORITY = 600  # 低于 official/superpowers/ECC/dev，碰撞时让既有源胜出

# trending 日期切片在 main() 里基于运行日期动态拼，避免模块级求值。
SKILL_QUERIES = [
    "topic:claude-skill",
    "topic:claude-skills",
    "topic:agent-skills",
    "topic:claude-code",
    '"claude skills" in:name,description',
    '"agent skills" in:name,description',
    '"SKILL.md" in:readme',
]
PLUGIN_QUERIES = [
    "topic:claude-plugin",
    "topic:claude-code-plugin",
    '"claude-plugin" in:name,description',
]


# --- owner/repo 解析 + known_repos 构建 -----------------------------------

def owner_repo_from_url(url):
    """从任意 GitHub URL 提取小写 ``owner/repo``；非 GitHub / 无法解析返回 None。"""
    if not url:
        return None
    m = re.search(r"github\.com/([^/]+)/([^/#?]+)", url, re.IGNORECASE)
    if not m:
        return None
    repo = m.group(2)
    if repo.endswith(".git"):
        repo = repo[:-4]
    slug = f"{m.group(1).lower()}/{repo.lower()}"
    return _KNOWN_MIRRORS.get(slug, slug)


def build_known_repos(index_paths=KNOWN_INDEX_PATHS):
    """构建 ``known_repos: set[str]``（全小写 owner/repo），覆盖全 catalog 全类型。

    每条 entry 双路提取：``source_url`` 反解 + ``install.marketplace_repo``
    （后者覆盖 marketplace 容器仓无自指 source_url 的盲区，见 dedup-analysis §4.4）。
    构建失败不静默退化成空 set —— 空 set 会让预过滤失效、全量重评。
    """
    known = set()
    loaded_any = False
    for path in index_paths:
        if not os.path.exists(path):
            continue
        try:
            entries = load_index(path)
        except Exception as e:  # noqa: BLE001
            logger.warning("known_repos: 读取 %s 失败：%s", path, e)
            continue
        loaded_any = True
        for e in entries or []:
            slug = owner_repo_from_url(e.get("source_url") or "")
            if slug:
                known.add(slug)
            inst = e.get("install")
            if isinstance(inst, dict):
                mr = inst.get("marketplace_repo")
                if mr and "/" in mr:
                    known.add(_KNOWN_MIRRORS.get(mr.lower(), mr.lower()))
    if not loaded_any:
        raise RuntimeError(
            "build_known_repos: 没有任何现有 index.json 可读，预过滤会失效；中止以免重复入库"
        )
    return known


# --- 发现：GitHub Search ---------------------------------------------------

def search_repos(query, max_pages=MAX_PAGES, throttle=SEARCH_THROTTLE, api=github_api):
    """跑一个 repo search 查询（按 stars 降序），返回 search item 列表。

    主动节流避开 search 桶（authed 30/min）；命中不足一页即停。``api`` 可注入便于测试。
    """
    items = []
    for page in range(1, max_pages + 1):
        q = quote(query, safe="")
        path = (
            f"search/repositories?q={q}&sort=stars&order=desc"
            f"&per_page=100&page={page}"
        )
        data = api(path)
        if not data or not isinstance(data, dict):
            break
        page_items = data.get("items") or []
        items.extend(page_items)
        if len(page_items) < 100:
            break  # 最后一页
        if throttle:
            time.sleep(throttle)
    return items


def collect_candidates(queries, known_repos, min_stars=MIN_STARS,
                       max_pages=MAX_PAGES, throttle=SEARCH_THROTTLE, api=github_api):
    """跑多个查询，聚合去重，预过滤掉已知仓与低星仓。

    返回 ``(candidates, stats)``：candidates 是 ``{full_name_lower: item}``，
    stats 记录召回/预过滤命中数（供 WARN 汇总）。
    """
    candidates = {}
    stats = {"raw": 0, "prefiltered_known": 0, "below_min_stars": 0}
    for query in queries:
        for it in search_repos(query, max_pages, throttle, api):
            full = (it.get("full_name") or "").lower()
            if not full or "/" not in full:
                continue
            stats["raw"] += 1
            if (it.get("stargazers_count") or 0) < min_stars:
                stats["below_min_stars"] += 1
                continue
            slug = _KNOWN_MIRRORS.get(full, full)
            if slug in known_repos:
                stats["prefiltered_known"] += 1
                continue
            if full in candidates:
                continue
            candidates[full] = it
    return candidates, stats


# --- 结构验证（一次 Tree 调用同时判 skill / plugin）------------------------

_MARKETPLACE_PATHS = {".claude-plugin/marketplace.json", "marketplace.json"}


def classify_repo(repo_slug, branch, api_list_files=list_repo_files):
    """用一次 Tree API 调用判定仓库结构属性。

    返回 ``("plugin"|"skill"|None, skill_paths)``：
      - 含 .claude-plugin/marketplace.json（或根 marketplace.json）→ "plugin"（优先，
        其 bundled skill 由下游 merge 合成，避免与 standalone skill 双重收录）
      - 否则含任意 SKILL.md → "skill"
      - 都没有 → None（越界工具天然落此）
    ``api_list_files`` 可注入便于测试。
    """
    paths = api_list_files(repo_slug, branch) or []
    has_marketplace = any(p in _MARKETPLACE_PATHS for p in paths)
    if has_marketplace:
        return "plugin", []
    skill_paths = [p for p in paths if os.path.basename(p).upper() == "SKILL.MD"]
    if skill_paths:
        return "skill", skill_paths
    return None, []


# --- skill entry 构造（复用 scan_repo_via_api + hard_filter）---------------

def build_skill_entries(repo_slug, branch, item, last_synced):
    """对一个 skill 仓扫描 SKILL.md 并构造 catalog skill entry 列表（已过 hard_filter）。

    复用 skill_registry.scan_repo_via_api（Tree+raw 解析 SKILL.md）与 hard_filter；
    entry schema 对齐 skill_registry.discover_skills（:269-308）。
    """
    parsed = skill_registry.scan_repo_via_api(repo_slug, branch)
    stars = int(item.get("stargazers_count") or 0)
    pushed_at = item.get("pushed_at") or ""
    owner, name = repo_slug.split("/", 1)
    entries = []
    for sk in parsed:
        source_url = f"https://github.com/{repo_slug}/tree/{branch}/{sk['skill_dir']}"
        candidate = {
            "id": f"{to_kebab_case(sk['name'])}-skill",
            "name": sk["name"],
            "type": "skill",
            "description": sk["description"],
            "source_url": source_url,
            "stars": stars,
            "pushed_at": pushed_at,
            "category": categorize(
                sk["name"], sk["description"], sk.get("tags"), sk.get("category", "")
            ),
            "tags": sk["tags"] if sk.get("tags") else extract_tags(sk["name"], sk["description"]),
            "tech_stack": [],
            "install": {
                "method": "git_clone",
                "repo": repo_slug,
                "branch": branch,
                "path": sk["skill_dir"],
            },
            "source": SOURCE_ID,
            "last_synced": last_synced,
        }
        # 预过滤已挡掉 Tier1 重复，这里 tier1 集合传空即可；只做 stars/spam/non-coding 把关。
        if skill_registry.hard_filter(candidate, stars, set(), set()) is None:
            entries.append(candidate)
    return entries


# --- merge-preserve 写入 ---------------------------------------------------

def merge_preserve(new_entries, existing_entries, dedup_url=True):
    """把 new_entries 追加到 existing_entries，按 id（+可选归一 source_url）去重。

    plugin 传 ``dedup_url=False``（同一 monorepo 多 plugin 合法共享 repo URL，
    对齐 deduplicate() 的 url_dedup_skip_types）。返回 ``(combined, accepted_count)``。
    """
    seen_ids = set()
    seen_urls = set()
    for e in existing_entries:
        if e.get("id"):
            seen_ids.add(e["id"])
        if dedup_url:
            nu = normalize_source_url(e.get("source_url") or "")
            if nu:
                seen_urls.add(nu)
    accepted = []
    for e in new_entries:
        eid = e.get("id") or ""
        if eid and eid in seen_ids:
            continue
        if dedup_url:
            nu = normalize_source_url(e.get("source_url") or "")
            if nu and nu in seen_urls:
                continue
            if nu:
                seen_urls.add(nu)
        if eid:
            seen_ids.add(eid)
        accepted.append(e)
    combined = list(existing_entries) + accepted
    combined.sort(key=lambda e: e.get("id", ""))
    return combined, len(accepted)


# --- 验证 cache（增量友好 + 不缓存空结果）---------------------------------

def load_verify_cache():
    if not os.path.exists(VERIFY_CACHE_PATH):
        return {}
    try:
        with open(VERIFY_CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def save_verify_cache(cache):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(VERIFY_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except OSError as e:
        logger.debug("verify cache 写入失败：%s", e)


# --- 主发现流程 ------------------------------------------------------------

def discover(last_synced, api=github_api, list_files=list_repo_files):
    """跑完整发现流程，返回 ``(skill_entries, plugin_repo_cfgs, stats)``。

    plugin 不在此构造 entry（schema 复杂，交给 sync_one_source），仅返回待同步的
    source_cfg 列表。
    """
    known = build_known_repos()
    logger.info("known_repos 预过滤集合大小：%d", len(known))

    cutoff = (datetime.now(timezone.utc) - timedelta(days=RECENCY_DAYS)).strftime("%Y-%m-%d")
    recency_query = f"topic:claude-code created:>{cutoff} stars:>{MIN_STARS}"
    skill_queries = SKILL_QUERIES + [recency_query]

    candidates, stats = collect_candidates(
        skill_queries + PLUGIN_QUERIES, known, api=api
    )
    logger.info(
        "发现：raw=%d，预过滤命中已知=%d，低于 %d star=%d，待验证唯一候选=%d",
        stats["raw"], stats["prefiltered_known"], MIN_STARS,
        stats["below_min_stars"], len(candidates),
    )

    verify_cache = load_verify_cache()
    new_cache = {}
    skill_entries = []
    plugin_cfgs = []
    stats.update({
        "skill_repos": 0, "plugin_repos": 0, "discarded": 0,
        "verify_failed": 0, "errored": 0,
    })

    for full, item in candidates.items():
        repo_slug = item.get("full_name")
        branch = item.get("default_branch") or "main"
        pushed_at = item.get("pushed_at") or ""

        # 单仓的结构验证 / SKILL.md 解析可能抛瞬时网络异常
        # （http.client.RemoteDisconnected 等）；隔离到 per-candidate try/except，
        # 单仓失败 → WARN + 计入 errored + 不写 new_cache（下次重试，不缓存失败结果），
        # 绝不让一个坏仓拖垮整个 discover()。
        try:
            cached = verify_cache.get(full)
            if cached and cached.get("pushed_at") == pushed_at and cached.get("kind"):
                kind, skill_paths = cached["kind"], []
            else:
                kind, skill_paths = classify_repo(repo_slug, branch, list_files)

            if kind == "plugin":
                stats["plugin_repos"] += 1
                plugin_cfgs.append({
                    "id": SOURCE_ID,
                    "repo_slug": repo_slug,
                    "branch": branch,
                    "source_priority": PLUGIN_SOURCE_PRIORITY,
                })
                new_cache[full] = {"pushed_at": pushed_at, "kind": "plugin"}
            elif kind == "skill":
                built = build_skill_entries(repo_slug, branch, item, last_synced)
                if built:
                    stats["skill_repos"] += 1
                    skill_entries.extend(built)
                    new_cache[full] = {"pushed_at": pushed_at, "kind": "skill"}
                else:
                    # 有 SKILL.md 但全被 hard_filter 刷掉 / 解析失败 → 不缓存空结果，下次重试
                    stats["verify_failed"] += 1
            else:
                stats["discarded"] += 1
                # 越界仓（无 SKILL.md/marketplace.json）：缓存为 discarded 避免反复 Tree
                new_cache[full] = {"pushed_at": pushed_at, "kind": "none"}
        except Exception as e:  # noqa: BLE001
            stats["errored"] += 1
            logger.warning("候选仓 %s 验证失败（跳过，下次重试）：%s", repo_slug, e)
            # 不写 new_cache → 不缓存失败结果，下个周期重新验证
            continue

    save_verify_cache(new_cache)
    return skill_entries, plugin_cfgs, stats


# --- plugin 同步（复用 sync_plugins_official.sync_one_source）---------------

def sync_plugins(plugin_cfgs, last_synced):
    """对发现的 plugin 仓复用官方 sync_one_source 构造 entry。返回 entry 列表。"""
    if not plugin_cfgs:
        return []
    layout_fetcher = None
    if spo.PluginContentFetcher is not None:
        try:
            layout_fetcher = spo.PluginContentFetcher()
        except Exception as e:  # noqa: BLE001
            logger.warning("PluginContentFetcher 初始化失败，bundle 字段置零：%s", e)
    plugin_blacklist = spo.load_plugin_blacklist()
    marketplace_cache = spo.marketplace_verifier.load_cache(spo.MARKETPLACE_CACHE_PATH)
    entries = []
    try:
        for cfg in plugin_cfgs:
            entries.extend(spo.sync_one_source(
                cfg, last_synced, layout_fetcher,
                plugin_blacklist=plugin_blacklist,
                marketplace_cache=marketplace_cache,
            ))
    finally:
        if layout_fetcher is not None:
            try:
                layout_fetcher.close()
            except Exception:  # noqa: BLE001
                pass
        spo.marketplace_verifier.save_cache(spo.MARKETPLACE_CACHE_PATH, marketplace_cache)
    return entries


# --- main ------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skills-output", default=SKILLS_INDEX)
    parser.add_argument("--plugins-output", default=PLUGINS_INDEX)
    parser.add_argument("--dry-run", action="store_true",
                        help="只发现+打印统计，不写 index")
    args = parser.parse_args(argv)

    last_synced = date.today().isoformat()

    try:
        skill_entries, plugin_cfgs, stats = discover(last_synced)
    except RuntimeError as e:
        logger.error("发现流程中止：%s", e)
        return 1

    plugin_entries = sync_plugins(plugin_cfgs, last_synced)

    # WARN 汇总：让一次发现的健康度在 CI 日志可见（不静默）。
    logger.warning(
        "GitHub trending 发现健康度：skill 仓=%d（%d 条 entry）｜plugin 仓=%d（%d 条 entry）"
        "｜丢弃越界=%d｜验证未产出=%d｜验证异常=%d｜预过滤已知=%d",
        stats["skill_repos"], len(skill_entries), stats["plugin_repos"],
        len(plugin_entries), stats["discarded"], stats["verify_failed"],
        stats["errored"], stats["prefiltered_known"],
    )

    if args.dry_run:
        logger.info("--dry-run：跳过写入")
        return 0

    # merge-preserve 写 skills
    if skill_entries:
        existing = load_index(args.skills_output) if os.path.exists(args.skills_output) else []
        combined, accepted = merge_preserve(skill_entries, existing, dedup_url=True)
        if accepted:
            save_index(combined, args.skills_output)
        logger.info("skills：合并写入 %d 条新 entry（共 %d）", accepted, len(combined))

    # merge-preserve 写 plugins（id-only dedup）
    if plugin_entries:
        existing = load_index(args.plugins_output) if os.path.exists(args.plugins_output) else []
        combined, accepted = merge_preserve(plugin_entries, existing, dedup_url=False)
        if accepted:
            save_index(combined, args.plugins_output)
        logger.info("plugins：合并写入 %d 条新 entry（共 %d）", accepted, len(combined))

    return 0


if __name__ == "__main__":
    sys.exit(main())
