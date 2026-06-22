# 把 github-trending 优质 monorepo 仓「毕业」为一等上游源

## Goal

把 github-trending 主动发现源里**质量稳定、出品方知名**的 monorepo 仓（如 `composiohq/awesome-codex-skills`、`thedaviddias/front-end-checklist`、`k-dense-ai/scientific-agent-skills`、`google/skills`、`mattpocock/skills` 等），从「统一塞进 `source=github-trending`」**促升为各自独立的一等上游源**（per-repo `source` slug + 展示名 + trust 分级），让 costrict-web 与我们自己的 About 页都能多展示一批来源,改善来源归因。

## What I already know（已实测，见 research/）

* **costrict-web 展示链路**：消费 catalog bundle 的 `index.json`，**逐 entry 原样读 `source` 字面值，不走 SOURCE_REGISTRY**。→ 只要把 entry 的 `source` 从 `github-trending` 改成逐仓 slug，costrict-web 立刻多展示一个来源（改完即生效）。
* **About 页链路**走 `sources.json`：新 source **必须登记进 `SOURCE_REGISTRY`**（key 逐字等于 entry 的 `source` 字面值）且 `count>0` 才显示，否则只 WARNING、静默丢弃。
* **逐仓 source 已有先例**：Tier-2 `skill_registry.discover_skills` 早就给每条 entry 设 `source=repo_slug`（`skill_registry.py:358`）；catalog 里 `ComposioHQ/awesome-claude-skills`（285 条）就是活的 per-repo source 样本。促升 = 复用此模式。
* **dedup 不看 `source`**（`utils.deduplicate` 按 id / source_url / identity-key）→ 促升不会产生重复、不触发重抓。
* **已入库旧 entry 不会自动改 source**：triage 走 `merge_preserve`（按 id 跳过已存在），不覆盖字段。catalog 现存 1508 条 `source=github-trending`（目标仓占大头）仍挂 github-trending → **需一次性迁移脚本**，否则同仓 source 分裂。
* **one-type-per-source 约束真实**：`SOURCE_REGISTRY` 每 slug 单 `type`。候选仓全是单一 type（纯 skill 或纯 plugin，无混型），登记时填对主体 type 即可，不触发 `TYPE_ORDER.index()` 报错。
* `mattpocock/skills` **当前不在 catalog**（刚加为 seed，未跑 triage）→ 在它首次入库前加进 promote 清单，则首次入库即带专属 slug，**省去迁移**。

## Requirements

1. **新增 promote 清单** `scripts/trending_promoted_repos.json`：数组，元素 `{repo, source_slug, label, type, trust}`。
   * `repo`：`owner/repo`（匹配候选 `full_name`，大小写不敏感）
   * `source_slug`：该仓专属 source 值（与 Tier-2 一致，规范 `owner/repo`）
   * `label` / `url` / `type` / `trust`：供 SOURCE_REGISTRY 登记（trust 默认 3 = 知名出品但自动发现，高于 github-trending 的 2）
2. **triage/sync 支持 per-repo source 覆盖**：处理候选时若 `full_name` 命中 promote map → 用 `source_slug` 覆盖 `SOURCE_ID`。
   * skill 路径：`sync_github_trending.build_skill_entries`（硬编码 `source=SOURCE_ID` at `:434`）改为接受 `source_id` 参数
   * plugin 路径：triage cfg `id`（`triage_github_trending.py:238`）换成该仓 slug
3. **促升仓跳过 LLM `is_primary_skill` 判别**（手工精选/可信，等同 Tier-1/Tier-2 白名单待遇）：triage 前置判别 + eval backstop 两处都对 promote 仓豁免。省 LLM、避免误杀。
4. **批量登记 `source_registry.py`**：promote 清单每仓在 `SOURCE_REGISTRY` 加 entry，key 逐字等于 `source_slug`。
5. **一次性迁移脚本**：把 catalog 里命中 promote 清单的仓、`source==github-trending` 的旧 entry 的 `source` 改写为对应 slug。覆盖 `catalog/skills/index.json`、`catalog/plugins/index.json`、`catalog/index.json`（或迁移 per-type 后重跑 `merge_index.py` 重生成 `catalog/index.json`——因 source 不进 content_hash，eval cache 命中不重评）。
6. **CLAUDE.md** 「主动发现源」段补一句促升机制（promote 清单 vs seed 清单的区别 + 迁移）。

## Acceptance Criteria

* [ ] promote 清单加载正确（含 schema 校验：repo/source_slug/type 必填）
* [ ] 命中 promote 仓的**新** skill entry 带 `source=<source_slug>` 而非 github-trending
* [ ] 命中 promote 仓的**新** plugin entry 带 `source=<source_slug>`
* [ ] promote 仓在 triage 跳过 is_primary_skill 判别（不调用 LLM 判别）
* [ ] `SOURCE_REGISTRY` 登记后 `build_sources_payload` 对该 source 不再 WARNING、count>0 时出现在 sources.json
* [ ] 迁移脚本把现存 github-trending 旧 entry 的 source 正确改写，且**不误伤**非 promote 仓
* [ ] 迁移后 `deduplicate()` 不产生重复（同仓 entry 全部归一 source）
* [ ] `mattpocock/skills` 在 promote 清单里（首次入库即带专属 slug）
* [ ] 单测覆盖：promote 加载 / skill 源覆盖 / plugin 源覆盖 / is_primary_skill 豁免 / registry 登记 / 迁移脚本
* [ ] 现有测试全绿（含 sync_github_trending / triage / source_registry / merge）

