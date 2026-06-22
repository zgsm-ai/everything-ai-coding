# Research: catalog 评分与信任度按来源计算 + github-trending 源校准

- **Query**: source_trust 怎么算 / 质量评估路由 / final_score 混合 + decision 阈值 / security scan / 增量短路；以及 github-trending 主动发现源该如何校准
- **Scope**: internal（带 file:line）
- **Date**: 2026-06-16

## 速览结论（先看这个）

| 问题 | 事实 |
|---|---|
| source_trust 看什么 | **只看 `entry.source` 这个字符串**，在一张硬编码 dict 里查表；与 `source_priority`（URL 派生的 dedup 优先级）**完全无关** |
| github-trending 的 source_trust | skill 和 plugin **都拿默认值 40**（`"github-trending"` 不在 `_SOURCE_TRUST` 表里），等同 "unknown source" |
| skill 走几维 | github-trending skill → `source=="github-trending"` → 走 `skill` task → **完整 6 维 LLM 评分** |
| plugin 走几维 | github-trending plugin → 走 `plugin` task → **plugin.yaml 已升级到 5 维 LLM 评分（v2）**，CLAUDE.md 里 "plugin task 关闭 LLM 评分 / health-only" 的说法**已过期**。所以 plugin **也有 LLM 质量把关**，不是 health-only |
| security scan 会跑吗 | 会。security_scan_and_map 对所有类型（含 plugin/skill）都跑；但**目前 security verdict 不参与 accept/reject 决策**（只写 `entry.security` 字段，不卡门槛） |
| 增量短路 | github-trending **没有专属 diff sidecar**，三条短路路径（skills.sh / mcp_registry / windsurfrules）都不命中它 → **每周走完整重评**（受底层 SQLite content_hash cache 保护，README 没变则 runner 自身 cache 命中） |

---

## 1. source_trust 怎么算

**核心：source_trust 是 `entry.source` 字符串查表，不是 `source_priority`。**

`ai-resource-eval/ai_resource_eval/runner.py:654-657`：
```python
def _compute_source_trust(self, entry: EvalItem) -> float:
    """Score 0-100 based on source field."""
    source = getattr(entry, "source", None) or ""
    return self._SOURCE_TRUST.get(source, self._SOURCE_TRUST_DEFAULT)
```

查表定义在 `runner.py:582-602`（`_SOURCE_TRUST` dict）：
```python
"curated": 90, "mcp.so": 80, "awesome-mcp-servers": 70, "awesome-mcp-zh": 65,
"awesome-cursorrules": 60, "anthropics/claude-code": 85, "anthropics-skills": 75,
"prompts-chat": 50, "rules-2.1-optimized": 50,
"claude-plugins-official": 100, "anthropics/claude-plugins-official": 100,
"superpowers-marketplace": 95, "obra/superpowers-marketplace": 95,
"claude-plugins.dev": 70, "awesome-claude-plugins": 50,
```
默认值 `_SOURCE_TRUST_DEFAULT = 40`（`runner.py:602`，注释 "unknown sources"）。

**`source_priority` 是完全独立的另一套东西**：`scripts/utils.py:820-855` 的 `source_priority(source_url)` 由 **URL** 派生（1000=anthropics / 900=官方组织+registry / 800=skills.sh / 500=其它 GitHub / 200=已知镜像 / 100=非 GitHub），**仅用于 merge 阶段去重时挑 winner**（`utils.py:1322/1329/1351/1362/1372`），从不进 source_trust 计算。任务描述里 "skill source_priority 由 URL 派生为 500 / plugin source_priority=600" 与 source_trust **无任何关系**。

**github-trending 的实际取值**：
- `sync_github_trending.py:79` → `SOURCE_ID = "github-trending"`
- skill entry：`sync_github_trending.py:262` 写 `"source": SOURCE_ID` → source 字段就是 `"github-trending"`
- plugin entry：经 `sync_plugins_official._entry_from_plugin`（`sync_plugins_official.py:784`）写 `"source": source_cfg["id"]`，而 `sync_github_trending.py:372` 把 `"id": SOURCE_ID` 塞进 plugin_cfg → plugin 的 source 字段同样是 `"github-trending"`
- 两者 `"github-trending"` 都不在 `_SOURCE_TRUST` 表 → **source_trust = 40（默认）**

source_trust 在各 task 的 health 权重里占 **0.40**（skill/rule/prompt/mcp）或 **0.30**（plugin），见 §3 yaml。

---

## 2. 质量评估路由（skill 6 维 / plugin 现在是 5 维 LLM，不是 health-only）

类型→task 映射：`scripts/eval_bridge.py:85-92`（`_TYPE_TO_TASK`）+ `resolve_task_name`（`eval_bridge.py:95-97`）。
- `skill → skill`，`plugin → plugin`。

