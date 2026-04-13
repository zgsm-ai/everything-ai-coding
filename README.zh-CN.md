<div align="center">
<img src="assets/logo.png" alt="Everything AI Coding logo" width="600" />
<p><strong><!-- README_APPROX_COUNT:START -->4000<!-- README_APPROX_COUNT:END -->+ 精选开发资源一站式索引</strong><br/>MCP Servers · Skills · Rules · Prompts</p>

<p>
  <a href="https://github.com/zgsm-ai/everything-ai-coding/stargazers"><img src="https://img.shields.io/github/stars/zgsm-ai/everything-ai-coding?style=flat-square&color=4A90D9" alt="Stars" /></a>
  <a href="https://github.com/zgsm-ai/everything-ai-coding/blob/main/LICENSE"><img src="https://img.shields.io/github/license/zgsm-ai/everything-ai-coding?style=flat-square" alt="License" /></a>
  <a href="https://github.com/zgsm-ai/everything-ai-coding/commits/main"><img src="https://img.shields.io/github/last-commit/zgsm-ai/everything-ai-coding?style=flat-square" alt="Last Commit" /></a>
  <img src="https://img.shields.io/badge/resources-4040-2ECC71?style=flat-square" alt="Resources" />
</p>

<p>
  <a href="./README.md">English</a> ·
  <a href="./README.zh-CN.md"><strong>简体中文</strong></a>
</p>

<p>
  <a href="#quick-start">快速开始</a> ·
  <a href="https://zgsm-ai.github.io/everything-ai-coding/">浏览目录</a> ·
  <a href="#catalog-overview">目录概览</a> ·
  <a href="#platforms">平台支持</a> ·
  <a href="#for-agents">给 Agent 的安装说明</a> ·
  <a href="#contributing">参与贡献</a>
</p>

</div>
<img src="assets/title-card.jpg" alt="Everything AI Coding title card" width="900" />

## 为什么选择 Everything AI Coding？

AI Coding Agent 越来越强，但周边生态仍然很分散。想找到可靠的 MCP Server、可复用 Skill、实用 Rule 或 Prompt，通常要在多个仓库和格式之间反复跳转。

Everything AI Coding 把这件事做成了一个持续更新的统一目录：自动同步上游资源、去重、富化元数据、补充质量信号，再把结果整理成可以被人和 Agent 直接搜索与安装的入口，让你 **一条命令就能发现并接入资源**。

<a id="quick-start"></a>
## 快速开始

按平台执行安装命令即可：

**macOS / Linux**

```bash
# Costrict CLI（在项目根目录执行）
curl -fsSL https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/install.sh | bash -s -- --platform costrict

# VSCode Costrict 插件
curl -fsSL https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/install.sh | bash -s -- --platform vscode-costrict

# Claude Code
curl -fsSL https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/install.sh | bash -s -- --platform claude-code

# Opencode（在项目根目录执行）
curl -fsSL https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/install.sh | bash -s -- --platform opencode
```

**Windows (PowerShell)**

```powershell
# Costrict CLI
irm https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/install.ps1 | iex

# 自动检测失败时手动指定平台
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/install.ps1))) -Platform costrict
```

安装后可以先试一个搜索命令：

```bash
# Claude Code
/everything-ai-coding:search typescript

# Opencode / Costrict CLI / VSCode Costrict (Roo Code)
/everything-ai-coding-search typescript
```

<video src="https://github.com/user-attachments/assets/552d5405-48c9-4d26-9fb0-34a2715efa24" controls width="100%"></video>

也可以把下面的提示词直接交给另一个 AI Agent：

```text
你是一个自动安装助手。请访问下面的 URL，阅读其中的 "For Agents" 小节，
然后严格按说明完成 Everything AI Coding 安装。

不要 clone 仓库，只读取这个 raw 文件：
https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/README.md

安装结束后，请说明你使用了哪个平台路径，以及验证是否成功。
```

<div align="center">
<h3><a href="https://zgsm-ai.github.io/everything-ai-coding/">浏览完整资源目录 →</a></h3>
<p>通过交互式 Web 目录搜索、筛选和探索全部 4000+ 开发资源。</p>
</div>

<a id="catalog-overview"></a>
## 目录概览

