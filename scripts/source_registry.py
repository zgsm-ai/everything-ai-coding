#!/usr/bin/env python3
"""上游源权威清单（单一真相）。

About 页"数据源 / 信任分级"两个区块过去是前端 ``About.tsx`` 手敲的静态
常量，源演进后没人回来同步，导致展示与真实 sync 源漂移（典型例子：
``antigravity-skills`` 的 URL 一度指向已删除的 ``antigravities/...`` 404 库，
真实源其实是 ``sickn33/antigravity-awesome-skills``）。

为根治漂移，这里维护一份权威清单：``catalog`` 的 ``source`` slug → 源仓库
URL / 展示名 / 类型 / 信任分级。``build_frontend_data.build_sources`` 读它，
join ``catalog/index.json`` 实时聚合的 entry 计数，产出
``frontend/public/api/sources.json``，前端只负责渲染。

维护约定：
- key 必须等于 sync 脚本写入 entry 的 ``source`` 字段值（不是源仓库 owner/repo，
  因为 entry 的 ``source_url`` 是被收录条目的深链，不是源仓库地址本身）。
- ``trust`` 1–5，对齐 health 信号 source_trust 的人工分级（5=官方/最高，
  2=第三方目录/最低）。镜像源（如 sickn33）按镜像信任度给 3。
- 真实在跑但被 dedup collapse、当周期 count 归零的源（如部分 registry/windsurf）
  仍登记在册，``count == 0`` 时不输出，数据回来后自动出现。
"""

import json
import logging
import os
from collections import Counter

logger = logging.getLogger("source_registry")

# 类型展示顺序（对齐 About 页原排版）
TYPE_ORDER = ["MCP", "Skills", "Rules", "Prompts", "Plugins"]

# 促升清单 entry 的小写 type（skill/plugin）→ About 页 TYPE_ORDER 展示 type。
_PROMOTE_TYPE_TO_DISPLAY = {"skill": "Skills", "plugin": "Plugins"}
# 促升清单路径（与 sync_github_trending.PROMOTED_REPOS_PATH 同一文件，DRY 单一真相）。
_PROMOTED_REPOS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "trending_promoted_repos.json"
)

# trust 分值 → 信任分级展示元数据（颜色沿用前端 TRUST_LEVELS 原值）
TIER_META = {
    5: {"label": "Tier 1", "color": "#30d158"},
    4: {"label": "Tier 2", "color": "#0071e3"},
    3: {"label": "Tier 3", "color": "#ff9f0a"},
    2: {"label": "Tier 4", "color": "#ff453a"},
}

# catalog source slug → 源元信息
SOURCE_REGISTRY: dict[str, dict] = {
    # ── MCP ──
    "awesome-mcp-servers": {
        "label": "awesome-mcp-servers",
        "url": "https://github.com/wong2/awesome-mcp-servers",
        "type": "MCP",
        "trust": 4,
    },
    "awesome-mcp-zh": {
        "label": "Awesome-MCP-ZH",
        "url": "https://github.com/yzfly/Awesome-MCP-ZH",
        "type": "MCP",
        "trust": 3,
    },
    "mcp.so": {
        "label": "mcp.so",
        "url": "https://mcp.so",
        "type": "MCP",
        "trust": 2,
    },
    "mcp-registry": {
        "label": "MCP Registry",
        "url": "https://registry.modelcontextprotocol.io",
        "type": "MCP",
        "trust": 5,
    },
    # ── Skills ──
    "anthropics-skills": {
        "label": "Anthropic Skills",
        "url": "https://github.com/anthropics/skills",
        "type": "Skills",
        "trust": 5,
    },
    "ai-agent-skills": {
        "label": "Ai-Agent-Skills",
        "url": "https://github.com/skillcreatorai/Ai-Agent-Skills",
        "type": "Skills",
        "trust": 3,
    },
    "antigravity-skills": {
        # 真实源是 sickn33 镜像，不是已删除的 antigravities/awesome-claude-code-skills
        "label": "antigravity-skills",
        "url": "https://github.com/sickn33/antigravity-awesome-skills",
        "type": "Skills",
        "trust": 3,
    },
    "vasilyu-skills": {
        "label": "ai-agents-public",
        "url": "https://github.com/vasilyu1983/ai-agents-public",
        "type": "Skills",
        "trust": 3,
    },
    "davila7/claude-code-templates": {
        "label": "claude-code-templates",
        "url": "https://github.com/davila7/claude-code-templates",
        "type": "Skills",
        "trust": 3,
    },
    "skills.sh": {
        "label": "skills.sh",
        "url": "https://skills.sh",
        "type": "Skills",
        "trust": 4,
    },
    "claude-office-skills": {
        "label": "claude-office-skills",
        "url": "https://github.com/claude-office-skills/skills",
        "type": "Skills",
        "trust": 3,
    },
    "composio-office": {
        # ComposioHQ/awesome-claude-skills 原创子集（文档/办公），仓库无 SPDX license
        "label": "awesome-claude-skills",
        "url": "https://github.com/ComposioHQ/awesome-claude-skills",
        "type": "Skills",
        "trust": 2,
    },
    # ── Rules ──
    "awesome-cursorrules": {
        "label": "awesome-cursorrules",
        "url": "https://github.com/PatrickJS/awesome-cursorrules",
        "type": "Rules",
        "trust": 4,
    },
    "rules-2.1-optimized": {
        "label": "Rules 2.1",
        "url": "https://github.com/Mr-chen-05/rules-2.1-optimized",
        "type": "Rules",
        "trust": 3,
    },
    "windsurfrules": {
        "label": "awesome-windsurfrules",
        "url": "https://github.com/SchneiderSam/awesome-windsurfrules",
        "type": "Rules",
        "trust": 3,
    },
    # ── Prompts ──
    "prompts-chat": {
        "label": "prompts.chat",
        "url": "https://github.com/f/prompts.chat",
        "type": "Prompts",
        "trust": 4,
    },
    "wonderful-prompts": {
        "label": "wonderful-prompts",
        "url": "https://github.com/langgptai/wonderful-prompts",
        "type": "Prompts",
        "trust": 3,
    },
    # ── Plugins ──
    "claude-plugins-official": {
        "label": "Anthropic Plugins",
        "url": "https://github.com/anthropics/claude-plugins-official",
        "type": "Plugins",
        "trust": 5,
    },
    "superpowers-marketplace": {
        "label": "superpowers-marketplace",
        "url": "https://github.com/obra/superpowers-marketplace",
        "type": "Plugins",
        "trust": 4,
    },
    "claude-plugins-dev": {
        "label": "claude-plugins.dev",
        "url": "https://claude-plugins.dev",
        "type": "Plugins",
        "trust": 3,
    },
    # ── 主动发现（跨类型）──
    # github-trending 同时产 skill + plugin，但 SOURCE_REGISTRY schema 假设单一
    # type（`type` 仅用于 About 页的 TYPE_ORDER 分组排序，必须是已知值）。
    # 这里按"主体是 skill 发现"归到 Skills，避免 build_sources_payload 在
    # TYPE_ORDER.index() 处抛 ValueError、破坏 About 页渲染；trust=2（自动发现、
    # 未策展，最低档）。多 type 精确归属属后续 schema 扩展，不在本任务范围。
    "github-trending": {
        "label": "GitHub Trending",
        "url": "https://github.com/search",
        "type": "Skills",
        "trust": 2,
    },
}


