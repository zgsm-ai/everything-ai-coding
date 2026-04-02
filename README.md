# Coding Hub

<div align="center">
<img src="assets/title-card.jpg" alt="Coding Hub" />

<p><strong>3900+ 精选开发资源一站式索引</strong><br/>MCP Servers · Skills · Rules · Prompts</p>

<p>
  <a href="https://github.com/zgsm-sangfor/costrict-coding-hub/stargazers"><img src="https://img.shields.io/github/stars/zgsm-sangfor/costrict-coding-hub?style=flat-square&color=4A90D9" alt="Stars" /></a>
  <a href="https://github.com/zgsm-sangfor/costrict-coding-hub/blob/main/LICENSE"><img src="https://img.shields.io/github/license/zgsm-sangfor/costrict-coding-hub?style=flat-square" alt="License" /></a>
  <a href="https://github.com/zgsm-sangfor/costrict-coding-hub/commits/main"><img src="https://img.shields.io/github/last-commit/zgsm-sangfor/costrict-coding-hub?style=flat-square" alt="Last Commit" /></a>
  <img src="https://img.shields.io/badge/resources-3907-2ECC71?style=flat-square" alt="Resources" />
</p>

<p>
  <a href="#-精选推荐">精选推荐</a> ·
  <a href="#quick-start">Quick Start</a> ·
  <a href="#features">Features</a> ·
  <a href="#platforms">Platforms</a> ·
  <a href="#for-agents">For Agents</a> ·
  <a href="#contributing">Contributing</a>
</p>

</div>

## Why Coding Hub?

AI Coding Agent 越来越强，但找到合适的 MCP Server、Skill、Rule 仍然是碎片化的。

Coding Hub 从 9 个上游源自动聚合、过滤、评估，让你和你的 Agent **一条命令就能搜索和安装**开发资源。

## Quick Start

一条命令安装，指定你的平台：

**macOS / Linux：**

```bash
# Costrict CLI（在项目根目录执行）
curl -fsSL https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/install.sh | bash -s -- --platform costrict

# VSCode Costrict 插件
curl -fsSL https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/install.sh | bash -s -- --platform vscode-costrict

# Claude Code
curl -fsSL https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/install.sh | bash -s -- --platform claude-code

# Opencode（在项目根目录执行）
curl -fsSL https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/install.sh | bash -s -- --platform opencode
```

**Windows (PowerShell)：**

```powershell
# Costrict CLI
irm https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/install.ps1 | iex

# 指定平台（如自动检测失败）
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/install.ps1))) -Platform costrict
```

安装完成后试试：

```bash
# Claude Code
/coding-hub:search typescript

# Opencode / Costrict CLI / VSCode Costrict (Roo Code)
/coding-hub-search typescript
```

或者复制以下 prompt 丢给你的 AI Agent：

```
你是一个自动化安装助手。请访问以下 URL 并阅读其中的 "For Agents" 部分，
严格按照步骤完成 coding-hub 技能的安装。

不要 clone 整个仓库，只需要读取这个 raw URL 的内容：
https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/README.md

根据你所在的平台（Claude Code / Opencode / Costrict CLI / VSCode Costrict），
执行对应的安装命令。安装完成后告诉我结果。
```

---


## ⭐ 精选推荐

> 从 3907+ 资源中按使用场景精选。安装后用 `/coding-hub:search` 搜索完整索引，或 `/coding-hub:recommend` 获取项目级推荐。

### 🌐 浏览器 & 自动化