| 类型 | 数量 | 说明 |
|------|------:|------|
| MCP Server | <!-- README_COUNT_MCP:START -->1627<!-- README_COUNT_MCP:END --> | Model Context Protocol 服务器 |
| Prompt | <!-- README_COUNT_PROMPT:START -->532<!-- README_COUNT_PROMPT:END --> | 面向开发者的 Prompt |
| Rule | <!-- README_COUNT_RULE:START -->236<!-- README_COUNT_RULE:END --> | 编码规范与 AI 工作流规则 |
| Skill | <!-- README_COUNT_SKILL:START -->1645<!-- README_COUNT_SKILL:END --> | 可复用的 Agent Skill |

### 数据来源

Everything AI Coding 从多类上游源聚合资源，并通过 GitHub Pages 与 raw GitHub 提供可直接消费的数据接口。

| 类型 | 来源 |
|------|------|
| MCP | [awesome-mcp-servers](https://github.com/wong2/awesome-mcp-servers) · [Awesome-MCP-ZH](https://github.com/yzfly/Awesome-MCP-ZH) · [mcp.so](https://mcp.so) |
| Skills | Tier 1: [anthropics/skills](https://github.com/anthropics/skills) · [Ai-Agent-Skills](https://github.com/skillcreatorai/Ai-Agent-Skills) · [antigravity-awesome-skills](https://github.com/sickn33/antigravity-awesome-skills) · [ai-agents-public](https://github.com/vasilyu1983/ai-agents-public)<br/>Tier 2: [awesome-repo-configs / skill_repos.json](https://github.com/Chat2AnyLLM/awesome-repo-configs) · [awesome-openclaw-skills](https://github.com/VoltAgent/awesome-openclaw-skills) · [openclaw/skills](https://github.com/openclaw/skills)<br/>Tier 3: `catalog/skills/curated.json` |
| Rules | [awesome-cursorrules](https://github.com/PatrickJS/awesome-cursorrules) · [rules-2.1-optimized](https://github.com/Mr-chen-05/rules-2.1-optimized) |
| Prompts | [prompts.chat](https://github.com/f/prompts.chat) · [wonderful-prompts](https://github.com/langgptai/wonderful-prompts) |

### 流水线概览

1. **同步**：`scripts/sync_*.py` 从上游拉取 MCP、Skill、Rule、Prompt 数据。
2. **合并**：`scripts/merge_index.py` 完成去重、富化、评分治理，并生成统一目录。
3. **评估**：根据来源可信度、相关性、内容质量、活跃度与可安装性等信号综合排序。
4. **发布**：GitHub Actions 每周自动刷新目录、生成轻量 API，并同步更新中英文 README。

<details>
<summary>项目结构</summary>

```text
everything-ai-coding/
├── install.sh                    # macOS/Linux 一键安装脚本
├── install.ps1                   # Windows 一键安装脚本
├── catalog/                      # 生成后的资源目录数据
│   ├── index.json                # 完整合并索引
│   ├── search-index.json         # 轻量搜索索引
│   ├── mcp/ skills/ rules/ prompts/
│   └── maintenance/              # 增量复抓状态
├── docs/api/                     # GitHub Pages 静态 API
├── platforms/                    # 各平台 skill 与命令定义
├── scripts/                      # 同步、合并、评分、发布脚本
├── .github/workflows/            # CI 自动化
```

</details>

<a id="platforms"></a>
## 平台支持

Everything AI Coding 当前支持四个 AI Coding 平台，共用同一份资源目录，但命令格式与安装路径略有差异。

| | Claude Code | Costrict | Opencode | VSCode Costrict (Roo Code) |
|---|---|---|---|---|
| 搜索 | `/everything-ai-coding:search <kw> [type:mcp]` | `/everything-ai-coding-search <kw> [type:mcp]` | `/everything-ai-coding-search <kw> [type:mcp]` | `/everything-ai-coding-search <kw> [type:mcp]` |
| 浏览 | `/everything-ai-coding:browse [category]` | `/everything-ai-coding-browse [category]` | `/everything-ai-coding-browse [category]` | `/everything-ai-coding-browse [category]` |
| 推荐 | `/everything-ai-coding:recommend` | `/everything-ai-coding-recommend` | `/everything-ai-coding-recommend` | `/everything-ai-coding-recommend` |
| 安装 | `/everything-ai-coding:install <name>` | `/everything-ai-coding-install <name>` | `/everything-ai-coding-install <name>` | `/everything-ai-coding-install <name>` |
| 卸载 | `/everything-ai-coding:uninstall <name>` | `/everything-ai-coding-uninstall <name>` | `/everything-ai-coding-uninstall <name>` | `/everything-ai-coding-uninstall <name>` |
| 更新 | `/everything-ai-coding:update` | `/everything-ai-coding-update` | `/everything-ai-coding-update` | `/everything-ai-coding-update` |

<details>
<summary>平台路径差异</summary>

| | Claude Code | Costrict | VSCode Costrict | Opencode |
|---|---|---|---|---|
| 全局 Skill 路径 | `~/.claude/skills/everything-ai-coding/` | `~/.costrict/skills/everything-ai-coding/` | `~/.costrict/skills/everything-ai-coding/` | `~/.opencode/skills/everything-ai-coding/` |
| 命令路径 | 同一全局目录 | `.costrict/everything-ai-coding/commands/`（项目级） | `~/.roo/commands/`（全局） | `.opencode/command/`（项目级） |
| 分隔符 | `:` | `-` | `-` | `-` |

- **Costrict CLI** 需要在每个项目根目录安装命令文件。
- **VSCode Costrict / Roo Code** 将命令文件安装到全局 `~/.roo/commands/`。
- **Claude Code** 可以从全局技能目录直接加载完整 skill 与子命令。
- **Opencode** 需要在每个项目下安装 `.opencode/command/` 中的命令文件。

</details>

<a id="for-agents"></a>
## 给 Agent 的安装说明

> 如果你是自动安装 Everything AI Coding 的 AI Agent，请严格按本节操作。

### 第 1 步：运行安装脚本

安装脚本会尽量自动识别你当前所在的平台。

**macOS / Linux**

```bash
curl -fsSL https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/install.sh | bash
```

**Windows (PowerShell)**

```powershell
irm https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/install.ps1 | iex
```

自动识别依赖以下进程级环境变量：

| 环境变量 | 平台 |
|----------|------|
| `COSTRICT_CALLER=vscode` | VSCode Costrict 插件 |
| `COSTRICT_RUNNING=1` | Costrict CLI |
| `CLAUDECODE=1` | Claude Code |
| `OPENCODE=1` | Opencode |

如果自动识别失败，请手动指定平台。

**macOS / Linux**

```bash
curl -fsSL https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/install.sh | bash -s -- --platform <platform>
```

**Windows (PowerShell)**

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/install.ps1))) -Platform <platform>
```

示例：

```bash
# Claude Code (macOS/Linux)
curl -fsSL https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/install.sh | bash -s -- --platform claude-code

# Opencode（在项目根目录执行）
curl -fsSL https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/install.sh | bash -s -- --platform opencode
```

```powershell
# Claude Code (Windows)
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/install.ps1))) -Platform claude-code
```

<details>
<summary>备选方案：手动下载文件，不使用 <code>curl | bash</code></summary>

当你不能直接执行安装脚本时，可以按平台分别下载 skill 和命令文件。

**Costrict CLI**（Skill 全局 + Commands 项目级）

```bash
mkdir -p ~/.costrict/skills/everything-ai-coding
curl -fsSL "https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/platforms/costrict/skills/everything-ai-coding/SKILL.md" -o ~/.costrict/skills/everything-ai-coding/SKILL.md
mkdir -p .costrict/everything-ai-coding/commands
for cmd in search browse recommend install uninstall update; do
  curl -fsSL "https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/platforms/costrict/commands/everything-ai-coding/everything-ai-coding-${cmd}.md" -o .costrict/everything-ai-coding/commands/everything-ai-coding-${cmd}.md
