# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

Everything AI Coding — 聚合 3300+ 精选 MCP Servers、Skills、Rules、Prompts 的开发资源索引。数据从 9 个上游源自动同步，支持 Claude Code、Opencode、Costrict、VSCode Costrict 四个平台。

## 提交规范

原子化提交，格式：`[type] 中文描述`

类型：`[feat]` `[fix]` `[refactor]` `[docs]` `[ci]` `[chore]`

规则：
- 每个提交只做一件事
- 描述用中文，简洁直白
- 不写 Co-Authored-By（除非协作场景）

## 测试

```bash
# 运行所有测试
python -m pytest tests/ -v

# 运行特定测试文件
python -m pytest tests/test_merge_index.py -v
python -m pytest tests/test_eval_bridge.py -v
python -m pytest tests/test_scoring_governor.py -v
```

## 开发命令

### 同步数据

```bash
# 同步各类型资源（需要 GITHUB_TOKEN 避免 rate limit）
GITHUB_TOKEN=xxx python scripts/sync_mcp.py
GITHUB_TOKEN=xxx python scripts/sync_rules.py
GITHUB_TOKEN=xxx python scripts/sync_skills.py    # Tier 2 评估需要 LLM_* 环境变量
GITHUB_TOKEN=xxx python scripts/sync_prompts.py

# 增量抓取 mcp.so（避免全量重抓）
python scripts/crawl_mcp_so.py --mode incremental

# 合并索引（包含去重、富化、评分、生命周期管理）
python scripts/merge_index.py

# 更新 README 中的资源统计数字（中英文 README 会同时更新）
python scripts/update_readme.py
```

### 评估引擎

```bash
# 安装本地评估包（首次 / 更新后）
pip install -e ai-resource-eval

# 用 CLI 直接跑全量评估（独立于 merge 管线）
ai-resource-eval run \
  --task all \
  --input catalog/index.json \
  --output .eval_cache/results.json \
  --judge openai_compat \
  --cache-dir .eval_cache \
  --concurrency 5 \
  --incremental \
  --no-interactive \
  --on-fail queue

# 环境变量：LLM_API_KEY / LLM_BASE_URL / LLM_MODEL（或 JUDGE_ 前缀）
```

### 本地验证

```bash
# 验证 JSON schema
python -c "import json; json.load(open('catalog/index.json'))"

# 检查索引完整性
python scripts/merge_index.py  # 会输出去重统计和完整性警告
```

**依赖说明**：sync 脚本仅用标准库（urllib、json）。评估引擎需要 `pip install -e ai-resource-eval`（pydantic、httpx）。CI 中自动安装。

## 架构

### 数据流水线

```
上游源 (9个 GitHub 仓库 + mcp.so)
    ↓  scripts/sync_*.py（解析 README/API/CSV，写入各类型 index.json）
catalog/{mcp,skills,rules,prompts}/index.json  ← 各类型索引（CI 生成）
    + catalog/*/curated.json                    ← 手工精选（手动维护）
    ↓  scripts/merge_index.py（去重 → 富化 → 评分 → 生命周期）
catalog/index.json                              ← 最终索引（CI 提交）
    ↓  scripts/update_readme.py
README.md + README.zh-CN.md                    ← 自动更新统计与精选区块
```

**关键流程**：
- `sync_*.py` — 从上游抓取，写入 `catalog/{type}/index.json`
- `merge_index.py` — 调用 `enrichment_orchestrator.py`（评估+富化）→ `scoring_governor.py`（reject 过滤）→ `catalog_lifecycle.py`（生命周期字段 + 增量复抓候选）
- `eval_bridge.py` — 胶水层：按资源类型分组，调用 ai-resource-eval harness，将评分 + enrichment 字段映射回 catalog entry，转换 health 格式

### 评分引擎（ai-resource-eval）

嵌入在 `ai-resource-eval/` 的独立评估包（同时有独立 GitHub 仓库 `papysans/ai-resource-eval`，两边各自演化）。

**评分+富化流程**：抓取 README → 单次 LLM 调用产出 6 维评分 + enrichment 字段（summary, summary_zh, tags, tech_stack, search_terms, highlights）→ health 信号 → final_score 混合 → decision 判定

