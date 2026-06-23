# 重构 search-index + 前端搜索：瘦身 + 预建索引 + 来源可搜

## Goal

解决 GitHub Pages 前端搜索的**性能差 + 可搜性弱**两大问题：search-index 体积过大（21MB）拖慢首屏、客户端逐条打分卡顿；且搜索文本不含来源/仓库/作者，导致"按来源/作者搜"（如搜 mattpocock）几乎搜不到。

## What I already know（已实测，eee95e9）

* **体积**：`catalog/search-index.json` = **21.1 MB**，22927 条，平均 877 字节/条（catalog/index.json 本体 74 MB）。整包下载 + 解析 + 客户端建索引。
* **字段臃肿**（占空间排序）：`search_text` 5.6MB / `description` 2.5MB / `source_url` 1.8MB / `description_zh` 1.0MB / `bundled_in` 0.28MB / `install_method` 0.24MB / `install` 0.13MB —— 很多是搜索不需要的全量内容。
* **可搜性**：前端 `frontend/src/hooks/useSearch.ts` 搜索字段 = `['name','description','description_zh','search_text']`（boost name:3/desc:1/search_text:0.8），**不含 source/source_url/作者**。`search_text` = 名字 + 中英描述 + tags，也不含来源仓库。→ 搜 "matt"：32 条 mattpocock skill 里只有 2 条（名字带 matt）能匹配，其余 30 条（grilling/handoff…）漏掉。
* **source 字段全空**：search-index 22927 条 `source` 全为空（slim_item 当前虽写 source，但 merge_index 生成的这份没带；字段集里实际无 source）→ 没法按来源筛/搜/分组。
* **搜索算法**：useSearch 客户端逐条 token 打分（O(n·tokens)/每次输入），2.3 万条上每次输入全表扫。
* **数据生成**：`scripts/build_frontend_data.py`（`slim_item` :70、search_index_path :191）+ `scripts/merge_index.py`（search_index_path :1472，二者都可能写这份文件，需厘清谁是权威）。
* **部署**：`publish-site.yml` 跑 build_frontend_data → pnpm build → 部署 frontend/dist（Weekly Sync 成功后由 deploy-pages.yml 触发）。

## 候选改进方向（待 brainstorm 收敛）

1. **瘦身索引**：search-index 只留搜索必需最小字段，重字段（description 全文 / install / description_zh / bundled_in）挪到点开 Detail 时按需拉。预计 21MB → 3-5MB。
2. **预建索引 + 虚拟列表**：构建期预生成序列化搜索索引（MiniSearch/FlexSearch），客户端 loadJSON；结果列表虚拟滚动。
3. **来源可搜**：search_text 收录 source/owner-repo/作者 + 填 source 字段 + 来源/作者 facet。
4. **（可选）服务端搜索**：Typesense/Algolia/Pages Function —— 规模再大才需要。

## Decision (ADR-lite)

1. **整体路线 = 静态瘦索引（客户端，纯静态无后端）**。不引服务端搜索。
2. **搜索库 = MiniSearch**：构建期 `addAll`→`serialize` 产序列化索引；客户端 `MiniSearch.loadJSON` 秒加载（不现建）；查询带字段 boost（对齐现有 name:3/desc:1）、prefix/fuzzy。
3. **激进瘦身**（21MB → 目标 ~2-3MB）：
   - 索引文本 `search_text` = name + description **截断 ~200 字** + tags + **source / owner-repo / 作者**（← 解决"按来源/作者搜不到"）。
   - 列表卡片只存最小字段：id/name/type/**source**/stars/final_score/freshness_label/短 snippet。
   - **重字段移出索引**（全 description / description_zh / install / bundled_in / tech_stack）→ 落到**按 id 拉的 per-entry JSON**（`api/entries/<id>.json`），Detail 只拉那一条（**顺带修掉 Detail 现在一次性加载全部 5 个 per-type JSON 的负担**）。
4. **顺带修 `source` 字段为空**（现 22927 条全空）：search-index/卡片带上 source，支持按来源展示/搜。

