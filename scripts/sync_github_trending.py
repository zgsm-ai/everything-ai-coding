#!/usr/bin/env python3
"""GitHub Search 主动发现源（Stage A：纯搜索）—— 把"按 stars 从 GitHub 搜索发现
热门 skill/plugin 仓"固化成一个 sync 源，补上"发现完全依赖上游 curated 白名单/
registry 先收录"的盲区。

**分阶段架构（防 CI 超时）**：本脚本只做 Stage A（纯搜索，**零 Tree API**），把候选表
落到 .github_trending_cache/candidates.json，交给 scripts/triage_github_trending.py
做 Stage B（拉树前的 plugin 探测 + LLM 真伪判别）+ Stage C（仅存活者深拉构造 entry）。

根因：旧版 discover() 对**每个**候选拉整棵递归 Tree（含 openclaw 2 万文件巨型 app），
21 分钟全耗在"拉巨树只为丢掉它"，写盘在最后被 kill → 全丢。Stage A 退化为纯搜索后
不拉任何 Tree，秒级完成；昂贵的判别 + 深拉移到 triage（带 LLM、独立 timeout、
增量写 + wall-clock 预算）。

Stage A 数据流：
    GitHub Search (repo) 按 stars 召回候选仓
      → known_repos 预过滤（已存在于任意 type/source 的仓直接挡掉）
      → MIN_STARS 过滤 + 按 stars 降序 + 每轮限量 MAX_VERIFY
      → 写候选表 candidates.json（每条含 full_name/stars/default_branch/
        pushed_at/topics/description），**不拉任何 Tree**

去重设计：repo 级 known_repos 预过滤是主防线（既省 API/LLM，又物理杜绝
deduplicate() 因 type 分命名空间而抓不住的跨类型重复）；merge 阶段 deduplicate() 兜底。
详见 .trellis/tasks/06-16-.../research/dedup-analysis.md。

依赖：**仅标准库** + 本仓 utils/skill_registry/sync_plugins_official。Stage C 深拉所需
的构造器（classify_repo / build_skill_entries / merge_preserve / sync_plugins）仍定义
在本模块，供 triage_github_trending.py import 复用；本脚本 main() 不再调用它们。
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
    normalize_source_url,
    to_kebab_case,
    categorize,
    extract_tags,
    filter_canonical_skill_paths,
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
# Stage A 产物：候选表（中间表），由 triage_github_trending.py 消费。
CANDIDATES_PATH = os.path.join(CACHE_DIR, "candidates.json")

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
# 每轮限量：Stage A 本轮只把 stars 最高的前 N 个 net-new 候选写进候选表交 triage。
# 单轮 triage 能在 CI timeout 内跑完 → 正常写 index → known_repos 下轮自动跳过它们、
# 推进 backlog。~1191 候选几轮内排空，新爆款每周补入。env 可覆盖。
MAX_VERIFY = int(os.environ.get("TRENDING_MAX_VERIFY", "300"))
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

# Part 1 廉价预过滤：把"恰好捆了 skill 的巨型 app/agent/framework"挡在 LLM 之前。
# 验证时整棵树已 fetch，total_files + SKILL.md 数是免费信号，密度(‰)无需额外 API。
#
# 阈值由实测样本校准（见 task PRD）：
#   app   openclaw(20116 文件,113 SKILL.md,5.6‰) / hermes-agent(5122,174,34‰)
#         / deer-flow(1323,25,18.9‰)
#   skill graphify(579,1,1.7‰) / gstack(1162,59,50.8‰) / taste(41,13,317‰)
#         / anthropics-skills(398,18,45.2‰)
# 结论：openclaw 应丢，其余应保留 → 只在"文件极多 + 密度极低 + 无 skill/plugin topic"
# 三条件全满足时才丢。hermes-agent(密度34‰)/deer-flow(文件1323)等模糊样本放行交 LLM。
MEGAAPP_FILE_THRESHOLD = int(os.environ.get("TRENDING_MEGAAPP_FILES", "2000"))
MEGAAPP_DENSITY_THRESHOLD = float(os.environ.get("TRENDING_MEGAAPP_DENSITY", "10.0"))  # ‰

# 强 skill/plugin topic 正信号：命中任一则即便像 app 也不丢（topic override）。
_SKILL_PLUGIN_TOPICS = {
    "claude-skill", "claude-skills", "agent-skill", "agent-skills",
    "claude-plugin", "claude-plugins", "claude-code-plugin", "skill", "skills",
}

# 次要负信号：仓库自述为 app/agent/harness/client/proxy/framework/IDE/desktop。
# 仅作辅助记录（不单独触发丢弃；丢弃由"文件数+密度+无正 topic"三件套决定）。
_APP_DESC_RE = re.compile(
    r"\b("
    r"application|app|agent|agentic|harness|framework|"
    r"cli\b|client|proxy|gateway|server|daemon|"
    r"ide\b|editor|desktop[- ]?app|platform|runtime|orchestrat\w*"
    r")\b",
    re.IGNORECASE,
)


def _skill_density_permille(total_files, skill_count):
    """SKILL.md 在整棵树里的密度（‰）。total_files=0 视作 0 密度。"""
    if not total_files:
        return 0.0
    return skill_count / total_files * 1000.0


def _has_skill_plugin_topic(topics):
    """topics 里是否有强 skill/plugin 正信号（用于 megaapp override）。"""
    for tp in topics or []:
        if (tp or "").strip().lower() in _SKILL_PLUGIN_TOPICS:
            return True
    return False


def is_megaapp(total_files, skill_count, topics, description=""):
    """判定是否"明显的巨型 app/agent（恰好捆了 skill）"——保守只丢明确样本。

    丢弃条件（全满足）：
      1. total_files > MEGAAPP_FILE_THRESHOLD（默认 2000）
      2. 密度 < MEGAAPP_DENSITY_THRESHOLD ‰（默认 10）
      3. 无强 skill/plugin topic（有则正信号 override，不丢）

    description self-describe 为 app/agent 等只是辅助负信号，不单独触发——
    避免把"description 含 framework 但其实是真 skill 集合"的仓误杀。
    实测：openclaw 被丢；graphify/gstack/anthropics-skills/taste/hermes-agent/
    deer-flow 全保留。
    """
    if _has_skill_plugin_topic(topics):
        return False  # 强正信号 override
    if total_files <= MEGAAPP_FILE_THRESHOLD:
        return False
    density = _skill_density_permille(total_files, skill_count)
    if density >= MEGAAPP_DENSITY_THRESHOLD:
        return False
    return True


def classify_repo(repo_slug, branch, api_list_files=list_repo_files):
    """用一次 Tree API 调用判定仓库结构属性。

    返回 ``("plugin"|"skill"|None, skill_paths, meta)``：
      - 含 .claude-plugin/marketplace.json（或根 marketplace.json）→ "plugin"（优先，
        其 bundled skill 由下游 merge 合成，避免与 standalone skill 双重收录）
      - 否则含任意 SKILL.md → "skill"
      - 都没有 → None（越界工具天然落此）
    ``meta`` = ``{"total_files": int, "skill_count": int}``，供 Part 1 megaapp
    预过滤复用（树已 fetch，这些数字是免费的）。``api_list_files`` 可注入便于测试。
    """
    paths = api_list_files(repo_slug, branch) or []
    total_files = len(paths)
    skill_paths = [p for p in paths if os.path.basename(p).upper() == "SKILL.MD"]
    # Drop localized/translated SKILL.md copies (e.g. docs/<locale>/skills/...).
    # Use the canonical count for both megaapp density and downstream scanning so
    # a multilingual repo (e.g. affaan-m/ECC) is not credited N× its real skills.
    skill_paths = filter_canonical_skill_paths(skill_paths)
    meta = {"total_files": total_files, "skill_count": len(skill_paths)}
    has_marketplace = any(p in _MARKETPLACE_PATHS for p in paths)
    if has_marketplace:
        return "plugin", [], meta
    if skill_paths:
        return "skill", skill_paths, meta
    return None, [], meta


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


# --- Stage A：纯搜索发现（零 Tree）-----------------------------------------

def discover_candidates(api=github_api, max_verify=None):
    """Stage A：纯搜索发现候选表，**零 Tree API**。返回 ``(candidates, stats)``。

    candidates 是 ``list[dict]``，每条含 search item 自带的零成本字段
    （``full_name`` / ``stargazers_count`` / ``default_branch`` / ``pushed_at`` /
    ``topics`` / ``description``），按 stars 降序、每轮限量到前 ``max_verify``。
    昂贵的结构验证 + LLM 判别 + 深拉全部移到 triage_github_trending.py。

    **每轮限量**（主修超时）：net-new 候选按 stars 降序，本轮只交前 ``max_verify``
    （默认 ``MAX_VERIFY``=300）给 triage。高星优先；下轮 known_repos 已含本轮入库的，
    自动推进 backlog。``max_verify=0`` 表示不限量（全量）。
    """
    if max_verify is None:
        max_verify = MAX_VERIFY
    known = build_known_repos()
    logger.info("known_repos 预过滤集合大小：%d", len(known))

    cutoff = (datetime.now(timezone.utc) - timedelta(days=RECENCY_DAYS)).strftime("%Y-%m-%d")
    recency_query = f"topic:claude-code created:>{cutoff} stars:>{MIN_STARS}"
    skill_queries = SKILL_QUERIES + [recency_query]

    candidates_map, stats = collect_candidates(
        skill_queries + PLUGIN_QUERIES, known, api=api
    )
    logger.info(
        "Stage A 发现：raw=%d，预过滤命中已知=%d，低于 %d star=%d，唯一候选=%d",
        stats["raw"], stats["prefiltered_known"], MIN_STARS,
        stats["below_min_stars"], len(candidates_map),
    )

    # 按 stars 降序排序后只取前 max_verify 个。高星优先交 triage，其余推迟到后续轮次。
    ranked = sorted(
        candidates_map.values(),
        key=lambda it: (it.get("stargazers_count") or 0),
        reverse=True,
    )
    total_candidates = len(ranked)
    stats["deferred"] = 0
    if max_verify and total_candidates > max_verify:
        stats["deferred"] = total_candidates - max_verify
        logger.info(
            "本轮限量 %d，推迟 %d 个到后续轮次（按 stars 降序，高星优先）",
            max_verify, stats["deferred"],
        )
        ranked = ranked[:max_verify]

    # 候选表只保留 triage 需要的零成本字段（不拉任何 Tree）。
    candidates = [
        {
            "full_name": it.get("full_name"),
            "stars": int(it.get("stargazers_count") or 0),
            "default_branch": it.get("default_branch") or "main",
            "pushed_at": it.get("pushed_at") or "",
            "topics": it.get("topics") or [],
            "description": it.get("description") or "",
        }
        for it in ranked
        if it.get("full_name")
    ]
    stats["candidates"] = len(candidates)
    return candidates, stats


def save_candidates(candidates, path=CANDIDATES_PATH):
    """把候选表落盘为 JSON（中间表，供 triage 消费）。"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(candidates, f, ensure_ascii=False, indent=2)


