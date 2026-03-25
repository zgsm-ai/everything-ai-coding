# Coding Hub

<div align="center">
<img src="assets/title-card.jpg" alt="Coding Hub" />

<p><strong>800+ 精选开发资源一站式索引</strong><br/>MCP Servers · Skills · Rules · Prompts</p>

<p>
  <a href="https://github.com/zgsm-sangfor/costrict-skills-repo/stargazers"><img src="https://img.shields.io/github/stars/zgsm-sangfor/costrict-skills-repo?style=flat-square&color=4A90D9" alt="Stars" /></a>
  <a href="https://github.com/zgsm-sangfor/costrict-skills-repo/blob/main/LICENSE"><img src="https://img.shields.io/github/license/zgsm-sangfor/costrict-skills-repo?style=flat-square" alt="License" /></a>
  <a href="https://github.com/zgsm-sangfor/costrict-skills-repo/commits/main"><img src="https://img.shields.io/github/last-commit/zgsm-sangfor/costrict-skills-repo?style=flat-square" alt="Last Commit" /></a>
  <img src="https://img.shields.io/badge/resources-869-2ECC71?style=flat-square" alt="Resources" />
</p>

<p>
  <a href="#quick-start">Quick Start</a> ·
  <a href="#features">Features</a> ·
  <a href="#platforms">Platforms</a> ·
  <a href="#for-agents">For Agents</a> ·
  <a href="#contributing">Contributing</a>
</p>

</div>

## Why Coding Hub?

AI Coding Agent 越来越强，但找到合适的 MCP Server、Skill、Rule 仍然是碎片化的。

Coding Hub 从 8 个上游源自动聚合、过滤、评估，让你和你的 Agent **一条命令就能搜索和安装**开发资源。

## Quick Start