done
```

**VSCode Costrict 插件 / Roo Code**（Skill 全局 + Commands 全局）

```bash
mkdir -p ~/.costrict/skills/everything-ai-coding
curl -fsSL "https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/platforms/vscode-costrict/skills/everything-ai-coding/SKILL.md" -o ~/.costrict/skills/everything-ai-coding/SKILL.md
mkdir -p ~/.roo/commands
for cmd in search browse recommend install uninstall update; do
  curl -fsSL "https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/platforms/vscode-costrict/commands/everything-ai-coding/everything-ai-coding-${cmd}.md" -o ~/.roo/commands/everything-ai-coding-${cmd}.md
done
```

**Claude Code**（Skill + Commands 全局安装）

```bash
mkdir -p ~/.claude/skills/everything-ai-coding
curl -fsSL "https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/platforms/claude-code/skills/everything-ai-coding/SKILL.md" -o ~/.claude/skills/everything-ai-coding/SKILL.md
for cmd in search browse recommend install uninstall update; do
  curl -fsSL "https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/platforms/claude-code/commands/everything-ai-coding/${cmd}.md" -o ~/.claude/skills/everything-ai-coding/${cmd}.md
done
```

**Opencode**（Skill 全局 + Commands 项目级）

```bash
mkdir -p ~/.opencode/skills/everything-ai-coding
curl -fsSL "https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/platforms/opencode/skills/everything-ai-coding/SKILL.md" -o ~/.opencode/skills/everything-ai-coding/SKILL.md
mkdir -p .opencode/command
for cmd in search browse recommend install uninstall update; do
  curl -fsSL "https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/platforms/opencode/command/everything-ai-coding-${cmd}.md" -o .opencode/command/everything-ai-coding-${cmd}.md
