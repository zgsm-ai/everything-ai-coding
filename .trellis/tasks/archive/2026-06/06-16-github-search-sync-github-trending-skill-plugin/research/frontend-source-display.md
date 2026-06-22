# Research: 前端如何展示 source + 给 github-trending 加视觉标识

- **Query**: 前端目前如何展示一个 catalog entry 的 `source`，给新的 `github-trending`（主动发现）源加视觉标识需要改什么
- **Scope**: internal（前端 React 代码 + 数据生成脚本）
- **Date**: 2026-06-16

## 关键事实速览

- `github-trending` 已是 sync 端写入的 `source` 值：`scripts/sync_github_trending.py:79` `SOURCE_ID = "github-trending"`。
  - skill entry：`scripts/sync_github_trending.py:262` 直接写 `"source": SOURCE_ID`。
  - plugin entry：trending 复用官方 plugin sync（`sync_plugins` → `spo.sync_one_source`，`sync_github_trending.py:413`），cfg 的 `id` 设为 `SOURCE_ID`（`:372`），而官方 plugin sync 用 `"source": source_cfg["id"]`（`scripts/sync_plugins_official.py:784`）→ 两类 entry 都带 `source == "github-trending"`。
- 当前 catalog 里 `github-trending` count = 0（尚未跑入库；本机已有 `.github_trending_cache/`）。
- `github-trending` **未登记** 进 `scripts/source_registry.py`（grep 确认 NOT FOUND）→ About 页"数据源/信任分级"两个区块不会显示它，且 `build_sources_payload` 会对它打 WARNING（`source_registry.py:202-206`）。

---

## Findings

### 1. source 在哪渲染

**ResourceCard（列表卡片）— `frontend/src/components/ResourceCard.tsx`**
- `source` 只在 rule/prompt 且无 star 时当 fallback 角标显示，其它类型不显示 source：
  - `:122-127` `{(item.type === 'rule' || item.type === 'prompt') && (!item.stars || item.stars === 0) && item.source && (<span>{item.source}</span>)}`
- 卡片左上角徽章区（`:68-91`）现有 source 相关信号：
  - type 徽章（`:70-72`，颜色表 `TYPE_COLORS` 在 `:5-11`，emoji 在 `TYPE_ICONS :13-19`）。
  - `freshness_label`（`:73-81`，读 `item.health?.freshness_label`，active/recent/stale 三色）。
  - plugin "unverified" 角标（`:50-55` `showUnverified = item.type === 'plugin' && item.install?.marketplace_verified === false`，渲染在 `:82-90`，amber 胶囊 + tooltip）。
- 卡片右上角（`:92-128`）：security shield（`:45-46` risk_level ≥ medium 才显示，emoji map `:61`）、bundled_in 🧩 按钮（`:102-116`）、stars（`:117-121`）。
- `final_score` 进度条（`:140-147`），category 胶囊（`:150-156`）。
- **结论**：卡片上没有"按 source 渲染的徽章"（除 rule/prompt 的纯文本 fallback）。trending 角标会是新增的视觉元素。

**Detail（详情页）— `frontend/src/pages/Detail.tsx`**
- source 以纯文本 chip 显示在 metadata chips 区：`:129-133` `{item.source && (<span>{t('detail.source')}: {item.source}</span>)}`，i18n key `detail.source`（en `Source` / zh `来源`，`frontend/src/hooks/useI18n.tsx:45`）。
- 其它 source 相关：freshness_label chip（`:134-142`）、last_commit（`:143-147`）、security banner（`:179`）、plugin unverified install 块（`:443-465`）。
- Detail 取数双路径：先并行拉 5 个 per-type JSON（`:20-32`），找不到再 fallback 到 `search-index.json`（`:34-49`，注意 `SearchIndexItem` cast 成 `CatalogItem`）。

**来源 display-name 映射在哪**
- **唯一权威映射**：`scripts/source_registry.py:37-152` `SOURCE_REGISTRY`，slug → `{label, url, type, trust}`。例如 `"skills.sh" → label "skills.sh"`、`"claude-plugins-official" → "Anthropic Plugins"`。
- 该映射只供 **About 页**（`build_sources_payload` → `frontend/public/api/sources.json` → `frontend/src/pages/About.tsx:380-398` 渲染数据源列表，`:357-378` 渲染信任分级）。
- ResourceCard/Detail **不读** 这个映射，直接显示原始 `item.source` slug 文本。
- `generate_featured.py` / `update_readme.py` 是否也有同类映射：本次未读到（任务里提到的 `everything-claude-code → Everything Claude Code` 映射应在 source_registry.py 体系里，trending 走的是 `SOURCE_REGISTRY` 这一份）。

