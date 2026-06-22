# 修复 security scan 复发性 6h 超时（认已有 security 字段 + 拆 aggregate）

## Goal

根治 aggregate job 的 security scan 因**重扫已带 security 字段的 entry** 而撞 GitHub 单 job 6h 硬上限、导致整轮取消（merge+commit 都没执行）的复发性故障。让 security scan 不再做无谓重扫，并让 merge+commit 不被 security 超时连累。

## Root Cause（已实测确认，run 27814065375）

- aggregate 的 security scan step（`sync.yml` 内联 `python -u - <<'PY'`，调 `eval_bridge.security_scan_and_map`）跑满 **6h00m** 被 GitHub 强杀（`##[error]The operation was canceled`），其后 merge+commit 没执行 → 不提交。
- 该 step 产生 **10,304 个 429**（占其余所有 enrich job 之和的数倍），retry 漏斗 `attempt 1/6→6/6 = 1746→1396→1061→689→202→28`（非死循环，是大批量真实调用 × provider 限流）。
- **触发批量的根因**：本会话 `recover_trending_entries.py` 回灌的 **2820 条 active-discovery entry 已带 `security` 字段**（1667/1669 有，798e6cf 扫过），**但 security scan 的增量短路只查 SQLite cache（`SHA256(content_hash:rubric_version)`，见 eval_bridge.py:44-66 注释），不认 entry 上已有的 `security` 字段**。这些条目 content_hash 不在本周 SQLite cache（且促升迁移改过 `source` 可能变了 hash）→ 全判冷、全重扫。
- **复发性**：security step 6h 被杀 → SQLite cache save step 没跑 → 下轮（周一 cron 默认 `SECURITY_SCAN_ENABLED=true`）这 2820 条仍冷 → 又 6h 超时 → 死循环。security 的 weekly cache（`security-eval-cache-YYYY-WW`，restore-keys 仅锚本周不跨周）使跨周更脆。

## Requirements

1. **A（根治：security scan 认 entry 已有的 `security` 字段）**：security_scan_and_map 对每个 entry，若它**已带合法 `security` 块**（结构完整 + `rubric_major_version` 匹配当前），**跳过 LLM 调用**，不再只依赖 SQLite cache。
   - 注意内容变更安全：若 entry content 变了应重扫。research 需确认 `security` 块是否记录了当时的 content_hash（或能否记录），以便"仅当 content_hash 未变才跳过"；若无法判定 content 变更，给出权衡（保守跳过 vs 牺牲新鲜度）。
   - 命中跳过时，最好同时把该结果回写 SQLite cache（warm cache），保持两条短路一致。
2. **B（防爆：拆 aggregate，commit 不被 security 连累）**：让 merge + commit（+ bundle 触发）在 security scan **之前/之外**完成，或 security 独立成非阻塞 job。这样 security 再超时也不挡 catalog 提交 + bundle 发布。
   - research 需给出 sync.yml aggregate job 当前步骤顺序，以及最小侵入的拆分方式（step 重排 vs 独立 job + artifact 传递）。
3. 不破坏现有 security 语义：失败兜底（不写 security 字段、下轮重试）、独立 cache namespace、verdict↔risk_level 校验、chunked write-back、`SECURITY_SCAN_ENABLED` / `SECURITY_SCAN_DRY_RUN` 开关。

## Acceptance Criteria

* [ ] entry 已带合法 security 块（rubric_major_version 匹配）→ security scan 跳过 LLM 调用（单测）
* [ ] content 变更（content_hash 不符）→ 仍重扫（单测，若采纳 content_hash 记录方案）
* [ ] 跳过命中时回写 SQLite cache（可选，单测）
* [ ] aggregate 拆分后：security scan 超时/失败**不阻断** merge+commit+bundle（CI 结构验证 / 干跑）
* [ ] 现有 security 测试不回归（失败兜底、verdict 校验、chunk、开关）
* [ ] 模拟"2820 条已带 security 字段"批量 → 跳过、不触发大批 LLM 调用（回归测试思路）

## Definition of Done

* 单测 + 现有测试绿
* CLAUDE.md security 段补"认 entry 已有 security 字段短路 + aggregate 拆分"说明
* （效果需一轮 CI 带 security 验证不再 6h 超时；代码层可单测）

## Out of Scope

* 不改 6 维质量评分 / enrich 路径（同类 SQLite cache 但本任务聚焦 security）
* 不重构 LLM provider / 限流策略（429 是 provider 侧，本任务只减少无谓调用量 + 防爆）
* 不改 recover_trending_entries.py（恢复已完成）

## Technical Notes

- security scan 落点：`.github/workflows/sync.yml`（aggregate job 内联 security step，约 line 753-880）、`scripts/eval_bridge.py:security_scan_and_map` + `_lookup_cached_result`（:229-）+ 顶部短路注释（:41-66）。
- `security` 块 schema：6 字段（risk_level/verdict/red_flags/permissions/summary/recommendations）+ `rubric_major_version`（当前 1）。research 确认是否含 content_hash。
- `catalog_lifecycle.PRESERVED_TOP_LEVEL_FIELDS=("security",)` 已让 security 跨 rebuild 保留——这正是 entry 带 security 字段的来源，A 方案与之天然契合。
- 关联：本故障由 `06-18-fix-trending-entry-persistence` 的恢复触发；持久化 fix 本身正确。
