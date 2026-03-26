# Coding Hub

<div align="center">
<img src="assets/title-card.jpg" alt="Coding Hub" />

<p><strong>1400+ 精选开发资源一站式索引</strong><br/>MCP Servers · Skills · Rules · Prompts</p>

<p>
  <a href="https://github.com/zgsm-sangfor/costrict-skills-repo/stargazers"><img src="https://img.shields.io/github/stars/zgsm-sangfor/costrict-skills-repo?style=flat-square&color=4A90D9" alt="Stars" /></a>
  <a href="https://github.com/zgsm-sangfor/costrict-skills-repo/blob/main/LICENSE"><img src="https://img.shields.io/github/license/zgsm-sangfor/costrict-skills-repo?style=flat-square" alt="License" /></a>
  <a href="https://github.com/zgsm-sangfor/costrict-skills-repo/commits/main"><img src="https://img.shields.io/github/last-commit/zgsm-sangfor/costrict-skills-repo?style=flat-square" alt="Last Commit" /></a>
  <img src="https://img.shields.io/badge/resources-1416-2ECC71?style=flat-square" alt="Resources" />
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

一条命令安装，指定你的平台：

```bash
# Claude Code
curl -fsSL https://raw.githubusercontent.com/zgsm-sangfor/costrict-skills-repo/main/install.sh | bash -s -- --platform claude-code

# Opencode（在项目根目录执行）
curl -fsSL https://raw.githubusercontent.com/zgsm-sangfor/costrict-skills-repo/main/install.sh | bash -s -- --platform opencode

# Costrict CLI（在项目根目录执行）
curl -fsSL https://raw.githubusercontent.com/zgsm-sangfor/costrict-skills-repo/main/install.sh | bash -s -- --platform costrict

# VSCode Costrict 插件
curl -fsSL https://raw.githubusercontent.com/zgsm-sangfor/costrict-skills-repo/main/install.sh | bash -s -- --platform vscode-costrict
```

安装完成后试试：

```bash
# Claude Code
/coding-hub:search typescript

# Opencode / Costrict CLI
/coding-hub-search typescript
```