## Definition of Done

* 单测 + 现有测试绿
* CLAUDE.md 主动发现源段补促升机制
* 迁移脚本跑过本地 catalog、diff 可见（source 改写条数符合预期、无误伤）
* （costrict-web 实际展示效果需下游消费 bundle 后验证；本仓只保证 bundle index.json 的 source 字段已变）

## Out of Scope

* **不改 costrict-web**（外部仓，逐 entry 读 source 字面值，promote 后自动多来源）
* **不促升低质仓**：`danielmiessler/personal_ai_infrastructure`(47%)、`samuraigpt/generative-media-skills`(5%)、`dotnet/skills`(8% + plugin)、大量 1-entry 高星仓（产出极少）
* **不改 dedup 逻辑 / schema**（promote 不动 identity-key、不升 bundle schema_version）
* **不碰 plugin marketplace 发布链路**（promote 只改 catalog index.json 的 source 字段）
* **seed 与 promote 维持两个独立文件**（seed=强行进候选池；promote=给专属 source。正交关系，一个仓可只 seed / 只 promote / 两者皆是）

## Confirmed Promote List（用户拍板：推荐清单 10 个）

> **slug 一致性铁律**：`source_slug` 字符串必须三处逐字相同 —— ①新 entry 写入值 ②SOURCE_REGISTRY 的 key ③迁移脚本写入值。迁移脚本对 entry 的 `source_url` 反解 `owner/repo` 做**大小写不敏感**匹配，命中后统一写成下表 `source_slug`（小写 `owner/repo`），从而无论旧 entry 原始大小写如何都收敛到同一 slug。

| repo（候选 full_name） | source_slug（统一小写） | label | type | trust |
|---|---|---|---|---|
| ComposioHQ/awesome-codex-skills | `composiohq/awesome-codex-skills` | Composio Awesome Codex Skills | skill | 3 |
| thedaviddias/Front-End-Checklist | `thedaviddias/front-end-checklist` | Front-End Checklist | skill | 3 |
| k-dense-ai/scientific-agent-skills | `k-dense-ai/scientific-agent-skills` | K-Dense Scientific Agent Skills | skill | 3 |
| wanshuiyin/auto-claude-code-research-in-sleep | `wanshuiyin/auto-claude-code-research-in-sleep` | Auto Claude Code Research | skill | 3 |
| opensensenova/sensenova-skills | `opensensenova/sensenova-skills` | SenseNova Skills | skill | 3 |
| Dimillian/skills | `dimillian/skills` | Dimillian Skills | skill | 3 |
| iofficeai/officecli | `iofficeai/officecli` | OfficeCLI Skills | skill | 3 |
| google/skills | `google/skills` | Google Skills | skill | 3 |
| browserbase/skills | `browserbase/skills` | Browserbase Skills | **plugin** | 3 |
| mattpocock/skills | `mattpocock/skills` | Matt Pocock Skills | skill | 3 |

`mattpocock/skills` 尚未入库 → 迁移脚本对它无操作（catalog 无匹配 entry），下轮 triage 首次入库即带 slug。`browserbase/skills` 走 plugin 路由，登记 type=plugin。

## Technical Notes

* 研究全文：[`research/promote-to-first-class-sources.md`](research/promote-to-first-class-sources.md)
* 关键落点：
  * `scripts/sync_github_trending.py:95`(SOURCE_ID) / `:434`(skill 写 source) / `:402-440`(build_skill_entries)
  * `scripts/triage_github_trending.py:238`(plugin cfg id) / `:267`(skill 构造) / is_primary_skill 判别处
  * `scripts/eval_bridge.py` authenticity backstop（promote 仓豁免）
  * `scripts/source_registry.py:37-177`(SOURCE_REGISTRY) / `:180-233`(build_sources_payload) / `:227-231`(未登记 WARNING)
  * `scripts/skill_registry.py:358`（per-repo source 先例模板）
* 迁移脚本判仓：从 entry 的 `source_url` 反解 `owner/repo`，命中 promote map 且 `source==github-trending` 才改。
* trust=3 → `TIER_META[3]`=Tier 3，About 页信任分级自动归类。

## Decision (ADR-lite)

**Context**: github-trending 把所有发现仓塞进单一 source，costrict-web 与 About 页都只能看到一个笼统来源，丢失了「这条 skill 出自 google / composio / k-dense」的归因。
**Decision**: 引入 curated promote 清单，把高质量知名仓切到各自的 per-repo source（复用 Tier-2 现成模式），批量登记展示名，并写一次性迁移脚本翻新已入库旧 entry。
**Consequences**: costrict-web 自动多展示来源；About 页需登记才显示；github-trending 退化为长尾仓的 catch-all；promote 仓信任度提升（跳过 is_primary_skill）；一次性迁移成本 + 后续维护一份 curated 清单。
