# 修复 github-trending / 促升 entry 跨轮持久化

## Goal

修复 active-discovery（github-trending + 促升源）skill/plugin entry **每轮被 `sync_skills.py` 无差别覆盖抹掉、永不累积** 的严重既有 bug，让这些 entry 跨周持久化。这是 github-trending 源与促升任务（06-18-promote）有任何长期价值的前提。

## Root Cause（已实测确认）

`scripts/sync_skills.py:993-1003`：
```python
output_path = catalog/skills/index.json
existing_entries = load_index(output_path)
...
all_entries = overlay_added_at(all_entries, existing_entries)  # 只搬 added_at 时间戳，不搬 entry
save_index(all_entries, output_path)   # 整文件覆盖，all_entries = 仅 Tier1+Tier2
```
- `save_index(all_entries)` 把 `catalog/skills/index.json` 整文件覆盖成只有 sync_skills 自己的 Tier1/2 skill；`overlay_added_at` 只搬时间戳不搬 entry。
- CI 顺序：**sync_skills 跑在 triage 之前**。triage 写的 github-trending/促升 skill 在下一轮开头被 sync_skills 抹掉；triage 又因 `known_repos` 跳过"已入库的仓"不会重新产出 → **永不补回**。
- **实测铁证**：`0db0532`（上轮）github-trending 54 仓 1508 条 vs `f47daa7`（本轮）33 仓 852 条，**0 重叠**；9 个促升仓 + 上轮全部 github-trending 仓在本轮 catalog 任何 source 下都不存在。连**未被迁移**的 220 条也消失 → 证明与 06-18 迁移无关，是 sync_skills 无差别覆盖。

## Requirements

1. **sync_skills 写盘前保留"非自己管辖"的 skill entry**（github-trending + 促升 slug + 任何不属于 sync_skills 域的 source），而不是无差别 `save_index(all_entries)`。
2. **查清并修复 plugin 侧同款问题**：`sync_plugins_official.py` 是否同样整文件覆盖 `catalog/plugins/index.json`、抹掉 triage 写的 github-trending/促升 plugin（browserbase 等）。
3. **保持现有保护语义不破**：0-entry clobber 守卫（`:995`）、`overlay_added_at`、`deduplicate`、plugin-source 过滤（`is_plugin_source`）行为不变。
4. **测试**：round-over-round 持久化回归——existing index 含 github-trending/促升 entry → 跑 sync_skills 写盘后这些 entry 仍在；且 sync_skills 自己的 Tier1/2 entry 正常更新。
5. **（research 决定）一次性恢复丢失数据**：上轮 github-trending（git `0db0532`）+ 促升迁移（`798e6cf`）的 entry 能否从 git 历史一次性回灌 catalog，避免等它们被重新发现（且部分可能已不在 top-300 候选、永远回不来）。

## Open Questions（research 回答）

* plugin 侧（sync_plugins_official）是否同 bug？修法是否对称？
* 除 sync_skills 外还有别的 catalog/skills/index.json 覆盖者吗？（sync_skills_sh 写独立文件，应无关，需确认）
* "sync_skills 管辖域"如何界定才稳？（按 source 白名单？按 source_url 是否属于 Tier1/2 仓？按"非 github-trending 且非促升"？）
* 一次性恢复：从哪个 commit 回灌？促升迁移后的 `798e6cf` 还是上轮 `0db0532`？回灌后会不会与本轮新 entry 撞 id/dedup？

## Acceptance Criteria

* [ ] sync_skills 写盘后，existing 里的 github-trending/促升 skill entry 全部保留（单测）
* [ ] sync_skills 自己的 Tier1/2 entry 仍正常 add/update（单测，不回归）
* [ ] 0-entry clobber 守卫、overlay_added_at、deduplicate、plugin-source 过滤语义不变（单测）
* [ ] plugin 侧若同 bug → 同样修复 + 单测
* [ ] （若采纳恢复）一次性恢复脚本回灌丢失 entry，dry-run 可见、不撞 id、幂等
* [ ] 现有测试全绿
* [ ] 模拟"连续两轮"：第一轮写入 github-trending → 第二轮 sync_skills+triage 后仍在（集成式单测或脚本验证）

## Definition of Done

* 单测 + 现有测试绿
* CLAUDE.md 数据流水线段补一句"sync_skills/sync_plugins 保留外来 active-discovery entry"的约束（防回归）
* 若做恢复：恢复脚本跑过、丢失 entry 回灌、diff 可见

## Out of Scope

* 不改 github-trending 的发现/triage 逻辑（已正确）
* 不改 06-18 促升机制代码（已正确，只是依赖本修复才有长期价值）
* 不重构整个多源 catalog 写入架构（只做最小正确修复 + 防回归）

## Technical Notes

* 关键落点：`scripts/sync_skills.py:975-1006`（all_entries 组装 + 覆盖写）、`overlay_added_at` 定义、`scripts/sync_plugins_official.py` 的 catalog/plugins/index.json 写入、`scripts/triage_github_trending.py:148-166 flush_skills`（merge_preserve 写入，已正确）、CI 步骤顺序（CLAUDE.md CI 段：sync_skills … → triage）。
* `merge_preserve`（sync_github_trending.py:514）本身正确（combined = existing + accepted，不按 source 过滤）；问题纯在 sync_skills 的前置覆盖。
* 关联：06-18-promote-trending-repos-first-class-sources（本修复是其长期价值前提）。
