# GitHub Search 主动发现源（sync_github_trending）

## Goal

把"用 GitHub Search API 按 stars 发现热门 skill/plugin 仓库"从一次性诊断手段，固化成一个**主动发现 sync 源**，补上当前管线最大的盲区：发现完全依赖上游 curated 白名单 / awesome-list / registry 先收录，导致 ~190 个高星热门 skill 仓"任何源都没有"。本源主动从 GitHub 索引捞，下游复用现有质量闸门（hard_filter + LLM 6 维 + security scan）+ 去重。

## Feasibility 判定：✅ 可行（三块研究均已实测验证）

- GitHub Search API 够用（repo search 召回 + Tree API 验证；现有 `utils.github_api` 直接支持；调用预算塞得进 CI）。
- 复用现成机器：`scan_repo_via_api`（skill）/ `_entry_from_plugin` + `marketplace_verifier`（plugin）/ `hard_filter` / Tier 2 LLM / `deduplicate`。
- **重复风险真实但可控**：301 候选中 60 已在库；其中 37 个是"仅以 plugin/mcp 存在"的跨类型重复地雷（`deduplicate()` 按 type 分命名空间，抓不住）。解法已明确：repo 级预过滤。

## Requirements

1. **发现**：用 GitHub Search repo API 跑一组 topic/keyword/star/recency 查询（按 stars 排序，分页），产出候选 `owner/repo` 列表。复用 `utils.github_api`，主动 2s 节流避开 search 桶限流。
2. **结构验证（资源属性判定）**：对候选仓查它是否真含 `SKILL.md`（→ skill，用 `scan_repo_via_api`）或 `.claude-plugin/marketplace.json`（→ plugin，用 `marketplace_verifier`）。两者都没有 → 丢弃（天然剔除 cherry-studio/cliproxyapi 这类越界工具）。
3. **repo 级预过滤（去重关键）**：构建 `known_repos` 集合 = 现有 `catalog/{skills,plugins,mcp}/index.json`（或 catalog/index.json）所有条目的 `owner/repo`（**同时从 `source_url` 解析 AND `install.marketplace_repo` 提取**，小写归一）。候选仓命中即跳过——在扫描/LLM **之前**挡掉，既省 API+LLM，又物理杜绝 `deduplicate()` 抓不住的跨类型重复。
4. **质量闸门**：通过的新仓进现有 `hard_filter` → 写入 `catalog/{skills,plugins}/index.json` → 由 merge_index 的 LLM 评估 + security + `deduplicate()` 兜底。
5. **失败可见 + 增量友好**：对齐刚修的 skill_registry 行为（不缓存空结果、失败 WARN 汇总、default_branch 用 search item 自带值零成本获取）。独立 weekly cache block。

## Acceptance Criteria

* [ ] 能从 GitHub Search 发现 catalog 当前没有的高星 skill 仓（用前序 190 孤儿样本验证命中率 > 50%）
* [ ] **零重复**：发现流程对 301 候选样本不产出任何已存在仓的新条目（含 37 个跨类型地雷）—— 单测断言预过滤命中
* [ ] 结构验证正确剔除无 SKILL.md/marketplace.json 的越界仓（cherry-studio 等样本）
* [ ] rate budget 不超 GitHub 限额（search ≤30/min，主动节流）+ 失败可见（WARN 汇总）
* [ ] 不破坏现有 sync；merge 后 catalog 总条目无回归性重复

## Definition of Done

* 单测覆盖：发现 query 构造、结构验证、**repo 级预过滤去重**、known_repos 提取（source_url + marketplace_repo 双路）
* lint / 现有测试 green
* CI 集成点 + cache block 明确
* docs：CLAUDE.md 的"上游源"章节加一节

## Out of Scope（explicit）

* star velocity / trending 时间序列信号（后续单独任务）
* awesome-list README 解析挖掘（#3，本源是其超集，降级为可选补充）
* 前端展示改动
* code search（`path:` 路线）作为主路径——因 auth + 9/min + 索引盲区，仅留作未来补充

## Research References

* [`research/dedup-analysis.md`](research/dedup-analysis.md) — 去重按 type 分命名空间，跨类型抓不住；301 候选 60 已在库（37 个跨类型地雷）；解法=repo 级预过滤（source_url + marketplace_repo 双路提取 owner/repo）
* [`research/github-search-api.md`](research/github-search-api.md) — repo search 30/min + 1000 上限；主路径 repo search + Tree API 验证；`utils.github_api` 现成支持；单次 ~36-120 search + ~300-500 Tree，塞得进 CI
* [`research/integration-point.md`](research/integration-point.md) — 只有独立 `sync_github_trending.py` 能覆盖 skill+plugin；复用 `_entry_from_plugin` + `scan_repo_via_api` 避免重写 schema；插在 sync.yml csc 之后 backfill 之前

## Decision (ADR-lite)

**Context**：要把 GitHub Search 发现固化成 sync 源；现有去重按 type 分命名空间，跨类型重复是主要风险；skill/plugin 走完全不同的链路。

**Decision**：
1. 建**独立 `scripts/sync_github_trending.py`**（设计 b），复用 `scan_repo_via_api` / `_entry_from_plugin` / `marketplace_verifier`，避免重写 entry schema。
2. **repo 级 `known_repos` 预过滤**作为去重主防线（merge 的 `deduplicate()` 仅兜底），从 source_url + install.marketplace_repo 双路提取小写 owner/repo。
3. 发现走 **repo search + Tree API 验证**主路径，不用 code search。

**Consequences**：覆盖 skill+plugin；物理杜绝跨类型重复 + 省 API/LLM；新增一个 sync 脚本（与现有 sync_* 同构，维护成本可接受）。trending 时间序列信号留待后续。

## MVP 范围（已定）

* **skill + plugin 一起**（用户决定）。skill 走 `scan_repo_via_api`，plugin 走 marketplace.json 验证 + `_entry_from_plugin`；plugin bundle 检测需 `PluginContentFetcher`（ai-resource-eval）。两类共用同一发现 + 预过滤 + 结构验证骨架，按类型分流写入。

## Technical Notes

* dedup：`utils.py:1278 deduplicate()` / `:1261 _identity_key_for_entry`（按 type 路由）/ `:878 skill_identity_key` / `:1236 plugin_identity_key`
* 复用扫描/构造：`skill_registry.py:137 scan_repo_via_api`、`sync_plugins_official.py:629 _entry_from_plugin`、`scripts/marketplace_verifier.py`
* GitHub API：`utils.py:github_api`（支持 search 端点，urllib + token + retry）、`list_repo_files`（需传 default_branch，search item 自带）、`get_repo_info`
* 数据流：skill `skill_registry.discover_skills` → `sync_skills.py:766` → `catalog/skills/index.json`；plugin `sync_plugins_official.py:997` 写 `catalog/plugins/index.json`（dev/csc merge-preserve）→ `merge_index.py:810 deduplicate()`
* CI：插在 `sync.yml:206`（csc 之后）~ `:213`（backfill 之前）；cache block 仿 `:104-122`
* 同会话已修复（前置）：commit 7d8d63a/90d3474/f7d49f7