**EvalItem 用 `type` 字段（不是 source）选 task**：`eval_bridge.py:965` `t = entry.get("type", "skill")`。github-trending 写的 `"type": "skill"`（`sync_github_trending.py:246`）/ plugin 走 `_entry_from_plugin` 设 type=plugin。所以 github-trending 的 skill 走 `skill` task，plugin 走 `plugin` task。

**skill task（6 维 LLM）**：`ai-resource-eval/ai_resource_eval/tasks/skill.yaml:8-20`
- coding_relevance 0.25 / doc_completeness 0.20 / desc_accuracy 0.15 / writing_quality 0.15 / specificity 0.15 / install_clarity 0.10
- → github-trending skill **走完整 6 维 LLM 评分**。

**plugin task —— CLAUDE.md 说法已过期**：`ai-resource-eval/ai_resource_eval/tasks/plugin.yaml:15-25` 现在有 **5 个 LLM metric**（v2 已激活）：
- coding_relevance 0.25 / doc_completeness 0.30 / desc_accuracy 0.15 / writing_quality 0.15 / specificity 0.15（剔除了 install_clarity，权重并入 doc_completeness）
- `plugin.yaml:49` `rubric_major_version: 2`，`plugin.yaml:54` `health_blend_alpha: 0.85`
- yaml 头注释（`plugin.yaml:8`）："Plugin 6 维 LLM 评分（v2 起激活）"

runner 据 `self._metrics` 是否为空决定走哪条路：`runner.py:343`（`if self._metrics:` → 跑 LLM metric）vs `runner.py:372`（`elif self._enrichment:` → health-only + enrichment-only）。plugin.yaml 现在有 metrics → **走 LLM 评分路径，不是 health-only**。

> **结论**：CLAUDE.md "所有 plugin task 关闭 LLM 评分（health-only）" 已不符现状。**github-trending 的 plugin 同样会过 5 维 LLM 质量把关**，与官方 marketplace plugin 同一套 rubric。任务里担心的 "未策展 plugin 只有 health 没有 LLM 质量缺口" **当前不成立**（除非把 plugin.yaml metrics 清空回退到 v1）。

---

## 3. final_score 混合 + decision 阈值

**LLM 分**：`ai-resource-eval/ai_resource_eval/scoring/governor.py:18-61` `compute_final_score`，公式 `Σ (score/5 × 100 × weight)`，每维 1-5 分。

**health 分**：`governor.py:63-130` `compute_health_score`，按 task 的 `heuristic_signals` 权重加权；被剔除的信号（如 github-trending 缺 install_count → 剔 install_popularity；非 plugin 剔 manifest_completeness）权重按比例分回（`governor.py:102-112`）。

**混合**：`governor.py:132-156` `compute_blended_score`，`blended = α×llm + (1-α)×health`，**α 默认 0.85**。runner 调用点 `runner.py:414-418`，`alpha=self._task_config.health_blend_alpha`（skill 默认 0.85，plugin 显式 0.85 见 `plugin.yaml:54`）。health-only 路径（llm_score is None）则 `final_score = health_score`（`runner.py:410-412`）。

**decision 阈值**（`ai-resource-eval/ai_resource_eval/scoring/decision.py:8-52`）：
- `final ≥ accept` → accept；`review ≤ final < accept` → review；`final < review` → reject
- **硬规则**：`coding_relevance ≤ 2` 时 accept 降级为 review（`decision.py:49-50`）

各 task 阈值（**全部 accept=65**）：
- skill：accept 65 / review 50（`skill.yaml:41-42`）
- plugin：accept 65 / review 50（`plugin.yaml:42-43`）
- rule：accept 65 / review 50（`rule.yaml:41-42`）
- prompt：accept 65 / review 50（`prompt.yaml:39-40`）
- mcp_server：accept 65 / review 50（`mcp_server.yaml:40-41`）

各 task 的 source_trust health 权重：skill/rule/prompt/mcp = **0.40**；plugin = **0.30**（其余 0.10 给 manifest_completeness）。

**自动发现的高 star 但未策展条目会落到哪？** 推演（github-trending skill，source_trust=40，假设 star 多 → popularity 接近满分、freshness 高）：
- health 部分 source_trust 偏低（40），但 freshness/popularity 可能高 → health_score 中等偏上；
- 但 health 只占 15%，**final_score 主要由 LLM 6 维（85%）决定**；
- 所以**真正决定 accept/review/reject 的是 LLM 内容质量**，source_trust=40 影响很小（满分 vs 40 的差异 × 0.40 权重 × 0.15 blend ≈ 最多约 3.6 分 final_score 摆动）。
- 即：高 star 但内容空洞的仓，LLM 维度低 → 仍会落到 review/reject；高 star 且内容扎实 → accept。LLM 是主闸门。