### 2. 有没有按 source 的筛选 / facet

**没有 source facet。** Browse 页（`frontend/src/pages/Browse.tsx`）只有三种 filter：
- type tabs（`:9` `TYPES = ['all','mcp','skill','rule','prompt','plugin']`，渲染 `:157-171`）。
- category 下拉（`:10-13` `CATEGORIES`，渲染 `:174-184`）。
- sort（`:188` `['score','stars']`）。
- 过滤逻辑 `filtered` useMemo（`:71-95`）只按 type/category/搜索词过滤，**没有任何 source 维度**。
- 数据来源：按 type 拉 `./api/{type}s.json`（`:46-57`），这些文件由 `build_frontend_data.build_type_files` 产出，`slim_item` 已带 `source`（见下）。

About 页信任分级标签长这样：`About.tsx:369-373` 每个 tier 把 `tier.sources`（slug 数组）渲染成 `font-mono` 灰色胶囊，配 `TrustDot`（`:96-109`）。

### 3. 哪些字段驱动角标 / search-index 透传

**per-type JSON（browse 卡片主数据）— `scripts/build_frontend_data.py:70-125` `slim_item`**
- `source` **已透传**：`:83` `"source": item.get("source", "")`。
- 同时带：`final_score`/`decision`/`health`（含 freshness_label）/`install`（plugin 的 `marketplace_verified` 在完整 install 对象里）/`security`/`bundled_in`/`highlights`/`tags`/`tech_stack` 等。
- plugin 专属：`:100-104` 透传 `marketplace_url/platforms/bundle/manifest_completeness`。
- **结论**：browse 卡片这条路径下，`item.source === "github-trending"` 前端已经能读到，无需改 slim_item。

**search-index.json（Detail fallback + 客户端搜索）— `scripts/merge_index.py:1062-1094`**
- `SEARCH_INDEX_FIELDS`（`:1063-1067`）：`id,name,type,category,tags,tech_stack,stars,description,description_zh,source_url,final_score,decision,freshness_label,bundled_in`。
- **`source` 不在其中！** 还额外注入 `install_method`（`:1072`）和 plugin 的 `install.marketplace_verified` 子对象（`:1076-1079`）。
- 前端 `SearchIndexItem` 类型（`frontend/src/types.ts:123-138`）也确认无 `source`。
- **结论**：bundled-only 或仅在 search-index 里的 entry，前端 fallback 取不到 `source`。trending entry 若也只活在 search-index（理论上不会，trending 是顶层 skill/plugin，会进 per-type JSON），角标会缺失。**要让 search-index fallback 也显示 trending 角标，需把 `source` 加进 `SEARCH_INDEX_FIELDS`。**

**第二份 search-index（GitHub Pages 静态 API）— `scripts/generate_pages.py:30-50`**
- 独立的 `SEARCH_INDEX_FIELDS`（`:30-33`），同样无 `source`。但 `generate_pages.py` 的 per-entry `{id}.json`（`:98-103`）写的是**完整 entry**（含 source），per-type `index.json`（`make_lightweight :43-50`）只取那 10 个字段、无 source。这套是 `docs/api/v1/` 的备用静态 API，前端当前主路径走 `frontend/public/api/`（build_frontend_data 产出）。

### 4. 加 github-trending 标识的最小改动

#### 数据侧（按方案不同，0–2 处脚本改动）

| 改动点 | 文件:行 | 何时需要 |
|---|---|---|
| `slim_item` 已透传 `source` | `build_frontend_data.py:83` | 已就绪，browse 卡片方案**无需改** |
| 把 `source` 加进 search-index 字段 | `merge_index.py:1063-1067` | 仅当要让 Detail fallback / 客户端搜索结果也带 trending 角标 |
| 把 `github-trending` 登记进 `SOURCE_REGISTRY` | `source_registry.py:37-152`（追加一条，需给 `label`/`url`/`type`/`trust`；注意它假设单 type，trending 同时产 skill+plugin → 可能要拆 2 条 slug 或扩展 schema） | 仅 About 页"数据源/信任分级"区块方案；不登记会持续打 WARNING |
| `generate_pages.py` 的 SEARCH_INDEX_FIELDS | `generate_pages.py:30-33` | 仅当 docs/api 静态 API 也要带 source |

#### 前端侧（按方案不同）