def _register_promoted_sources(registry: dict[str, dict], path: str = _PROMOTED_REPOS_PATH) -> None:
    """把 ``trending_promoted_repos.json`` 里每个促升仓登记进 ``registry``（DRY）。

    促升仓从统一 github-trending 切到专属 per-repo source slug；为了 About 页能展示
    它们，每个 slug 必须登记进 ``SOURCE_REGISTRY``，key **逐字等于** entry 写入的
    ``source`` 值（清单里的小写 ``source_slug``）。直接读促升清单生成 entry，避免与
    清单两处漂移。文件缺失 / 损坏 → 跳过（不崩，About 页仅少展示几个源）。
    """
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:  # noqa: BLE001
        logger.warning("促升清单读取失败，跳过登记：%s", e)
        return
    raw = data.get("repos") if isinstance(data, dict) else data
    if not isinstance(raw, list):
        return
    for item in raw:
        if not isinstance(item, dict):
            continue
        slug = (item.get("source_slug") or "").strip()
        rtype = (item.get("type") or "").strip()
        if not slug or rtype not in _PROMOTE_TYPE_TO_DISPLAY:
            continue  # schema 校验由 sync_github_trending.load_promoted_repos 兜底
        registry[slug] = {
            "label": (item.get("label") or "").strip() or slug,
            "url": (item.get("url") or "").strip() or f"https://github.com/{item.get('repo', slug)}",
            "type": _PROMOTE_TYPE_TO_DISPLAY[rtype],
            "trust": int(item.get("trust") or 3),
        }


# 促升仓批量登记（key 逐字等于促升清单的小写 source_slug，与 entry 写入值对齐）。
_register_promoted_sources(SOURCE_REGISTRY)


def build_sources_payload(items: list[dict]) -> dict:
    """从 catalog items 聚合源计数，产出 sources.json 的 payload。

    返回 ``{"sources": [...], "tiers": [...]}``：
    - ``sources`` — registry 中 ``count > 0`` 的源，按类型顺序 + count 降序。
    - ``tiers`` — 按 trust 分值聚合的信任分级（驱动 About 的"信任分级"区块）。

    registry 未覆盖、但 catalog 里实际出现的 source（零散 Tier 2/3 收录）会打
    WARNING 但不展示——提醒维护者按需补登记，避免边角源污染展示。
    """
    counts = Counter(i.get("source", "") for i in items)

    sources = []
    for slug, meta in SOURCE_REGISTRY.items():
        n = counts.get(slug, 0)
        if n == 0:
            continue  # 真实未入库（被 collapse / 本周期未跑），不展示
        sources.append(
            {
                "slug": slug,
                "name": meta["label"],
                "url": meta["url"],
                "type": meta["type"],
                "trust": meta["trust"],
                "count": n,
            }
        )

    sources.sort(key=lambda s: (TYPE_ORDER.index(s["type"]), -s["count"]))

    # 信任分级：按 trust 分组（仅含实际展示的源）
    by_trust: dict[int, list[str]] = {}
    for s in sources:
        by_trust.setdefault(s["trust"], []).append(s["slug"])
    tiers = []
    for score in sorted(TIER_META, reverse=True):
        if score in by_trust:
            tiers.append(
                {
                    "score": score,
                    "label": TIER_META[score]["label"],
                    "color": TIER_META[score]["color"],
                    "sources": by_trust[score],
                }
            )

    # registry 未覆盖的实际源 → WARN（不阻断）
    unknown = sorted(s for s in counts if s and s not in SOURCE_REGISTRY)
    for u in unknown:
        print(
            f"  WARNING: source '{u}' (n={counts[u]}) 不在 SOURCE_REGISTRY，未展示于 sources.json"
        )

    return {"sources": sources, "tiers": tiers}