**reject 过滤**：`scripts/scoring_governor.py:100-113`，`decision=="reject"` 且非 dry-run 才真删（默认 `EVAL_DRY_RUN=true` 只标记不删，`scoring_governor.py:43`）。注意还有 **registry 专属严过滤**（`scoring_governor.py:115-135`，仅对 `source=="registry.modelcontextprotocol.io"` 要求 decision==accept 才入库），**github-trending 不在此特判内**。

---

## 4. security scan

会对 github-trending 条目跑。

- 管线插入点：`scripts/enrichment_orchestrator.py:59-80`，质量评分后调 `security_scan_and_map`（`eval_bridge.py:1365`）。受 `SECURITY_SCAN_ENABLED`（默认非 false 即开，`enrichment_orchestrator.py:60`）控制。
- 路由：`eval_bridge.py:1314-1335`，对**所有有 id 的 entry** 构造 EvalItem（mcp 走合成 install.config，其它类型走 fetcher）→ 不按 source 过滤，所以 github-trending 的 skill/plugin **都会被扫**。
- task 配置：`ai-resource-eval/ai_resource_eval/tasks/security_scan.yaml`，输出 6 字段（risk_level / verdict / red_flags / permissions / summary / recommendations），`metrics: []` + `heuristic_signals: []`（`security_scan.yaml:23-24`），独立 `rubric_major_version: 2`（`:30`）、独立 cache namespace `security`。
- **关键缺口**：`security_scan.yaml:11-15` 注释明说 "**security 评估不影响 accept/reject 决策，threshold 语义在 security 路径下未被使用**"。映射函数 `_map_security_to_entry`（`eval_bridge.py:1237-1270`）只把结果写进 `entry.security` 字段，**不触碰 `entry.decision`**。也就是说**目前 verdict=reject 的条目仍可能 decision=accept 入库**，security 只是展示性元数据。
- verdict↔risk_level 强约束（不匹配视为评估失败，不写 security 字段）由 SecurityScanResult validator 把关，失败兜底见 `runner.py:520-523` 一带（返回 None 不写）。

---

## 5. 增量评估短路

三条短路路径都**不覆盖 github-trending**：

1. **skills.sh**（`eval_bridge.py:328-375`）：要求 entry 带 `skills_sh_url` 字段（`_is_skills_sh_derived`，`eval_bridge.py:213-222`）。github-trending skill 不写该字段 → 不命中。
2. **mcp_registry**（`eval_bridge.py:460-506`）：要求 `source=="registry.modelcontextprotocol.io"`（`_is_mcp_registry_derived`，`eval_bridge.py:442-457`）→ 不命中。
3. **windsurfrules**（`eval_bridge.py:546-571`）：当前**整条路径被禁用**（`eval_bridge.py:564-571` 直接 `return {}, list(entries)`），且只认 awesome-windsurfrules → 不命中。

→ github-trending 条目落入 `remaining_by_type`，**走完整 runner 评估**。但底层仍有保护：runner 自身的 SQLite cache 按 `content_hash + rubric_version` 命中（`runner.py:332-335` `_check_cache`），README 未变 + rubric 未升级 → 复用上轮结果，**不会重复 LLM 调用**。区别只是 github-trending 没有 sync 端的 diff sidecar 来"预筛跳过 fetch"，每周仍要 fetch 一次内容算 content_hash（参考 mcp_registry/skills.sh 的 diff 是用来省掉这步 fetch+lookup 的）。

短路调度总入口：`eval_bridge.py:972-1034`（`run_eval` 内 incremental 分支）。

---

## 校准建议（针对 github-trending 主动发现源）

> 以下为基于上述代码事实的校准点，供主 agent 决策。

### A. source_trust 取值
- 现状：github-trending → 默认 40（"unknown"）。这其实是**合理的保守值**——主动发现、未经人工策展，给它和 unknown 同档说得通。
- 若想显式表达"自动发现、低于任何策展源"，可在 `runner.py:583` 的 `_SOURCE_TRUST` 加一行 `"github-trending": 40`（或更低，如 30/35），让取值"有意为之"而非靠默认兜底。**注意 source_trust 在 final_score 里影响极小**（最多约 3.6 分摆动，见 §3），所以这主要是语义/可解释性，不是质量闸门。

### B. 要不要给自动发现的 plugin 补 LLM 质量评估
- **不需要补——plugin 现在已经走 5 维 LLM 评分**（plugin.yaml v2，§2）。CLAUDE.md 的 "health-only" 描述过期。github-trending plugin 与官方 marketplace plugin 共用同一 plugin task、同一 65 阈值、同一 0.85 blend。
- 真正的质量闸门是 LLM 5 维 + accept=65，不依赖 source_trust。所以"未策展 plugin 质量缺口"在当前代码下**不存在**。
- 若要进一步收紧（因为是自动发现），可考虑给 github-trending 专门调高 plugin/skill 的 accept 阈值（需要 per-source 阈值机制，目前 task 配置只按 type 不按 source —— 这是一个**当前不存在的能力**，要新增）。