| 组件 | 文件:行 |
|---|---|
| ResourceCard 角标区（左上） | `ResourceCard.tsx:68-91`（紧挨现有 unverified 角标 `:82-90`） |
| Detail metadata chip 区 | `Detail.tsx:122-148`（source chip 在 `:129-133`） |
| i18n 文案 | `frontend/src/hooks/useI18n.tsx`（参照现有 `detail.source :45`、`trending.title :24`，新增 `source.trending` / tooltip key） |
| Browse facet（若做 source 过滤） | `Browse.tsx:9-13`（filter 常量）+ `:71-95`（filtered 逻辑）+ `:155-202`（filter UI） |

#### 三个具体展示方案

**方案 A — ResourceCard "trending 火苗" 角标（最小、推荐）**
- 数据流：零脚本改动（`slim_item` 已带 source）。只动前端。
- 前端：在 `ResourceCard.tsx:82-90` 现有 unverified 角标旁，加一个条件块
  `const showTrending = item.source === 'github-trending'`，渲染 🔥/⚡ 胶囊（复用现有 `text-xs px-1.5 py-0.5 rounded-full` 样式 + orange/amber 配色，对齐 `:74-80` freshness 的视觉语言），tooltip 走新 i18n key（en "Auto-discovered from GitHub trending" / zh "GitHub 趋势主动发现"）。
- 代价：Detail fallback 路径（search-index）不显示——但 trending 顶层 entry 会进 per-type JSON，实际 Detail 主路径（`Detail.tsx:20-32`）能读到 source，影响很小。
- 若要 Detail 也显示：在 `Detail.tsx:129-133` source chip 上加同样的条件着色，并把 `source` 补进 `merge_index.py:1063-1067` 兜底 fallback。

**方案 B — Detail "auto-discovered 提示条"（信息更重）**
- 数据流：建议把 `source` 补进 `merge_index.py:1063` `SEARCH_INDEX_FIELDS`（否则 fallback 路径拿不到），并同步 `frontend/src/types.ts:123-138` `SearchIndexItem` 加 `source`。
- 前端：在 `Detail.tsx` header 下方（约 `:120` 描述之后、`:122` chips 之前）加一个 glass 提示条（仿 `:286-296` bundled-in 提示条结构），文案说明"该资源由 GitHub trending 主动发现，非人工 curated 源，质量以评分为准"。
- 代价：改动跨 3 文件（merge_index + types + Detail），视觉最显眼。

**方案 C — Browse 新增 "Trending / 主动发现" facet**
- 数据流：`source` 已在 per-type JSON（`build_frontend_data.py:83`），browse 主路径够用；搜索结果路径若也要过滤需补 `merge_index.py:1063` 的 source。
- 前端：在 `Browse.tsx` 加第四个 filter（类似 `:174-184` category 下拉，或一个独立 toggle "Curated / Trending / All"），`filtered` useMemo（`:71-95`）里加 `result.filter(i => i.source === 'github-trending')` 分支。
- 可选搭配把 `github-trending` 登记进 `source_registry.py:37-152`，让 About 页也出现该源（注意 trending 同时产 skill+plugin，单条 registry entry 的 `type` 字段是单值，需评估拆 2 个 slug 还是扩 schema）。
- 代价：交互最完整，但 facet UI + filter 逻辑改动量最大。

## Caveats / Not Found

- `source_registry.py` 的 schema 假设每个 source 单一 `type`（MCP/Skills/Rules/...），但 `github-trending` 同时产出 skill 和 plugin。若走方案 C 的 About 登记，需决定：拆成 `github-trending-skill` / `github-trending-plugin` 两个 slug（但 entry 的 `source` 字段统一是 `github-trending`，对不上），或扩展 `build_sources_payload`（`source_registry.py:155-208`）支持多 type / 按实际 count 分组。这是登记路线的真实摩擦点。
- 未读 `generate_featured.py` / `update_readme.py` 的内部映射细节（任务提到的 `everything-claude-code → Everything Claude Code` 未在本次 grep 命中具体位置）；trending 的展示主战场是 ResourceCard/Detail/About，README/featured 是否需要 trending 标识不在本研究范围确认。
- 当前 catalog `github-trending` count = 0，本机未跑过完整入库，所以无法实测前端真实渲染；以上基于代码静态分析。
- trending skill/plugin entry 目前**只靠 `source` 字段**区分（无 `discovered_via` / `trending: true` 这类专属布尔字段，`sync_github_trending.py:243-264` 的 skill entry schema 确认）。若希望前端判断更语义化，可在 sync 端加一个布尔字段，但那是 sync 侧改动、非前端必需。