把这个仓库丢给你的 AI Agent，它会自动阅读 [For Agents](#for-agents) 部分并完成安装。或者手动安装：

```bash
# Claude Code — 一键安装
cp -r platforms/claude-code/skills/coding-hub/ ~/.claude/skills/coding-hub/
mkdir -p .claude/commands/coding-hub/ && cp platforms/claude-code/commands/coding-hub/*.md .claude/commands/coding-hub/

# 试试看
/coding-hub:search typescript
```

<details>
<summary>Opencode / Costrict 安装</summary>

```bash
# Opencode
mkdir -p ~/.opencode/skills/coding-hub/
cp platforms/opencode/skills/coding-hub/SKILL.md ~/.opencode/skills/coding-hub/
mkdir -p .opencode/command/ && cp platforms/opencode/command/*.md .opencode/command/

# Costrict
mkdir -p ~/.cospec/skills/coding-hub/
cp platforms/costrict/skills/coding-hub/SKILL.md ~/.cospec/skills/coding-hub/
mkdir -p .cospec/coding-hub/commands/ && cp platforms/costrict/commands/coding-hub/*.md .cospec/coding-hub/commands/
```

</details>

## Features

| 类型 | 数量 | 说明 |
|------|------|------|
| MCP Server | 510 | Model Context Protocol 服务器 |
| Prompt | 2 | 开发者专用 Prompt |
| Rule | 182 | 编码规范 / AI 辅助规则 |
| Skill | 175 | Agent Skill 扩展 |

**数据来源**：从 8 个上游源自动聚合，每周通过 GitHub Actions 同步，过滤 star > 10 的 coding 相关资源。

| 上游 | 来源 |
|------|------|
| MCP | [awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers) · [Awesome-MCP-ZH](https://github.com/yzfly/Awesome-MCP-ZH) |
| Skills | [anthropics/skills](https://github.com/anthropics/skills) · [Ai-Agent-Skills](https://github.com/skillcreatorai/Ai-Agent-Skills) |
| Rules | [awesome-cursorrules](https://github.com/PatrickJS/awesome-cursorrules) · [rules-2.1-optimized](https://github.com/Mr-chen-05/rules-2.1-optimized) |
| Prompts | [prompts.chat](https://github.com/f/prompts.chat) · [wonderful-prompts](https://github.com/langgptai/wonderful-prompts) |

## Platforms

支持三个 AI Coding 平台，命令格式略有差异：

| | Claude Code | Opencode | Costrict |
|---|---|---|---|
| 搜索 | `/coding-hub:search <kw>` | `/coding-hub-search <kw>` | `/coding-hub-search <kw>` |
| 浏览 | `/coding-hub:browse [cat]` | `/coding-hub-browse [cat]` | `/coding-hub-browse [cat]` |
| 推荐 | `/coding-hub:recommend` | `/coding-hub-recommend` | `/coding-hub-recommend` |
| 安装 | `/coding-hub:install <name>` | `/coding-hub-install <name>` | `/coding-hub-install <name>` |
| 更新 | `/coding-hub:update` | `/coding-hub-update` | `/coding-hub-update` |

<details>
<summary>平台路径差异</summary>

| | Claude Code | Opencode | Costrict |
|---|---|---|---|
| Skill 路径 | `~/.claude/skills/<name>/` | `~/.opencode/skills/<name>/` | `~/.cospec/skills/<name>/` |
| Command 路径 | `.claude/commands/<ns>/` | `.opencode/command/` | `.cospec/<ns>/commands/` |
| 命令分隔符 | `:` | `-` | `-` |

</details>

<details>
<summary>项目结构</summary>

```
costrict-skills-repo/
├── catalog/                  # 资源索引（数据层）
│   ├── index.json            # 合并后的完整索引（1292 条）
│   ├── schema.json           # 条目 schema 定义
│   ├── mcp/                  # MCP Server 源数据
│   ├── skills/               # Skill 源数据
│   ├── rules/                # Rule 源数据
│   └── prompts/              # Prompt 源数据
│
├── platforms/                # 各平台 Skill + 子命令
│   ├── claude-code/          # Claude Code 格式
│   ├── opencode/             # Opencode 格式
│   └── costrict/             # Costrict 格式
│
├── scripts/                  # 数据同步脚本
│   ├── sync_mcp.py           # 从上游同步 MCP
│   ├── sync_skills.py        # 从上游同步 Skills
│   ├── sync_rules.py         # 从上游同步 Rules
│   ├── sync_prompts.py       # 从上游同步 Prompts
│   ├── merge_index.py        # 合并生成 index.json
│   └── llm_evaluator.py      # LLM 质量评估
│
└── openspec/                 # 变更管理（OpenSpec）
```

</details>

## Contributing

欢迎通过 PR 向 `catalog/` 下对应类型目录添加精选资源。

---

## For Agents

> **AI Agent 请阅读本节。** 以下内容供 Agent 自动安装 coding-hub skill，无需人工干预。
> 请根据当前运行平台选择对应的安装方式。

### Claude Code

```bash
# 安装 skill（全局）
cp -r platforms/claude-code/skills/coding-hub/ ~/.claude/skills/coding-hub/

# 安装子命令（项目级）
mkdir -p .claude/commands/coding-hub/
cp platforms/claude-code/commands/coding-hub/*.md .claude/commands/coding-hub/
```

安装后可用命令：
- `/coding-hub:search <关键词>` — 搜索资源
- `/coding-hub:browse [分类]` — 浏览分类
- `/coding-hub:recommend` — 基于当前项目推荐
- `/coding-hub:install <名称>` — 安装资源
- `/coding-hub:update` — 更新到最新版本

### Opencode

```bash
# 安装 skill（全局）
mkdir -p ~/.opencode/skills/coding-hub/
cp platforms/opencode/skills/coding-hub/SKILL.md ~/.opencode/skills/coding-hub/

# 安装子命令（项目级）
mkdir -p .opencode/command/
cp platforms/opencode/command/*.md .opencode/command/
```

安装后可用命令：
- `/coding-hub-search <关键词>` — 搜索资源
- `/coding-hub-browse [分类]` — 浏览分类
- `/coding-hub-recommend` — 基于当前项目推荐
- `/coding-hub-install <名称>` — 安装资源
- `/coding-hub-update` — 更新到最新版本

### Costrict

```bash
# 安装 skill（全局）
mkdir -p ~/.cospec/skills/coding-hub/
cp platforms/costrict/skills/coding-hub/SKILL.md ~/.cospec/skills/coding-hub/

# 安装子命令（项目级）
mkdir -p .cospec/coding-hub/commands/
cp platforms/costrict/commands/coding-hub/*.md .cospec/coding-hub/commands/
```

安装后可用命令：
- `/coding-hub-search <关键词>` — 搜索资源
- `/coding-hub-browse [分类]` — 浏览分类
- `/coding-hub-recommend` — 基于当前项目推荐
- `/coding-hub-install <名称>` — 安装资源
- `/coding-hub-update` — 更新到最新版本

### 更新

```
/coding-hub:update              # Claude Code
/coding-hub-update              # Opencode / Costrict
```

更新命令会从 GitHub 拉取最新的 skill 和子命令文件覆盖本地。

### 验证

安装完成后，运行搜索命令测试：

```
/coding-hub:search typescript    # Claude Code
/coding-hub-search typescript    # Opencode / Costrict
```

返回搜索结果表格即安装成功。

### 数据源

索引 URL: `https://raw.githubusercontent.com/zgsm-sangfor/costrict-skills-repo/main/catalog/index.json`

索引是 JSON 数组，每个条目包含 `id`, `name`, `type`(mcp/skill/rule/prompt), `description`, `source_url`, `stars`, `category`, `tags`, `tech_stack`, `install`。