- 🔌 **[microsoft/playwright-mcp](https://github.com/microsoft/playwright-mcp)** — 微软官方出品，使用 Playwright 让 AI 精确控制网页，自动化抓取数据。 ⭐ 30.1k
- 🔌 **[ScrapeGraphAI](https://github.com/ScrapeGraphAI/Scrapegraph-ai)** — AI-powered web scraping library that creates scraping pipelines using… ⭐ 23.2k
- 🔌 **[Skyvern](https://github.com/Skyvern-AI/skyvern/tree/main/integrations/mcp)** — MCP Server to let Claude / your AI control the browser ⭐ 21.0k
- 🔌 **[Agent Reach](https://github.com/Panniantong/Agent-Reach)** — 一句话给 AI Agent 装上全网搜索能力。一键安装 + 配置 13+ 平台工具（Twitter、Reddit、YouTube、GitHu… ⭐ 14.4k
- 🎯 **[webapp-testing](https://github.com/anthropics/skills/tree/main/skills/webapp-testing)** — Toolkit for interacting with and testing local web applications using… `Anthropic 官方`
- 🎯 **[audit-library-health](https://github.com/skillcreatorai/Ai-Agent-Skills/tree/main/skills/audit-library-health)** — Use when checking the overall health of a skills library. Run doctor,… `社区精选`
- 📋 **[Ai Powered Code Review (Rules 2.1)](https://github.com/Mr-chen-05/rules-2.1-optimized/tree/master/project-rules)** — AI驱动的智能代码审查规则 - 基于机器学习的代码质量分析和自动化审查流程 `Rules 2.1`
- 📋 **[Commit (Rules 2.1)](https://github.com/Mr-chen-05/rules-2.1-optimized/tree/master/project-rules)** — Unified comprehensive commit workflow (standard + fast + AI) - 统一全面提交工… `Rules 2.1`
- 💡 **[资深编程专家 CAN](https://github.com/langgptai/wonderful-prompts)** — 实测 GPT-4 才可以有比较好的效果，完整的对话：  [示例——CAN 完整对话](examples/gpt4_CAN_coder.md)… `wonderful-prompts`

### 🐙 Git & 协作

- 🔌 **[github/github-mcp-server](https://github.com/github/github-mcp-server)** — GitHub 官方出品，让 AI 通过 API 深度集成 GitHub，实现自动化工作流等。 ⭐ 28.5k
- 🔌 **[idosal/git-mcp](https://github.com/idosal/git-mcp)** — 通用远程 MCP 服务器，用于连接任何 GitHub 仓库或项目以获取文档。 ⭐ 7.9k
- 🔌 **[Chart](https://github.com/antvis/mcp-server-chart)** — 🤖 A Model Context Protocol server for generating visual charts using… ⭐ 3.9k
- 🔌 **[julien040/anyquery](https://github.com/julien040/anyquery)** — 通过 SQL 查询 40+ 应用，并连接 PG/MySQL/SQLite 数据库。本地优先，注重隐私。 ⭐ 1.7k
- 🎯 **[changelog-generator](https://github.com/skillcreatorai/Ai-Agent-Skills/tree/main/skills/changelog-generator)** — Automatically creates user-facing changelogs from git commits by… `社区精选`
- 🎯 **[address-github-comments](https://github.com/sickn33/antigravity-awesome-skills/tree/main/skills/address-github-comments)** — Use when you need to address review or issue comments on an open… `antigravity-skills`
- 📋 **[Analyze Issue (Rules 2.1)](https://github.com/Mr-chen-05/rules-2.1-optimized/tree/master/project-rules)** — GitHub issue analysis and implementation specification - GitHub问题分析和实现… `Rules 2.1`
- 📋 **[Python Github Setup Cursorrules Prompt File Rules](https://github.com/PatrickJS/awesome-cursorrules/tree/main/rules/python-github-setup-cursorrules-prompt-file)** — Python GitHub Setup .cursorrules prompt file `CursorRules`
- 💡 **[Commit Message Preparation](https://github.com/f/prompts.chat)** — # Git Commit Guidelines for AI Language Models  ## Core Principles … `prompts.chat`

### 🚀 DevOps & 安全

- 🔌 **[FastAPI-MCP](https://github.com/tadata-org/fastapi_mcp)** — Expose your FastAPI endpoints as Model Context Protocol (MCP) tools,… ⭐ 11.7k
- 🔌 **[Nginx UI](https://github.com/0xJacky/nginx-ui)** — Yet another WebUI for Nginx ⭐ 10.9k
- 🔌 **[AWS CDK](https://github.com/awslabs/mcp/tree/main/src/cdk-mcp-server)** — Get prescriptive CDK advice, explain CDK Nag rules, check… ⭐ 8.6k
- 🔌 **[ghidraMCP](https://github.com/LaurieWired/GhidraMCP)** — MCP Server for Ghidra ⭐ 8.1k
- 🎯 **[doc-coauthoring](https://github.com/anthropics/skills/tree/main/skills/doc-coauthoring)** — Guide users through a structured workflow for co-authoring… `Anthropic 官方`
- 🎯 **[ask-questions-if-underspecified](https://github.com/skillcreatorai/Ai-Agent-Skills/tree/main/skills/ask-questions-if-underspecified)** — Clarify requirements before implementing. Do not use automatically,… `社区精选`
- 📋 **[Security Audit Rules](https://github.com/Mr-chen-05/rules-2.1-optimized/tree/master/project-rules)** — AI-assisted security review rules covering OWASP, input validation,… `精选`
- 📋 **[Permission Control System (Rules 2.1)](https://github.com/Mr-chen-05/rules-2.1-optimized/tree/master/global-rules)** — 权限控制系统 - 定义用户/AI/系统的角色权限和操作审计 `Rules 2.1`
- 💡 **[模拟 Linux 终端](https://github.com/langgptai/wonderful-prompts)** — 我想让你充当 Linux 终端。我将输入命令，您将回复终端应显示的内容。我希望您只在一个唯一的代码块内回复终端输出，而不是其他任何内容。不要… `wonderful-prompts`

### 📚 文档 & 知识

- 🔌 **[microsoft/markitdown](https://github.com/microsoft/markitdown/tree/main/packages/markitdown-mcp)** — MarkItDown MCP 工具访问 - 一个将多种文件格式（本地或远程）转换为 Markdown 以供 LLM 使用的库。 ⭐ 93.1k
- 🔌 **[Context 7](https://github.com/upstash/context7-mcp)** — Context7 MCP - Up-to-date Docs For Any Cursor Prompt ⭐ 51.4k
- 🔌 **[Mastra/mcp-docs-server](https://github.com/mastra-ai/mastra/tree/main/packages/mcp-docs-server)** — Provides AI assistants with direct access to Mastra.ai's complete… ⭐ 22.6k
- 🔌 **[cognee-mcp](https://github.com/topoteretes/cognee/tree/main/cognee-mcp)** — GraphRAG 记忆服务器，支持自定义摄取、数据处理和搜索。 ⭐ 14.8k
- 🎯 **[slack-gif-creator](https://github.com/anthropics/skills/tree/main/skills/slack-gif-creator)** — Knowledge and utilities for creating animated GIFs optimized for… `Anthropic 官方`
- 🎯 **[theme-factory](https://github.com/anthropics/skills/tree/main/skills/theme-factory)** — Toolkit for styling artifacts with a theme. These artifacts can be… `Anthropic 官方`
- 📋 **[Technical Documentation Rules](https://github.com/Mr-chen-05/rules-2.1-optimized/tree/master/project-rules)** — AI rules for generating and maintaining technical documentation `精选`
- 📋 **[Mermaid (Rules 2.1)](https://github.com/Mr-chen-05/rules-2.1-optimized/tree/master/project-rules)** — Mermaid diagram generation for various visualizations - Mermaid图表生成工具 `Rules 2.1`
- 💡 **["Explain It Like I Built It"  Technical Documentation for Non-Technical Founders](https://github.com/f/prompts.chat)** — You are a senior technical writer who specializes in making complex… `prompts.chat`

### 🎨 前端 & 设计

- 🔌 **[mediar-ai/screenpipe](https://github.com/mediar-ai/screenpipe)** — 本地优先系统，捕获屏幕/音频并带时间戳索引，SQL/嵌入存储，语义搜索，LLM 历史分析，事件触发动作。通过 NextJS 插件生态系统构建… ⭐ 17.9k
- 🔌 **[Framelink Figma MCP Server](https://github.com/GLips/Figma-Context-MCP)** — MCP server to provide Figma layout information to AI coding agents… ⭐ 14.0k
- 🔌 **[Inbox Zero](https://github.com/elie222/inbox-zero/tree/main/apps/mcp-server)** — Inbox Zero 官方集成，AI 个人邮件助手 (基于 Gmail，提供需回复/需跟进邮件识别等功能)。 ⭐ 10.4k
- 🔌 **[Lingo.dev](https://github.com/lingodotdev/lingo.dev/blob/main/mcp.md)** — Make your AI agent speak every language on the planet, using… ⭐ 5.4k
- 🎯 **[brand-guidelines](https://github.com/anthropics/skills/tree/main/skills/brand-guidelines)** — Applies Anthropic's official brand colors and typography to any sort… `Anthropic 官方`
- 🎯 **[canvas-design](https://github.com/anthropics/skills/tree/main/skills/canvas-design)** — Create beautiful visual art in .png and .pdf documents using design… `Anthropic 官方`
- 📋 **[Frontend Rules (Rules 2.1)](https://github.com/Mr-chen-05/rules-2.1-optimized/tree/master/global-rules)** — 前端开发AI助手规则 - 智能化企业级标准，集成最新前端技术栈和智能MCP工具编排 `Rules 2.1`
- 📋 **[Frontend Dev (Rules 2.1)](https://github.com/Mr-chen-05/rules-2.1-optimized/tree/master/project-rules)** — Frontend development workflow with Vue/React/TypeScript - 前端开发完整工作流 `Rules 2.1`
- 💡 **[Fullstack Software Developer](https://github.com/f/prompts.chat)** — Act as a fullstack developer with expertise in both frontend and… `精选`

### ⚙️ 后端 & 数据库

- 🔌 **[pydantic/pydantic-ai/mcp-run-python](https://github.com/pydantic/pydantic-ai/tree/main/mcp-run-python)** — Pydantic 出品，在安全的沙盒环境中运行 Python 代码，适合开发编程代理。 ⭐ 16.0k
- 🔌 **[googleapis/genai-toolbox](https://github.com/googleapis/genai-toolbox)** — Google 官方开源 MCP 服务器，专注于为数据库提供简单、快速、安全的工具。 ⭐ 13.6k
- 🔌 **[InstantDB](https://github.com/instantdb/instant/tree/main/client/packages/mcp)** — Create, manage, and update applications on InstantDB, the modern… ⭐ 9.8k
- 🔌 **[Supabase MCP Servers](https://github.com/supabase-community/mcp-supabase)** — A collection of MCP servers that connect LLMs to Supabase ⭐ 2.6k
- 🎯 **[PocketBase Hooks](https://github.com/davila7/claude-code-templates/tree/main/cli-tool/components/skills/pocketbase/pb-hooks)** — Server-side JavaScript hooks for PocketBase (pb_hooks). Use when… `davila7/claude-code-templates`
- 🎯 **[alphafold-database](https://github.com/davila7/claude-code-templates/tree/main/cli-tool/components/skills/scientific/alphafold-database)** — Access AlphaFold's 200M+ AI-predicted protein structures. Retrieve… `davila7/claude-code-templates`
- 📋 **[Supabase Rules](https://github.com/PatrickJS/awesome-cursorrules/tree/main/rules/supabase)** — Cursor rules for Supabase with PostgreSQL and Edge Functions `精选`
- 📋 **[Backend Dev (Rules 2.1)](https://github.com/Mr-chen-05/rules-2.1-optimized/tree/master/project-rules)** — Backend development workflow with Java/Python/Node.js - 后端开发完整工作流 `Rules 2.1`
- 💡 **[编写函数(Python 为例)](https://github.com/langgptai/wonderful-prompts)** — 使用 ChatGPT 编写 Python 函数计算三角形面积。给出 （1）函数描述；（2）函数定义；（3）函数输出。搭建如示例的代码框架，让… `wonderful-prompts`

### 🤖 AI & MCP 开发

- 🔌 **[modelcontextprotocol/server-filesystem](https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem)** — 官方参考实现，提供对本地文件系统的直接访问，带可配置权限。 ⭐ 82.7k
- 🔌 **[Homebrew](https://github.com/Homebrew/brew/blob/HEAD/Library/Homebrew/mcp_server.rb)** — An MCP server for the Homebrew package manager. ⭐ 47.2k
- 🔌 **[claude-cookbooks](https://github.com/anthropics/anthropic-cookbook)** — A collection of notebooks/recipes showcasing some fun and effective… ⭐ 36.6k
- 🔌 **[FastMCP v2 🚀](https://github.com/jlowin/fastmcp)** — 🚀 The fast, Pythonic way to build MCP servers and clients ⭐ 24.0k
- 🎯 **[algorithmic-art](https://github.com/anthropics/skills/tree/main/skills/algorithmic-art)** — Creating algorithmic art using p5.js with seeded randomness and… `Anthropic 官方`
- 🎯 **[claude-api](https://github.com/anthropics/skills/tree/main/skills/claude-api)** — Build apps with the Claude API or Anthropic SDK. TRIGGER when: code… `Anthropic 官方`
- 📋 **[Super Brain System (Rules 2.1)](https://github.com/Mr-chen-05/rules-2.1-optimized/tree/master/global-rules)** — 超级大脑系统 - 智能项目管理激活机制和核心功能 `Rules 2.1`
- 📋 **[Ai Ethical Boundaries (Rules 2.1)](https://github.com/Mr-chen-05/rules-2.1-optimized/tree/master/global-rules)** — AI伦理边界规则 - 确保AI行为符合伦理标准和社会价值观 `Rules 2.1`
- 💡 **[混淆代码翻译](https://github.com/langgptai/wonderful-prompts)** — 分析这段代码是什么编程语言，功能是什么？然后翻译整段代码，把所有变量和函数都重命名，使其成为更加清晰易懂的代码 `wonderful-prompts`

> 图例：🔌 MCP Server · 🎯 Skill · 📋 Rule · 💡 Prompt


## Features

| 类型 | 数量 | 说明 |
|------|------|------|
| MCP Server | 1629 | Model Context Protocol 服务器 |
| Prompt | 524 | 开发者专用 Prompt |
| Rule | 236 | 编码规范 / AI 辅助规则 |
| Skill | 1518 | Agent Skill 扩展 |

**数据来源**：从 14 个上游源自动聚合，每周通过 GitHub Actions 同步并部署到 GitHub Pages CDN，过滤 star > 10 的 coding 相关资源。

| 上游 | 来源 |
|------|------|
| MCP | [awesome-mcp-servers](https://github.com/wong2/awesome-mcp-servers) · [Awesome-MCP-ZH](https://github.com/yzfly/Awesome-MCP-ZH) · [mcp.so](https://mcp.so) |
| Skills | [anthropics/skills](https://github.com/anthropics/skills) · [Ai-Agent-Skills](https://github.com/skillcreatorai/Ai-Agent-Skills) · [antigravity-awesome-skills](https://github.com/sickn33/antigravity-awesome-skills) · [davila7/claude-code-templates](https://github.com/davila7/claude-code-templates) |
| Rules | [awesome-cursorrules](https://github.com/PatrickJS/awesome-cursorrules) · [rules-2.1-optimized](https://github.com/Mr-chen-05/rules-2.1-optimized) |
| Prompts | [prompts.chat](https://github.com/f/prompts.chat) · [wonderful-prompts](https://github.com/langgptai/wonderful-prompts) |

### 📊 质量筛选标准

我们通过三层过滤确保资源质量：

**第一层：基础过滤**
- ⭐ Star 数 > 10（活跃度指标）
- 📅 最近 6 个月有更新（维护状态）
- 🏷️ 明确标注为 coding 相关

**第二层：分类评估**

| 类型 | 筛选策略 |
|------|---------|
| **MCP Servers** | 从 awesome-mcp-servers + Awesome-MCP-ZH + mcp.so 聚合，按独立仓库去重 |
| **Skills** | Tier 1: anthropics/skills + Ai-Agent-Skills + antigravity-awesome-skills（全量）<br/>Tier 2: GitHub 搜索 + LLM 质量评估（TOP 300）<br/>Tier 3: 手工精选（curated.json） |
| **Rules** | awesome-cursorrules + rules-2.1-optimized，优先实用性和标签丰富度 |
| **Prompts** | prompts.chat + wonderful-prompts，优先 coding 相关和中文资源 |

**第三层：持续更新**
- 🤖 每周自动同步（GitHub Actions）
- 🔄 自动去重和合并
- 📈 动态更新 star 数和活跃度
- 🌐 GitHub Pages CDN 加速分发（单条 API ~1KB，搜索索引 ~2MB）

### 🔁 生命周期与增量维护

- `mcp` / `skill` 条目会记录 `added_at`，表示首次进入 catalog 的日期
- `catalog/index.json` 保留顶层兼容字段，同时新增 `evaluation` 子对象承载统一评分与收录原因
- `catalog/maintenance/incremental_recrawl_candidates.json` 保存达到阈值的增量复抓候选，`incremental_recrawl_state.json` 保存去重/冷却状态
- 现有 `catalog/mcp/crawl_state.json` 与 `catalog/skills/.repo_cache.json` 继续负责各自来源的增量同步，不直接替代 catalog 生命周期治理


## Platforms

支持四个 AI Coding 平台，命令格式略有差异：

| | Claude Code | Costrict | Opencode | VSCode Costrict (Roo Code) |
|---|---|---|---|---|
| 搜索 | `/coding-hub:search <kw> [type:mcp]` | `/coding-hub-search <kw> [type:mcp]` | `/coding-hub-search <kw> [type:mcp]` | `/coding-hub-search <kw> [type:mcp]` |
| 浏览 | `/coding-hub:browse [cat]` | `/coding-hub-browse [cat]` | `/coding-hub-browse [cat]` | `/coding-hub-browse [cat]` |
| 推荐 | `/coding-hub:recommend` | `/coding-hub-recommend` | `/coding-hub-recommend` | `/coding-hub-recommend` |
| 安装 | `/coding-hub:install <name>` | `/coding-hub-install <name>` | `/coding-hub-install <name>` | `/coding-hub-install <name>` |
| 卸载 | `/coding-hub:uninstall <name>` | `/coding-hub-uninstall <name>` | `/coding-hub-uninstall <name>` | `/coding-hub-uninstall <name>` |
| 更新 | `/coding-hub:update` | `/coding-hub-update` | `/coding-hub-update` | `/coding-hub-update` |

<details>
<summary>平台路径差异</summary>

| | Claude Code | Costrict | VSCode Costrict | Opencode |
|---|---|---|---|---|
| Skill 路径（全局） | `~/.claude/skills/coding-hub/` | `~/.costrict/skills/coding-hub/` | `~/.costrict/skills/coding-hub/` | `~/.opencode/skills/coding-hub/` |
| Commands 路径 | 同上（全局） | `.costrict/coding-hub/commands/`（项目级） | `~/.roo/commands/`（全局） | `.opencode/command/`（项目级） |
| 命令分隔符 | `:` | `-` | `-` | `-` |

- **Costrict CLI** 的命令文件需要安装到每个项目目录，在项目根目录运行 `install.sh` 即可
- **VSCode Costrict 插件 (Roo Code)** 支持 Roo Code 原生 slash commands，命令文件安装到 `~/.roo/commands/`，通过 `/coding-hub-update` 自动下载
- **Claude Code** 支持从全局 skills 目录加载子命令，一次安装所有项目可用
- **Opencode** 的命令文件需要安装到每个项目目录，在项目根目录运行 `install.sh` 即可

</details>

<details>
<summary>项目结构</summary>

```
costrict-coding-hub/
├── install.sh               # 一键安装脚本（macOS/Linux，curl | bash）
├── install.ps1              # 一键安装脚本（Windows，irm | iex）
├── catalog/                  # 资源索引（数据层）
│   ├── index.json            # 合并后的完整索引（3900+ 条）
│   ├── search-index.json     # 轻量搜索索引（仅搜索字段，~2MB）
│   ├── schema.json           # 条目 schema 定义
│   ├── mcp/                  # MCP Server 源数据（含 added_at 生命周期字段）
│   ├── skills/               # Skill 源数据（含 added_at 生命周期字段）
│   ├── rules/                # Rule 源数据
│   ├── prompts/              # Prompt 源数据
│   └── maintenance/          # 增量复抓候选与状态
│
├── docs/api/                 # GitHub Pages 静态 API（CI 生成，不提交）
│   └── v1/                   # API v1
│       ├── search-index.json # 搜索索引副本
│       ├── {type}/index.json # 各类型轻量索引
│       └── {type}/{id}.json  # 单条完整数据（~1-2KB）
│
├── platforms/                # 各平台 Skill + 子命令
│   ├── claude-code/          # Claude Code 格式（命令分隔符 `:`）
│   ├── opencode/             # Opencode 格式
│   ├── costrict/             # Costrict 格式
│   └── vscode-costrict/      # VSCode Costrict 插件格式
│
├── scripts/                  # 数据同步与生成脚本
│   ├── sync_mcp.py           # 从上游同步 MCP
│   ├── sync_skills.py        # 从上游同步 Skills
│   ├── sync_rules.py         # 从上游同步 Rules
│   ├── sync_prompts.py       # 从上游同步 Prompts
│   ├── crawl_mcp_so.py       # 增量抓取 mcp.so
│   ├── merge_index.py        # 合并生成 index.json（去重→富化→评分→生命周期）
│   ├── generate_pages.py     # 生成 GitHub Pages 静态 API（按条目拆分）
│   ├── update_readme.py      # 自动更新 README 统计数字
│   ├── enrichment_orchestrator.py  # 富化调度
│   ├── unified_enrichment.py       # Layer 2: source_trust, confidence
│   ├── llm_evaluator.py            # LLM 质量评估
│   ├── scoring_governor.py         # 评分治理: final_score 加权
│   ├── health_scorer.py            # 健康评分四维信号
│   ├── catalog_lifecycle.py        # 生命周期字段与增量复抓
│   └── utils.py                    # 公共工具函数
│
├── .github/workflows/        # CI/CD
│   ├── sync.yml              # 每周自动同步上游资源
│   ├── deploy-pages.yml      # 同步后自动部署 GitHub Pages 静态 API
│   ├── test.yml              # PR 测试
│   └── validate-pr.yml       # PR 校验
│
└── openspec/                 # 变更管理（OpenSpec）
```

</details>

## For Agents

> **AI Agent 请阅读本节完成自动安装。** 请严格按照以下步骤执行，不要跳过任何一步。

### 第 1 步: 一键安装

安装脚本支持自动检测平台，直接执行即可：

**macOS / Linux：**

```bash
curl -fsSL https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/install.sh | bash
```

**Windows (PowerShell)：**

```powershell
irm https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/install.ps1 | iex
```

脚本通过以下**进程级环境变量**自动识别平台（这些变量由各平台进程启动时注入，不会互相污染）：

| 环境变量 | 平台 |
|---------|------|
| `COSTRICT_CALLER=vscode` | VSCode Costrict 插件 |
| `COSTRICT_RUNNING=1` | Costrict CLI |
| `CLAUDECODE=1` | Claude Code |
| `OPENCODE=1` | Opencode |


如果自动检测失败，可以手动指定：

**macOS / Linux：**
```bash
curl -fsSL https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/install.sh | bash -s -- --platform <platform>
```

**Windows (PowerShell)：**
```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/install.ps1))) -Platform <platform>
```

示例：
```bash
# Claude Code (macOS/Linux)
curl -fsSL https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/install.sh | bash -s -- --platform claude-code

# Opencode（在项目根目录执行）
curl -fsSL https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/install.sh | bash -s -- --platform opencode
```

```powershell
# Claude Code (Windows)
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/install.ps1))) -Platform claude-code
```

<details>
<summary>如果无法执行 curl | bash（备选方案）</summary>

根据你的平台，手动执行对应命令：
**Costrict CLI:**（Skill 全局 + Commands 项目级）

```bash
mkdir -p ~/.costrict/skills/coding-hub
curl -fsSL "https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/platforms/costrict/skills/coding-hub/SKILL.md" -o ~/.costrict/skills/coding-hub/SKILL.md
mkdir -p .costrict/coding-hub/commands
for cmd in search browse recommend install uninstall update; do
  curl -fsSL "https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/platforms/costrict/commands/coding-hub/coding-hub-${cmd}.md" -o .costrict/coding-hub/commands/coding-hub-${cmd}.md
done
```

**VSCode Costrict 插件:**（Skill 全局 + Commands 全局）

```bash
mkdir -p ~/.costrict/skills/coding-hub
curl -fsSL "https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/platforms/vscode-costrict/skills/coding-hub/SKILL.md" -o ~/.costrict/skills/coding-hub/SKILL.md
mkdir -p ~/.roo/commands
for cmd in search browse recommend install uninstall update; do
  curl -fsSL "https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/platforms/vscode-costrict/commands/coding-hub/coding-hub-${cmd}.md" -o ~/.roo/commands/coding-hub-${cmd}.md
done
```

> Roo Code 支持原生 slash commands，命令文件安装到全局 `~/.roo/commands/`。


**Claude Code:**（Skill + Commands 全部安装到全局目录）

```bash
mkdir -p ~/.claude/skills/coding-hub
curl -fsSL "https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/platforms/claude-code/skills/coding-hub/SKILL.md" -o ~/.claude/skills/coding-hub/SKILL.md
for cmd in search browse recommend install uninstall update; do
  curl -fsSL "https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/platforms/claude-code/commands/coding-hub/${cmd}.md" -o ~/.claude/skills/coding-hub/${cmd}.md
done
```

**Opencode:**（Skill 全局 + Commands 项目级）

```bash
mkdir -p ~/.opencode/skills/coding-hub
curl -fsSL "https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/platforms/opencode/skills/coding-hub/SKILL.md" -o ~/.opencode/skills/coding-hub/SKILL.md
mkdir -p .opencode/command
for cmd in search browse recommend install uninstall update; do
  curl -fsSL "https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/platforms/opencode/command/coding-hub-${cmd}.md" -o .opencode/command/coding-hub-${cmd}.md
done
```
</details>

### 第 2 步: 验证安装

执行搜索命令验证安装是否成功：

```
# Costrict CLI / Opencode
/coding-hub-search typescript

# VSCode Costrict 插件
在插件聊天中发送: "用 coding-hub 搜索 typescript"

# Claude Code
/coding-hub:search typescript
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

搜索/浏览/推荐使用轻量搜索索引（~2MB），安装使用单条 API（~1KB），均通过 GitHub Pages CDN 分发：

| 用途 | URL |
|------|-----|
| 搜索索引 | `https://zgsm-sangfor.github.io/costrict-coding-hub/api/v1/search-index.json` |
| 单条 API | `https://zgsm-sangfor.github.io/costrict-coding-hub/api/v1/{type}/{id}.json` |
| 类型索引 | `https://zgsm-sangfor.github.io/costrict-coding-hub/api/v1/{type}/index.json` |
| 全量索引（fallback） | `https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/catalog/index.json` |

索引是 JSON 数组，每个条目包含 `id`, `name`, `type`(mcp/skill/rule/prompt), `description`, `source_url`, `stars`, `category`, `tags`, `tech_stack`, `install`。

---

## 🚀 为什么选择 Costrict？

如果你喜欢 Coding Hub 的理念，不妨试试我们的旗舰产品 **[Costrict](https://github.com/zgsm-ai/costrict)** —— 一个更强大的 AI Coding Agent 平台：

[立即体验 Costrict →](https://github.com/zgsm-ai/costrict)

---

## Contributing

欢迎通过 PR 向 `catalog/` 下对应类型目录添加精选资源。提交前请确保：

- 资源与 coding 相关
- 提供准确的 `source_url`、`description`、`tags`
- 遵循 `catalog/schema.json` 定义的数据格式

---

## Disclaimer

Coding Hub 是一个资源索引聚合项目，所有收录的 MCP Server、Skill、Rule、Prompt 均来自第三方开源仓库，版权归各自作者所有。本项目仅提供索引和安装便利，**不对第三方资源的安全性、可用性、准确性或合规性做任何保证**。

使用本项目收录的任何资源所产生的风险由用户自行承担。建议在使用前审查资源的源代码和许可证。如发现安全问题或侵权内容，请通过 Issue 反馈，我们会及时处理。

本项目以 [MIT License](LICENSE) 发布。