def load_candidates(path=CANDIDATES_PATH):
    """读取 Stage A 产出的候选表；缺失 / 损坏返回空列表。"""
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


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
    """Stage A 入口：纯搜索 → 写候选表 candidates.json。**不拉任何 Tree、不写 index。**

    昂贵的判别 + 深拉 + 写 index 由 scripts/triage_github_trending.py 承接。
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates-output", default=CANDIDATES_PATH,
                        help="候选表落盘路径（中间表，供 triage 消费）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只发现+打印统计，不写候选表")
    args = parser.parse_args(argv)

    # 提前建 cache 目录：即便发现流程早退（如 build_known_repos raise），CI 的
    # cache save step 也有目录可存，避免 "Cache save failed" annotation。
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
    except OSError as e:
        logger.debug("cache 目录创建失败：%s", e)

    try:
        candidates, stats = discover_candidates()
    except RuntimeError as e:
        logger.error("Stage A 发现流程中止：%s", e)
        return 1

    # WARN 汇总：让一次发现的健康度在 CI 日志可见（不静默）。
    logger.warning(
        "GitHub trending Stage A 发现健康度：raw=%d｜预过滤已知=%d｜低于%dstar=%d"
        "｜本轮候选=%d｜推迟=%d",
        stats["raw"], stats["prefiltered_known"], MIN_STARS,
        stats["below_min_stars"], stats.get("candidates", 0),
        stats.get("deferred", 0),
    )

    if args.dry_run:
        logger.info("--dry-run：跳过写候选表")
        return 0

    save_candidates(candidates, args.candidates_output)
    logger.info("Stage A：候选表写入 %d 条 → %s", len(candidates), args.candidates_output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