**6 个 LLM 维度**：coding_relevance, doc_completeness, desc_accuracy, writing_quality, specificity, install_clarity

**Enrichment 字段**：summary（英文）, summary_zh（中文）, tags, tech_stack, search_terms, highlights — 通过 `enrichment: true` task config 控制

**3 个 health 信号**：freshness, popularity, source_trust

**混合公式**：`final_score = llm_score × 0.85 + health_score × 0.15`

**4 种 task 配置**（内置于包内）：mcp_server, skill, rule, prompt — 各有不同的维度权重和 accept/review 阈值，均默认 `enrichment: true`

**缓存**：SQLite（`.eval_cache/`），基于 content_hash + rubric_version，增量评估只评新增/变更条目

### Skills 三层来源与去重

- **Tier 1**（最高优先级）: anthropics/skills + Ai-Agent-Skills + antigravity-awesome-skills + vasilyu1983/ai-agents-public（全量收录，非技术类过滤）
- **Tier 2**: GitHub 搜索 + awesome-openclaw-skills → LLM 评估（TOP 300）
- **Tier 3**（最低优先级）: `catalog/skills/curated.json` 手工精选

**去重逻辑**（`utils.py:deduplicate()`）：
1. 按 `source_url` 去重（先入为主，Tier 1 优先保留）
2. 按 `id` 去重（同一 ID 只保留第一个）
3. 结果：Tier 1 > Tier 2 > Tier 3

### 多平台适配

`platforms/` 下四套内容，差异仅在文件命名、frontmatter、命令引用格式：

| 平台 | 命令分隔符 | 命令路径 |
|------|-----------|---------|
| claude-code | `:` | `commands/everything-ai-coding/{cmd}.md` |
| opencode | `-` | `command/everything-ai-coding-{cmd}.md` |
| costrict | `-` | `commands/everything-ai-coding/everything-ai-coding-{cmd}.md` |
| vscode-costrict | `-` | `commands/everything-ai-coding/everything-ai-coding-{cmd}.md` |

修改 skill 内容时需同步四个平台文件。

### 脚本模块依赖关系

```
merge_index.py
  ├── utils.py                    (公共工具：load_index, save_index, deduplicate, categorize, extract_tags)
  ├── enrichment_orchestrator.py  (调度：仅调用 eval_bridge)
  │   └── eval_bridge.py          (评估+富化 → ai-resource-eval 本地包)
  ├── scoring_governor.py         (reject 过滤 + dry-run 控制)
  └── catalog_lifecycle.py        (生命周期: added_at, 增量复抓候选)
```

## CI

`.github/workflows/sync.yml` — 每周一 UTC 3:23 自动触发，也支持 `workflow_dispatch` 手动触发。

**流程**：crawl_mcp_so → sync_mcp → sync_rules → sync_skills → sync_prompts → verify_sync → merge_index → update_readme → auto commit+push

**缓存**：CI 通过 `actions/cache` 持久化 `.llm_cache.json`、`.eval_cache/`（SQLite）、`incremental_recrawl_state.json`、`fallback_skill_repos.json` 等文件避免重复计算。

**环境变量**：
- `GITHUB_TOKEN`（自动提供）
- `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`（评估引擎用，可选 — 无 key 则跳过评估）
- `EVAL_DRY_RUN`（默认 `true`，reject 条目仅标记不删除）
- `EVAL_INCREMENTAL`（CI 中硬编码 `true`，防止意外全量评估）

## 注意事项

- `catalog/index.json`、各类型 `index.json`、`catalog/featured*.md` 由 CI 生成并提交，供 skill 命令与 README 渲染使用
- `curated.json` 是手工维护的精选数据，也提交到仓库
- 本地跑 sync 脚本不带 `GITHUB_TOKEN` 会大量 429 限流，数据不完整但不影响验证逻辑
- `fetch_raw_content()` 对 404 只输出 DEBUG 日志，这是正常探测行为（如 skills.json 列出但无 SKILL.md 的条目）
- `merge_index.py` 会在去重后检查各类型的 drop 比例，超过 50% 会输出 WARNING
- `ai-resource-eval` 依赖 pydantic + httpx，首次使用需 `pip install -e ai-resource-eval`
