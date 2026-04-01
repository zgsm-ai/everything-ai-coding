# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

Coding Hub — 聚合 3300+ 精选 MCP Servers、Skills、Rules、Prompts 的开发资源索引。数据从 9 个上游源自动同步，支持 Claude Code、Opencode、Costrict、VSCode Costrict 四个平台。

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
python -m pytest tests/test_unified_enrichment.py -v
python -m pytest tests/test_llm_evaluator.py -v
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

# 合并索引（包含去重、富化、评分治理、生命周期管理）
python scripts/merge_index.py

# 更新 README 中的资源统计数字
python scripts/update_readme.py
```

### 本地验证

```bash
# 验证 JSON schema
python -c "import json; json.load(open('catalog/index.json'))"

# 检查索引完整性
python scripts/merge_index.py  # 会输出去重统计和完整性警告
```

**依赖说明**：脚本仅用标准库（urllib、json），无需 pip install。CI 中安装 requests 用于缓存恢复。

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
README.md                                       ← 自动更新统计
```

**关键流程**：
- `sync_*.py` — 从上游抓取，写入 `catalog/{type}/index.json`
- `merge_index.py` — 调用 `enrichment_orchestrator.py`（统一富化）→ `scoring_governor.py`（评分治理）→ `catalog_lifecycle.py`（生命周期字段 + 增量复抓候选）
- `unified_enrichment.py` — Layer 2 信号填充（source_trust、confidence、heuristic reason）
- `llm_evaluator.py` — LLM 质量评估（coding_relevance、content_quality、specificity）

### Skills 三层来源与去重

- **Tier 1**（最高优先级）: anthropics/skills + Ai-Agent-Skills + antigravity-awesome-skills（全量收录，非技术类过滤）
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
| claude-code | `:` | `commands/coding-hub/{cmd}.md` |
| opencode | `-` | `command/coding-hub-{cmd}.md` |
| costrict | `-` | `commands/coding-hub/coding-hub-{cmd}.md` |
| vscode-costrict | `-` | `commands/coding-hub/coding-hub-{cmd}.md` |

修改 skill 内容时需同步四个平台文件。

### 脚本模块依赖关系

```
merge_index.py
  ├── utils.py              (公共工具：load_index, save_index, deduplicate, categorize, extract_tags)
  ├── enrichment_orchestrator.py  (调度富化)
  │   ├── unified_enrichment.py   (Layer 2: source_trust, confidence, heuristic reason)
  │   ├── llm_evaluator.py        (LLM 评估: coding_relevance, content_quality, specificity)
  │   └── health_scorer.py        (健康评分: popularity, freshness, quality, installability)
  ├── scoring_governor.py         (评分治理: final_score 加权计算)
  └── catalog_lifecycle.py        (生命周期: added_at, 增量复抓候选)
```

### 评分体系

- `evaluation` 子对象包含 LLM 评估维度 + 综合分数
- `health` 子对象包含 popularity/freshness/quality/installability 四维信号
- `scoring_governor.py` 将各维度加权为 `final_score`（0-100），输出 `decision`（accept/review/reject）
- `SOURCE_TRUST_MAP`（在 `unified_enrichment.py`）: 按来源分配信任分（anthropics-skills=5, mcp.so=2）

## CI

`.github/workflows/sync.yml` — 每周一 UTC 3:23 自动触发，也支持 `workflow_dispatch` 手动触发。

**流程**：crawl_mcp_so → sync_mcp → sync_rules → sync_skills → sync_prompts → verify_sync → merge_index → update_readme → auto commit+push

**缓存**：CI 通过 `actions/cache` 持久化 `.llm_cache.json`、`.llm_eval_cache.json`、`.llm_tag_cache.json`、`.llm_translate_cache.json`、`incremental_recrawl_state.json`、`fallback_skill_repos.json` 等文件避免重复计算。

**Secrets**：`GITHUB_TOKEN`（自动提供）、`LLM_BASE_URL`/`LLM_API_KEY`/`LLM_MODEL`（LLM 评估用，可选）

## 注意事项

- `catalog/index.json` 和各类型 `index.json` 由 CI 生成并提交，供 skill 命令通过 raw URL 读取
- `curated.json` 是手工维护的精选数据，也提交到仓库
- 本地跑 sync 脚本不带 `GITHUB_TOKEN` 会大量 429 限流，数据不完整但不影响验证逻辑
- `fetch_raw_content()` 对 404 只输出 DEBUG 日志，这是正常探测行为（如 skills.json 列出但无 SKILL.md 的条目）
- `merge_index.py` 会在去重后检查各类型的 drop 比例，超过 50% 会输出 WARNING
- `llm_evaluator.py` 有 30 天缓存过期策略，自动迁移旧格式缓存条目