或者把这个仓库丢给你的 AI Agent，它会自动阅读 [For Agents](#for-agents) 部分完成安装。

<details>
<summary>手动安装（git clone）</summary>

```bash
# 1. 克隆仓库
git clone https://github.com/zgsm-sangfor/costrict-skills-repo.git
cd costrict-skills-repo

# 2. Claude Code — Skill + Commands 全部安装到全局 skills 目录
cp -r platforms/claude-code/skills/coding-hub/ ~/.claude/skills/coding-hub/
cp platforms/claude-code/commands/coding-hub/*.md ~/.claude/skills/coding-hub/

# 3. Opencode — Skill 全局，Commands 到项目目录
# cp platforms/opencode/skills/coding-hub/SKILL.md ~/.opencode/skills/coding-hub/SKILL.md
# cp platforms/opencode/command/coding-hub-*.md <your-project>/.opencode/command/
```

其他平台见 [Platforms](#platforms) 章节的路径差异。

</details>

<details>
<summary>网络问题？</summary>

如果 GitHub 访问受限，可以设置代理后再 clone 和使用：

```bash
# HTTP 代理（根据你的代理端口修改）
export https_proxy=http://127.0.0.1:7890

# 或 Git 单独设置代理
git config --global http.proxy http://127.0.0.1:7890
git config --global https.proxy http://127.0.0.1:7890
```

后续 `/coding-hub:install` 等命令从 GitHub 拉取资源时同样需要网络通畅。

</details>

## Features

| 类型 | 数量 | 说明 |
|------|------|------|
| MCP Server | 495 | Model Context Protocol 服务器 |
| Prompt | 510 | 开发者专用 Prompt |
| Rule | 236 | 编码规范 / AI 辅助规则 |
| Skill | 175 | Agent Skill 扩展 |

**数据来源**：从 8 个上游源自动聚合，每周通过 GitHub Actions 同步，过滤 star > 10 的 coding 相关资源。

| 上游 | 来源 |
|------|------|
| MCP | [awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers) · [Awesome-MCP-ZH](https://github.com/yzfly/Awesome-MCP-ZH) |
| Skills | [anthropics/skills](https://github.com/anthropics/skills) · [Ai-Agent-Skills](https://github.com/skillcreatorai/Ai-Agent-Skills) |
| Rules | [awesome-cursorrules](https://github.com/PatrickJS/awesome-cursorrules) · [rules-2.1-optimized](https://github.com/Mr-chen-05/rules-2.1-optimized) |
| Prompts | [prompts.chat](https://github.com/f/prompts.chat) · [wonderful-prompts](https://github.com/langgptai/wonderful-prompts) |

## Platforms

支持四个 AI Coding 平台，命令格式略有差异：

| | Claude Code | Opencode | Costrict |
|---|---|---|---|
| 搜索 | `/coding-hub:search <kw> [type:mcp]` | `/coding-hub-search <kw> [type:mcp]` | `/coding-hub-search <kw> [type:mcp]` |
| 浏览 | `/coding-hub:browse [cat]` | `/coding-hub-browse [cat]` | `/coding-hub-browse [cat]` |
| 推荐 | `/coding-hub:recommend` | `/coding-hub-recommend` | `/coding-hub-recommend` |
| 安装 | `/coding-hub:install <name>` | `/coding-hub-install <name>` | `/coding-hub-install <name>` |
| 卸载 | `/coding-hub:uninstall <name>` | `/coding-hub-uninstall <name>` | `/coding-hub-uninstall <name>` |
| 更新 | `/coding-hub:update` | `/coding-hub-update` | `/coding-hub-update` |

<details>
<summary>平台路径差异</summary>

| | Claude Code | Opencode | Costrict | VSCode Costrict |
|---|---|---|---|---|
| Skill 路径（全局） | `~/.claude/skills/coding-hub/` | `~/.opencode/skills/coding-hub/` | `~/.costrict/skills/coding-hub/` | `~/.costrict/skills/coding-hub/` |
| Commands 路径 | 同上（全局） | `.opencode/command/`（项目级） | `.costrict/coding-hub/commands/`（项目级） | 无（内置于 SKILL.md） |
| 命令分隔符 | `:` | `-` | `-` | `-` |

- **Claude Code** 支持从全局 skills 目录加载子命令，一次安装所有项目可用
- **Opencode / Costrict CLI** 的命令文件需要安装到每个项目目录，在项目根目录运行 `install.sh` 即可
- **VSCode Costrict 插件** 所有命令逻辑内置于 SKILL.md，无需单独安装命令

</details>

<details>
<summary>项目结构</summary>

```
costrict-skills-repo/
├── install.sh               # 一键安装脚本（curl | bash）
├── catalog/                  # 资源索引（数据层）
│   ├── index.json            # 合并后的完整索引（869 条）
│   ├── schema.json           # 条目 schema 定义
│   ├── mcp/                  # MCP Server 源数据
│   ├── skills/               # Skill 源数据
│   ├── rules/                # Rule 源数据
│   └── prompts/              # Prompt 源数据
│
├── platforms/                # 各平台 Skill + 子命令
│   ├── claude-code/          # Claude Code 格式
│   ├── opencode/             # Opencode 格式
│   ├── costrict/             # Costrict 格式
│   └── vscode-costrict/      # VSCode Costrict 插件格式
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

> **AI Agent 请阅读本节完成自动安装。** 请严格按照以下步骤执行，不要跳过任何一步。

### 第 1 步: 一键安装

安装脚本支持自动检测平台，直接执行即可：

```bash
curl -fsSL https://raw.githubusercontent.com/zgsm-sangfor/costrict-skills-repo/main/install.sh | bash
```

脚本通过以下**进程级环境变量**自动识别平台（这些变量由各平台进程启动时注入，不会互相污染）：

| 环境变量 | 平台 |
|---------|------|
| `COSTRICT_CALLER=vscode` | VSCode Costrict 插件 |
| `COSTRICT_RUNNING=1` | Costrict CLI |
| `CLAUDECODE=1` | Claude Code |
| `OPENCODE=1` | Opencode |

> **注意**: `COSTRICT_BASE_URL`、`OPENCODE_CMUX_ATTENTION_MODE` 等变量会在所有平台出现（shell profile 泄漏），**不能**用来判断平台。只有上表中的 4 个变量是各平台进程启动时独占注入的。

如果自动检测失败，可以手动指定：
```bash
curl -fsSL https://raw.githubusercontent.com/zgsm-sangfor/costrict-skills-repo/main/install.sh | bash -s -- --platform <platform>
```

示例：
```bash
# Claude Code
curl -fsSL https://raw.githubusercontent.com/zgsm-sangfor/costrict-skills-repo/main/install.sh | bash -s -- --platform claude-code

# Opencode（在项目根目录执行）
curl -fsSL https://raw.githubusercontent.com/zgsm-sangfor/costrict-skills-repo/main/install.sh | bash -s -- --platform opencode
```

<details>
<summary>如果无法执行 curl | bash（备选方案）</summary>

根据你的平台，手动执行对应命令：

**Claude Code:**（Skill + Commands 全部安装到全局目录）

```bash
mkdir -p ~/.claude/skills/coding-hub
curl -fsSL "https://raw.githubusercontent.com/zgsm-sangfor/costrict-skills-repo/main/platforms/claude-code/skills/coding-hub/SKILL.md" -o ~/.claude/skills/coding-hub/SKILL.md
for cmd in search browse recommend install uninstall update; do
  curl -fsSL "https://raw.githubusercontent.com/zgsm-sangfor/costrict-skills-repo/main/platforms/claude-code/commands/coding-hub/${cmd}.md" -o ~/.claude/skills/coding-hub/${cmd}.md
done
```

**Opencode:**（Skill 全局 + Commands 项目级）

```bash
mkdir -p ~/.opencode/skills/coding-hub
curl -fsSL "https://raw.githubusercontent.com/zgsm-sangfor/costrict-skills-repo/main/platforms/opencode/skills/coding-hub/SKILL.md" -o ~/.opencode/skills/coding-hub/SKILL.md
mkdir -p .opencode/command
for cmd in search browse recommend install uninstall update; do
  curl -fsSL "https://raw.githubusercontent.com/zgsm-sangfor/costrict-skills-repo/main/platforms/opencode/command/coding-hub-${cmd}.md" -o .opencode/command/coding-hub-${cmd}.md
done
```

**Costrict CLI:**（Skill 全局 + Commands 项目级）

```bash
mkdir -p ~/.costrict/skills/coding-hub
curl -fsSL "https://raw.githubusercontent.com/zgsm-sangfor/costrict-skills-repo/main/platforms/costrict/skills/coding-hub/SKILL.md" -o ~/.costrict/skills/coding-hub/SKILL.md
mkdir -p .costrict/coding-hub/commands
for cmd in search browse recommend install uninstall update; do
  curl -fsSL "https://raw.githubusercontent.com/zgsm-sangfor/costrict-skills-repo/main/platforms/costrict/commands/coding-hub/coding-hub-${cmd}.md" -o .costrict/coding-hub/commands/coding-hub-${cmd}.md
done
```

**VSCode Costrict 插件:**（仅 Skill，无需命令）

```bash
mkdir -p ~/.costrict/skills/coding-hub
curl -fsSL "https://raw.githubusercontent.com/zgsm-sangfor/costrict-skills-repo/main/platforms/vscode-costrict/skills/coding-hub/SKILL.md" -o ~/.costrict/skills/coding-hub/SKILL.md
```

> VSCode Costrict 插件无需安装子命令，所有命令逻辑已内置于 SKILL.md。

</details>

### 第 2 步: 验证安装

执行搜索命令验证安装是否成功：

```
# Claude Code
/coding-hub:search typescript

# Opencode / Costrict CLI
/coding-hub-search typescript

# VSCode Costrict 插件
在插件聊天中发送: "用 coding-hub 搜索 typescript"
```

**预期结果**: 返回一个包含搜索结果的 Markdown 表格。如果返回了表格，安装成功。如果提示命令不存在，请检查第 1 步的安装是否正确执行。

### 可用命令

安装成功后，以下命令可用（命令分隔符根据平台不同为 `:` 或 `-`）：

| 命令 | 说明 |
|------|------|
| `search <关键词> [type:mcp\|skill\|rule\|prompt]` | 搜索资源，可按类型筛选 |
| `browse [分类] [type:...]` | 浏览分类 |
| `recommend [type:...]` | 基于当前项目技术栈推荐 |
| `install <名称>` | 安装资源 |
| `uninstall <名称>` | 卸载资源 |
| `update` | 更新到最新版本 |

### 数据源

索引 URL: `https://raw.githubusercontent.com/zgsm-sangfor/costrict-skills-repo/main/catalog/index.json`

索引是 JSON 数组，每个条目包含 `id`, `name`, `type`(mcp/skill/rule/prompt), `description`, `source_url`, `stars`, `category`, `tags`, `tech_stack`, `install`。
