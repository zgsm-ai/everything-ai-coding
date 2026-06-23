# 已入库 monorepo 增量重扫：抓后续新增 skill

## Goal

修复"已入库的 github-trending/促升 monorepo 仓被冻结在入库那一刻的 skill 集、后续上游新增的 skill 永远收不进来"的覆盖盲区。让活跃 monorepo（mattpocock/skills、composiohq、k-dense 等）长出来的新 skill 能在后续周期被增量抓取。

## Root Cause（已实测，2026-06-22~23）

- `mattpocock/skills` 入库时 32 个 SKILL.md；现仓库已 34 个（`skills/deprecated/qa`、`skills/in-progress/review` 入库后新增）。`scan_repo_via_api` 现在跑返回 34（这 2 个**不是被过滤**，是入库后才加的）。
- **机制**：仓一旦入库 → 进 `known_repos`（`sync_github_trending.build_known_repos`）→ github-trending Stage A **预过滤跳过它** → triage 不再深拉它 → 新 skill 永不补回。
- 持久化修复（06-18）只保证"已入库 entry 不被 sync_skills/sync_plugins 抹掉"，**不负责重扫已知仓抓新增**。
- **影响面 = github-trending + 促升 monorepo**（经 Stage A 发现、然后被 known_repos 跳过的仓）。**Tier-2（`skill_registry.discover_skills` 扫 `skill_repos.json` 白名单）每轮都重扫、不受此 bug 影响**（待实现期确认这条边界）。

## 候选方案（待 brainstorm 收敛）

核心思路：给已入库的发现源 monorepo 加**增量重扫**——

1. **变更检测**：记每个已扫仓的"上次扫描时的 `pushed_at`"（或 SKILL.md 数/树 SHA），与当前 `pushed_at` 比；变了才重扫。`pushed_at` 已在 Stage A 候选/仓元数据里。
2. **Stage A 豁免**：`build_known_repos` 预过滤时，对"已入库但 `pushed_at` 比上次扫描新"的仓**豁免跳过**、重新作为候选。
3. **triage 重拉 + merge_preserve**：重扫仓走同一深拉，新 skill 经 merge_preserve（按 id/url 去重）加进来，**只有新 skill 进评估**（存量 entry 不动、不重评）。
4. **状态存储**：每个仓的 last-scanned `pushed_at` 存在 cache（如 `.github_trending_cache/scanned_repos.json`）。

## Decision (ADR-lite)（2026-06-23 brainstorm 收敛）

1. **变更检测 = pushed_at 门**：存每仓"上次扫描 pushed_at"于 `.github_trending_cache/scanned_repos.json`；每轮对范围仓拉一次仓元数据（GET `repos/<owner>/<repo>`）比对，变新才重扫。粗但最省（任意 push 触发，但无新 skill 时只浪费一次拉树、不调 LLM）。
2. **范围 = github-trending + 促升的 skill monorepo**：从 catalog 取 `source ∈ {github-trending} ∪ 促升 slug` 且 `type=skill` 的 entry 反解唯一 owner/repo（~60-110 仓）。**排除 Tier-2**（`skill_registry.discover_skills` 已每轮重扫）。**plugin 不做**（bundle 重检复杂，另起/后续）。
3. **落点 = Stage A 豁免注入**：在 `build_known_repos` 预过滤后，对"在范围内 + pushed_at 变新"的仓**豁免 known_repos 跳过、作为候选注入** → 走现有 triage 深拉 → `merge_preserve` 按 id/url **只加新 skill**（促升仓专属 slug 在 triage 照常套用）→ 成功后更新 scanned_repos.json。
4. **成本上限 = `MAX_RESCAN`（默认 ~30）**：每轮重拉树的仓数设上限，超出推迟下轮（按 pushed_at 最新优先），防 CI 超时。
5. 只有新 skill 进评估（存量不动、不重评）；不破坏持久化修复（06-18）+ known_repos 跨类型去重 + Tier-2 既有重扫。

## Requirements

* 已入库的 github-trending/促升 skill monorepo 上游新增 skill 后，后续周期能增量抓到
* pushed_at 未变的仓不重扫（省成本）；超 MAX_RESCAN 推迟下轮
* 重扫仅加新 skill（merge_preserve 按 id/url）；不重评存量
* 促升仓重扫出的新 skill 仍带专属 source slug
* 不破坏持久化修复（06-18）、known_repos 跨类型去重、Tier-2 既有重扫、seed 机制

## Acceptance Criteria

* [ ] 范围仓集正确：从 catalog 取 source∈{github-trending}∪促升slug 且 type=skill 的唯一 owner/repo（排除 Tier-2）
* [ ] pushed_at 变新 → 该仓被注入候选、豁免 known_repos 跳过；未变 → 不注入
* [ ] 重扫仓走 triage 深拉，merge_preserve 只加库里没有的新 skill（已有的不重复、不重评）
* [ ] 促升仓重扫的新 skill 带专属 slug（非 github-trending）
* [ ] `scanned_repos.json` 成功扫描后更新 pushed_at；失败/空不更新（下轮重试）
* [ ] MAX_RESCAN 限量生效，超出按 pushed_at 最新优先、其余推迟
* [ ] 单测：范围识别 / pushed_at 比对 / 豁免注入 / merge_preserve 只加新 / cache 更新 / 限量
* [ ] 现有 sync_github_trending / triage 测试不回归

## Implementation Plan（PR1→PR3）

* **PR1**：`scanned_repos.json` cache 读写 + 范围仓识别（从 catalog 反解）+ pushed_at 变更检测；单测。
* **PR2**：Stage A 在 `build_known_repos`/`discover_candidates` 后豁免注入需重扫仓 + MAX_RESCAN 限量；确认 triage `merge_preserve` 只加新 + 促升 slug；成功后更新 cache。健康度日志（重扫仓数/新增 skill 数/限量推迟）。
* **PR3**：CI 接线（scanned_repos.json 进 weekly cache block）+ CLAUDE.md「主动发现源」段补增量重扫 + 边界文档。

## Definition of Done

* 单测 + 现有测试绿
* CLAUDE.md 补增量重扫机制 + scanned_repos.json cache
* （实际增量效果需 CI 带 token 跑一轮验证；代码层可单测）

## Out of Scope（evolving）

* 不改 Tier-2 发现路径（已每轮重扫）
* 不做 skill id 命名空间重构（另一回事，见 memory skill-id-namespacing-collision）

## Technical Notes

* 关键文件：`scripts/sync_github_trending.py`（`build_known_repos` 预过滤、`discover_candidates`、`collect_seed_candidates`、候选表）、`scripts/triage_github_trending.py`（深拉）、`scripts/skill_registry.py`（`scan_repo_via_api`）、`.github_trending_cache/`（cache）。
* 候选/仓元数据已含 `pushed_at`、`default_branch`。
* 关联：持久化修复 06-18-fix-trending-entry-persistence（保留 vs 重扫的分工）；促升 06-18-promote。