## Open Questions（剩余，非阻塞）
* 来源/作者 **facet 筛选**：MVP 必做还是 stretch？（倾向 stretch —— search_text 收录 source 已让"搜 mattpocock"可用）
* 结果列表**虚拟滚动**库（react-window 等）：MVP 纳入还是看瘦身后是否还卡再定？

## Requirements

* search-index 体积从 21MB 降到 ~2-3MB 量级（重字段移出）
* `search_text` 收录 source / owner-repo / 作者 → 搜 "matt"/"mattpocock" 命中该来源全部 32 条
* search-index/卡片 `source` 字段填充（现 22927 条全空）
* 前端搜索换 MiniSearch（loadJSON 预建索引），干掉 useSearch 的 O(n) 全表扫
* Detail 改按 id 拉 per-entry JSON（`api/entries/<id>.json`），不再一次性加载 5 个 per-type 大文件；移出索引的字段从这里取
* 结果列表虚拟滚动
* 不破坏现有 fallback（search-index 兜底、ResourceCard/Detail 渲染）

## Acceptance Criteria

* [x] search-index.json 体积显著下降：raw 21MB → 11.3MB，**gzip wire 3.46MB → 2.18MB（达 ~3MB 下载目标）**。注：2.3 万条规模下卡片必需字段地板 ~2.5MB，raw ≤3MB 不现实；进一步压 search_text/snippet 另列跟进。
* [ ] 搜 "mattpocock" / "matt" 返回 mattpocock/skills 全部条目（≥30 条，对比当前仅 2）
* [ ] search-index 条目带非空 source（抽样验证）
* [ ] 构建期产出 MiniSearch 序列化索引 + per-entry JSON（`api/entries/<id>.json` 含全字段）
* [ ] 前端用 MiniSearch.loadJSON 查询；Detail 按 id 拉单条，不再加载全部 per-type
* [ ] 结果列表虚拟滚动（大结果集不渲染全部 DOM）
* [ ] build_frontend_data 单测：瘦字段、search_text 含 source、per-entry JSON 产出
* [ ] 前端 tsc/构建通过；Detail/卡片渲染不回归（含 search-index fallback 路径）

## Implementation Plan（PR1→PR3）

* **PR1 数据层**（`scripts/build_frontend_data.py`）：slim search-index（最小卡片字段 + 含 source/作者的截断 search_text）+ 填 source + 产 per-entry JSON（`api/entries/<id>.json` 全字段）+ MiniSearch 序列化索引产出。单测覆盖。
* **PR2 前端搜索/详情**：`useSearch` 换 MiniSearch.loadJSON + ms.search（保留字段 boost 语义）；`Detail.tsx` 改按 id 拉 per-entry JSON（保留 search-index fallback）。
* **PR3 列表渲染 + 收尾**：结果列表虚拟滚动；（stretch）来源/作者 facet；兼容性兜底 + 文档。

## Definition of Done

* 单测（build_frontend_data）+ 前端构建/tsc 通过
* CLAUDE.md / 相关说明补 search-index 新 schema + per-entry JSON + MiniSearch 接入
* 体积与"搜来源"效果实测达标（AC）

## Out of Scope（evolving）

* 暂不引服务端搜索基础设施（除非 brainstorm 决定）
* 不改 catalog/index.json 本体 schema（74MB 是另一回事，bundle 侧已有过滤）

## Technical Notes

* 关键文件：`frontend/src/hooks/useSearch.ts`、`scripts/build_frontend_data.py`（slim_item / search-index 生成）、`scripts/merge_index.py:1472`、`publish-site.yml`、`frontend/src/pages/{Home,Detail}.tsx`、`frontend/src/components/ResourceCard.tsx`。
* search-index entry 现字段：id/name/type/category/tags/tech_stack/stars/description/description_zh/source_url/final_score/decision/freshness_label/bundled_in/install_method/install/search_text。
* 关联：本问题在排查"mattpocock 搜不到"时发现（promote 任务后续）。