done
```

</details>

### 第 2 步：验证安装是否成功

运行搜索命令确认命令是否可用：

```text
# Costrict CLI / Opencode
/everything-ai-coding-search typescript

# VSCode Costrict 插件
在聊天窗口发送："用 everything-ai-coding 搜索 typescript"

# Claude Code
/everything-ai-coding:search typescript
```

期望结果：返回一个 Markdown 表格，列出匹配资源。如果命令不存在，说明文件没有安装到正确的平台路径。

### 可用命令

| 命令 | 说明 |
|------|------|
| `search <关键词> [type:mcp\|skill\|rule\|prompt]` | 搜索资源，可按类型过滤 |
| `browse [分类] [type:...]` | 按分类浏览 |
| `recommend [type:...]` | 根据当前项目技术栈推荐资源 |
| `install <名称>` | 安装资源 |
| `uninstall <名称>` | 卸载资源 |
| `update` | 更新到最新版本 |

### 数据接口

搜索、浏览、推荐依赖轻量搜索索引，安装则读取单条资源 API：

| 用途 | URL |
|------|-----|
| 搜索索引 | `https://zgsm-ai.github.io/everything-ai-coding/api/v1/search-index.json` |
| 单条 API | `https://zgsm-ai.github.io/everything-ai-coding/api/v1/{type}/{id}.json` |
| 类型索引 | `https://zgsm-ai.github.io/everything-ai-coding/api/v1/{type}/index.json` |
| 全量索引回退地址 | `https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/catalog/index.json` |

## 为什么推荐 Costrict？

如果你喜欢 Everything AI Coding 的工作流，也可以试试 **[Costrict](https://github.com/zgsm-ai/costrict)** —— 我们更完整的 AI Coding Agent 平台，适合更强的自动化与团队协作场景。

[立即了解 Costrict →](https://github.com/zgsm-ai/costrict)

<a id="contributing"></a>
## 参与贡献

欢迎提交 PR，为 `catalog/` 下相应目录补充优质资源。提交前请确保：

- 资源与编程或 AI 辅助开发相关，
- `source_url`、`description`、tags 等字段准确，
- 数据格式符合 `catalog/schema.json`。

如果你需要的是维护视角的上下文，而不是快速安装说明，可以继续看仓库内 wiki：[`docs/wiki/`](./docs/wiki/README.md)。

## 免责声明

Everything AI Coding 是一个第三方开源资源的索引与安装辅助项目。目录中的 MCP Server、Skill、Rule、Prompt 的版权与责任均归原作者所有。

本仓库 **不对** 第三方资源的安全性、可用性、准确性或合规性作任何保证。请在使用前自行审查源码与许可证；如果发现安全或版权问题，欢迎通过 Issue 反馈。

本项目遵循 [MIT License](LICENSE) 发布。