### C. security 门槛
- 现状：security 只写字段、**不卡 decision**（§4）。对未经审查的自动发现仓，"caution 也 reject"这类硬门槛**当前没有任何代码实现**——需要新增逻辑（最自然的落点是 `scripts/scoring_governor.py` 的 reject 过滤段 `:100-135`，类似 registry strict-accept 那段，加一个"github-trending 源 + security.verdict in {caution,reject} → drop"的二次过滤）。
- 可参照的现成模式：`scoring_governor.py:115-135` 的 `MCP_REGISTRY_STRICT_ACCEPT` 二次过滤（按 source 字符串 + decision 条件 drop），结构上可平移成 security-based 过滤。

### D. 增量评估
- github-trending 无 diff sidecar，每周全量重 fetch（但 LLM cache 仍命中，§5）。若 sync 端想省 fetch，可仿 `sync_skills_sh.compute_diff` / `sync_mcp_registry` 写一个 `.github_trending_cache/diff.json`（按 repo full_name + pushed_at 算 added/changed/stable），再在 `eval_bridge.py` 加第 4 条短路。当前 `sync_github_trending.py:363-377` 已经维护了一个 verify_cache（按 pushed_at），可作为 diff 的数据基础。**这是优化项，不是正确性问题**——不做的话每周多一轮 fetch，但评分结果不受影响。

---

## 关键文件清单

| 文件 | 关键行 | 作用 |
|---|---|---|
| `ai-resource-eval/ai_resource_eval/runner.py` | 582-602 (`_SOURCE_TRUST`), 654-657 (`_compute_source_trust`), 343/372 (LLM vs health-only 分支), 402-422 (blend) | source_trust 查表 + 评分主流程 |
| `ai-resource-eval/ai_resource_eval/scoring/governor.py` | 18-61 (LLM 分), 63-130 (health 分), 132-156 (blend α=0.85) | 三种分数计算 |
| `ai-resource-eval/ai_resource_eval/scoring/decision.py` | 8-52 | accept/review/reject 阈值 + coding_relevance≤2 降级 |
| `ai-resource-eval/ai_resource_eval/tasks/skill.yaml` | 8-20 (6 维), 41-42 (阈值 65/50) | skill task |
| `ai-resource-eval/ai_resource_eval/tasks/plugin.yaml` | 15-25 (5 维 LLM, v2), 32-35 (source_trust 0.30), 42-43, 49, 54 | plugin task（已非 health-only） |
| `ai-resource-eval/ai_resource_eval/tasks/security_scan.yaml` | 11-15 (不卡 decision), 23-24, 30, 32 | security task |
| `ai-resource-eval/ai_resource_eval/api/types.py` | 110 (`source`), 117 (`install_count`), 175-187 (HealthSignals) | EvalItem/HealthSignals schema |
| `scripts/eval_bridge.py` | 85-97 (type→task), 328-571 (三种短路), 1237-1396 (security) | bridge |
| `scripts/scoring_governor.py` | 43 (dry-run), 100-113 (reject 过滤), 115-135 (registry strict) | governance / reject 落地 |
| `scripts/enrichment_orchestrator.py` | 50-55 (eval), 59-80 (security 阶段) | 管线编排 |
| `scripts/utils.py` | 820-855 (`source_priority`, URL 派生, 仅 dedup 用) | source_priority ≠ source_trust |
| `scripts/sync_github_trending.py` | 79 (`SOURCE_ID`), 246/262 (skill type+source), 369-376 (plugin cfg id+priority 600) | trending 源写入 |
| `scripts/sync_plugins_official.py` | 784-785 (`_entry_from_plugin` 写 source/source_priority) | plugin entry 的 source 来自 cfg id |

## Caveats / Not Found

- **CLAUDE.md 与代码不一致**：CLAUDE.md "所有 plugin task 关闭 LLM 评分（health-only）" 已过期，plugin.yaml 实际是 v2 的 5 维 LLM 评分。后续若引用 CLAUDE.md 描述需以 plugin.yaml 实际内容为准。
- **per-source 阈值 / security 卡门槛 / github-trending diff** 三项均为**当前代码不存在的能力**，建议 B/C/D 涉及新增逻辑，非现有行为描述。
- 未实际运行评估验证 github-trending 条目的真实 final_score 分布（无 LLM key 环境下无法跑）；§3 的落点推演基于公式推导，非实测。
