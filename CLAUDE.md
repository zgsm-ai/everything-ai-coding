# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

Coding Hub — 聚合 1200+ 精选 MCP Servers、Skills、Rules、Prompts 的开发资源索引。数据从 9 个上游源自动同步，支持 Claude Code、Opencode、Costrict 三个平台。

## 提交规范

原子化提交，格式：`[type] 中文描述`

类型：`[feat]` `[fix]` `[refactor]` `[docs]` `[ci]` `[chore]`

规则：
- 每个提交只做一件事
- 描述用中文，简洁直白
- 不写 Co-Authored-By（除非协作场景）

## 常用命令

```bash
# 同步脚本（需要 GITHUB_TOKEN 环境变量避免 rate limit）
GITHUB_TOKEN=xxx python scripts/sync_mcp.py       # 同步 MCP servers
GITHUB_TOKEN=xxx python scripts/sync_rules.py      # 同步 Rules
GITHUB_TOKEN=xxx python scripts/sync_skills.py     # 同步 Skills（还需 LLM_* 环境变量做 Tier 2 评估）
GITHUB_TOKEN=xxx python scripts/sync_prompts.py    # 同步 Prompts

# 合并所有类型索引 → catalog/index.json
python scripts/merge_index.py

# 从 index.json 更新 README 中的资源数量
python scripts/update_readme.py
```

无需 pip install，脚本只用标准库（urllib）。CI 中额外安装 requests 但脚本未使用。

## 架构

### 数据流

```
上游源 (9个 GitHub 仓库 + mcp.so)
    ↓  scripts/sync_*.py（解析 README/API/CSV）
catalog/{mcp,skills,rules,prompts}/index.json  ← 各类型自动生成索引（CI 重建并提交）
    + catalog/*/curated.json                    ← 手工精选条目（提交到仓库）
    ↓  scripts/merge_index.py（去重+合并）
catalog/index.json                              ← 最终完整索引（CI 重建并提交）
    ↓  scripts/update_readme.py（正则替换数量）
README.md                                       ← 自动更新资源统计数字
```

### Skills 的三层来源

- **Tier 1**: anthropics/skills + skillcreatorai/Ai-Agent-Skills + sickn33/antigravity-awesome-skills（全量收录，非技术类过滤）
- **Tier 2**: `skill_registry.py` 从 GitHub 搜索发现 + `sync_skills.py` 从 VoltAgent/awesome-openclaw-skills 解析 coding 分类 → 合并后统一送 `llm_evaluator.py` LLM 质量评估过滤（TOP 300）
- **Tier 3**: `catalog/skills/curated.json` 手工精选

合并时优先级：Tier 1 > Tier 2 > Tier 3（`deduplicate()` 先入为主）

### 多平台适配

所有 skill 和命令文件统一在 `platforms/` 下：

| 平台 | Skill | Commands | 命令分隔符 |
|------|-------|----------|-----------|
| claude-code | `platforms/claude-code/skills/coding-hub/SKILL.md` | `commands/coding-hub/{cmd}.md` | `:` |
| opencode | `platforms/opencode/skills/coding-hub/SKILL.md` | `command/coding-hub-{cmd}.md` | `-` |
| costrict | `platforms/costrict/skills/coding-hub/SKILL.md` | `commands/coding-hub/coding-hub-{cmd}.md` | `-` |
| vscode-costrict | `platforms/vscode-costrict/skills/coding-hub/SKILL.md` | `commands/coding-hub/coding-hub-{cmd}.md` | `-` |

四套内容基本相同，差异仅在：文件命名、frontmatter 字段、正文中的命令引用格式、安装目标路径。VSCode Costrict 插件版使用 `.roo/` 路径存放 MCP 和 Rule/Prompt。

### 索引条目 Schema

每条资源包含：`id`（kebab-case）、`name`、`type`（mcp/skill/rule/prompt）、`description`、`source_url`、`stars`、`category`（11 个分类之一）、`tags`、`tech_stack`、`install`（含 method/config/files/repo）、`source`、`last_synced`。

完整定义见 `catalog/schema.json`。

## CI

`.github/workflows/sync.yml` — 每周一 UTC 3:23 自动触发，也支持手动触发。

流程：sync_mcp → sync_rules → sync_skills → sync_prompts → merge_index → update_readme → 自动 commit+push（仅在有变化时）。

需要的 secrets：`GITHUB_TOKEN`（自动提供）、`LLM_BASE_URL`/`LLM_API_KEY`/`LLM_MODEL`（Tier 2 评估用，可选）。

## 注意事项

- `catalog/index.json` 和各类型 `index.json` 由 CI 生成并提交到仓库，供 skill 命令通过 raw URL 读取
- `curated.json` 是手工维护的精选数据，也提交到仓库
- 本地跑 sync 脚本不带 `GITHUB_TOKEN` 会大量 429 限流，数据不完整但不影响验证逻辑
- `fetch_raw_content()` 对 404 只输出 DEBUG 日志，这是正常探测行为（如 skills.json 列出但无 SKILL.md 的条目）
