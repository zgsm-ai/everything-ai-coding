# Coding Hub

<div align="center">
<img src="assets/title-card.jpg" alt="Coding Hub" />

<p><strong><!-- README_APPROX_COUNT:START -->4000<!-- README_APPROX_COUNT:END -->+ 精选开发资源一站式索引</strong><br/>MCP Servers · Skills · Rules · Prompts</p>

<p>
  <a href="https://github.com/zgsm-sangfor/costrict-coding-hub/stargazers"><img src="https://img.shields.io/github/stars/zgsm-sangfor/costrict-coding-hub?style=flat-square&color=4A90D9" alt="Stars" /></a>
  <a href="https://github.com/zgsm-sangfor/costrict-coding-hub/blob/main/LICENSE"><img src="https://img.shields.io/github/license/zgsm-sangfor/costrict-coding-hub?style=flat-square" alt="License" /></a>
  <a href="https://github.com/zgsm-sangfor/costrict-coding-hub/commits/main"><img src="https://img.shields.io/github/last-commit/zgsm-sangfor/costrict-coding-hub?style=flat-square" alt="Last Commit" /></a>
  <img src="https://img.shields.io/badge/resources-4025-2ECC71?style=flat-square" alt="Resources" />
</p>

<p>
  <a href="./README.md">English</a> ·
  <a href="./README.zh-CN.md"><strong>简体中文</strong></a>
</p>

<p>
  <a href="#quick-start">快速开始</a> ·
  <a href="#featured-picks">精选推荐</a> ·
  <a href="#catalog-overview">目录概览</a> ·
  <a href="#platforms">平台支持</a> ·
  <a href="#for-agents">给 Agent 的安装说明</a> ·
  <a href="#contributing">参与贡献</a>
</p>

</div>

## 为什么选择 Coding Hub？

AI Coding Agent 越来越强，但周边生态仍然很分散。想找到可靠的 MCP Server、可复用 Skill、实用 Rule 或 Prompt，通常要在多个仓库和格式之间反复跳转。

Coding Hub 把这件事做成了一个持续更新的统一目录：自动同步上游资源、去重、富化元数据、补充质量信号，再把结果整理成可以被人和 Agent 直接搜索与安装的入口，让你 **一条命令就能发现并接入资源**。

<a id="quick-start"></a>
## 快速开始

按平台执行安装命令即可：

**macOS / Linux**

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

**Windows (PowerShell)**

```powershell
# Costrict CLI
irm https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/install.ps1 | iex

# 自动检测失败时手动指定平台
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/install.ps1))) -Platform costrict
```

安装后可以先试一个搜索命令：

```bash
# Claude Code
/coding-hub:search typescript

# Opencode / Costrict CLI / VSCode Costrict (Roo Code)
/coding-hub-search typescript
```

<video src="https://github.com/user-attachments/assets/552d5405-48c9-4d26-9fb0-34a2715efa24" controls width="100%"></video>

也可以把下面的提示词直接交给另一个 AI Agent：

```text
你是一个自动安装助手。请访问下面的 URL，阅读其中的 "For Agents" 小节，
然后严格按说明完成 Coding Hub 安装。

不要 clone 仓库，只读取这个 raw 文件：
https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/README.md

安装结束后，请说明你使用了哪个平台路径，以及验证是否成功。
```

<a id="featured-picks"></a>
<!-- README_FEATURED_SECTION:START -->
## ⭐ 精选推荐

> 从 4025+ 资源中按使用场景精选。安装后可使用 `/coding-hub:search` 搜索完整索引，或通过 `/coding-hub:recommend` 获取项目级推荐。

### 🌐 浏览器与自动化

- 🔌 **[microsoft/playwright-mcp](https://github.com/microsoft/playwright-mcp)** — 微软官方出品，用Playwright让AI控制网页。 ⭐ 30.5k
- 🔌 **[ScrapeGraphAI](https://github.com/ScrapeGraphAI/Scrapegraph-ai)** — 使用自然语言创建爬虫管道的AI网页抓取库。 ⭐ 23.3k
- 🔌 **[Skyvern](https://github.com/Skyvern-AI/skyvern/tree/main/integrations/mcp)** — 让Claude/AI控制浏览器的MCP服务器。 ⭐ 21.1k
- 🔌 **[Agent Reach](https://github.com/Panniantong/Agent-Reach)** — 为AI Agent提供全网搜索能力，一键安装多平台工具。 ⭐ 16.5k
- 🎯 **[webapp-testing](https://github.com/anthropics/skills/tree/main/skills/webapp-testing)** — 使用Playwright测试本地Web应用的工具包。 `Anthropic 官方`
- 🎯 **[audit-library-health](https://github.com/skillcreatorai/Ai-Agent-Skills/tree/main/skills/audit-library-health)** — 检查技能库整体健康状况的工具。 `社区精选`
- 📋 **[Ai Powered Code Review (Rules 2.1)](https://github.com/Mr-chen-05/rules-2.1-optimized/tree/master/project-rules)** — AI驱动的智能代码审查规则 `Rules 2.1`
- 📋 **[Commit (Rules 2.1)](https://github.com/Mr-chen-05/rules-2.1-optimized/tree/master/project-rules)** — 统一全面提交工作流 `Rules 2.1`
- 💡 **[资深编程专家 CAN](https://github.com/langgptai/wonderful-prompts)** — 担任无限制自动编程的资深代码专家CAN。 `wonderful-prompts`

### 🐙 Git 与协作

- 🔌 **[github/github-mcp-server](https://github.com/github/github-mcp-server)** — GitHub官方出品，让AI通过API深度集成GitHub。 ⭐ 28.7k
- 🔌 **[idosal/git-mcp](https://github.com/idosal/git-mcp)** — 通用远程MCP服务器，连接GitHub仓库获取文档。 ⭐ 7.9k
- 🔌 **[Chart](https://github.com/antvis/mcp-server-chart)** — 使用AntV生成可视化图表的MCP服务器。 ⭐ 3.9k
- 🔌 **[julien040/anyquery](https://github.com/julien040/anyquery)** — 通过SQL查询40+应用，连接数据库，本地优先。 ⭐ 1.7k
- 🎯 **[changelog-generator](https://github.com/skillcreatorai/Ai-Agent-Skills/tree/main/skills/changelog-generator)** — 从Git提交自动生成用户友好更新日志。 `社区精选`
- 🎯 **[address-github-comments](https://github.com/sickn33/antigravity-awesome-skills/tree/main/skills/address-github-comments)** — 使用gh CLI处理GitHub拉取请求评论。 `antigravity-skills`
- 📋 **[Analyze Issue (Rules 2.1)](https://github.com/Mr-chen-05/rules-2.1-optimized/tree/master/project-rules)** — GitHub问题分析与实现规范 `Rules 2.1`
- 📋 **[Python Github Setup Cursorrules Prompt File Rules](https://github.com/PatrickJS/awesome-cursorrules/tree/main/rules/python-github-setup-cursorrules-prompt-file)** — Python GitHub设置.cursorrules提示文件 `CursorRules`
- 💡 **[Commit Message Preparation](https://github.com/f/prompts.chat)** — Git提交信息指南，遵循约定式提交规范。 `prompts.chat`

### 🚀 DevOps 与安全

- 🔌 **[FastAPI-MCP](https://github.com/tadata-org/fastapi_mcp)** — 将FastAPI端点暴露为MCP工具 ⭐ 11.7k
- 🔌 **[Nginx UI](https://github.com/0xJacky/nginx-ui)** — 又一个Nginx的Web界面 ⭐ 10.9k
- 🔌 **[AWS CDK](https://github.com/awslabs/mcp/tree/main/src/cdk-mcp-server)** — 提供CDK建议、规则解释与模式发现的MCP服务器。 ⭐ 8.7k
- 🔌 **[ghidraMCP](https://github.com/LaurieWired/GhidraMCP)** — Ghidra的MCP服务器 ⭐ 8.1k
- 🎯 **[doc-coauthoring](https://github.com/anthropics/skills/tree/main/skills/doc-coauthoring)** — 引导用户完成结构化文档协作工作流。 `Anthropic 官方`
- 🎯 **[ask-questions-if-underspecified](https://github.com/skillcreatorai/Ai-Agent-Skills/tree/main/skills/ask-questions-if-underspecified)** — 实施前明确需求，仅在调用时使用。 `社区精选`
- 📋 **[Security Audit Rules](https://github.com/Mr-chen-05/rules-2.1-optimized/tree/master/project-rules)** — 安全审计规则：覆盖OWASP与输入验证审查 `精选`
- 📋 **[Permission Control System (Rules 2.1)](https://github.com/Mr-chen-05/rules-2.1-optimized/tree/master/global-rules)** — 权限控制系统：定义角色权限与操作审计 `Rules 2.1`
- 💡 **[模拟 Linux 终端](https://github.com/langgptai/wonderful-prompts)** — 模拟Linux终端，仅以代码块形式返回命令输出。 `wonderful-prompts`

### 📚 文档与知识

- 🔌 **[microsoft/markitdown](https://github.com/microsoft/markitdown/tree/main/packages/markitdown-mcp)** — MarkItDown MCP工具，将多种文件格式转换为Markdown。 ⭐ 94.4k
- 🔌 **[Context 7](https://github.com/upstash/context7-mcp)** — Context7 MCP - 为任何Cursor提示提供最新文档。 ⭐ 52.1k
- 🔌 **[Mastra/mcp-docs-server](https://github.com/mastra-ai/mastra/tree/main/packages/mcp-docs-server)** — 为AI助手提供Mastra.ai完整知识库的直接访问。 ⭐ 22.8k
- 🔌 **[cognee-mcp](https://github.com/topoteretes/cognee/tree/main/cognee-mcp)** — GraphRAG记忆服务器，支持自定义摄取与搜索。 ⭐ 15.0k
- 🎯 **[slack-gif-creator](https://github.com/anthropics/skills/tree/main/skills/slack-gif-creator)** — 为Slack制作优化动画GIF的工具集。 `Anthropic 官方`
- 🎯 **[theme-factory](https://github.com/anthropics/skills/tree/main/skills/theme-factory)** — 为各类文档应用预设或自定义主题的样式工具。 `Anthropic 官方`
- 📋 **[Technical Documentation Rules](https://github.com/Mr-chen-05/rules-2.1-optimized/tree/master/project-rules)** — 技术文档规则：生成与维护技术文档AI规则 `精选`
- 📋 **[Mermaid (Rules 2.1)](https://github.com/Mr-chen-05/rules-2.1-optimized/tree/master/project-rules)** — Mermaid图表生成工具 `Rules 2.1`
- 💡 **["Explain It Like I Built It"  Technical Documentation for Non-Technical Founders](https://github.com/f/prompts.chat)** — 资深技术作家，为非技术创始人简化复杂系统文档。 `prompts.chat`

### 🎨 前端与设计

- 🔌 **[mediar-ai/screenpipe](https://github.com/mediar-ai/screenpipe)** — 本地优先的屏幕音频捕获与AI分析系统。 ⭐ 18.1k
- 🔌 **[Framelink Figma MCP Server](https://github.com/GLips/Figma-Context-MCP)** — Figma布局信息MCP服务器，供AI编码代理使用 ⭐ 14.0k
- 🔌 **[Inbox Zero](https://github.com/elie222/inbox-zero/tree/main/apps/mcp-server)** — Inbox Zero官方集成，AI个人邮件助手。 ⭐ 10.4k
- 🔌 **[Lingo.dev](https://github.com/lingodotdev/lingo.dev/blob/main/mcp.md)** — 让AI代理使用Lingo.dev本地化引擎支持全球语言。 ⭐ 5.4k
- 🎯 **[brand-guidelines](https://github.com/anthropics/skills/tree/main/skills/brand-guidelines)** — 将Anthropic官方品牌色彩和排版应用于各类设计制品。 `Anthropic 官方`
- 🎯 **[canvas-design](https://github.com/anthropics/skills/tree/main/skills/canvas-design)** — 使用设计哲学创建.png和.pdf视觉艺术，适用于海报和设计。 `Anthropic 官方`
- 📋 **[Frontend Rules (Rules 2.1)](https://github.com/Mr-chen-05/rules-2.1-optimized/tree/master/global-rules)** — 前端开发AI助手规则：企业级标准与智能工具编排 `Rules 2.1`
- 📋 **[Frontend Dev (Rules 2.1)](https://github.com/Mr-chen-05/rules-2.1-optimized/tree/master/project-rules)** — 前端开发完整工作流 `Rules 2.1`
- 💡 **[Fullstack Software Developer](https://github.com/f/prompts.chat)** — 担任精通前后端技术的全栈软件开发专家。 `精选`

### ⚙️ 后端与数据库

- 🔌 **[pydantic/pydantic-ai/mcp-run-python](https://github.com/pydantic/pydantic-ai/tree/main/mcp-run-python)** — Pydantic出品，在沙盒中运行Python代码。 ⭐ 16.2k
- 🔌 **[googleapis/genai-toolbox](https://github.com/googleapis/genai-toolbox)** — Google官方开源MCP服务器，为数据库提供工具。 ⭐ 14.0k
- 🔌 **[InstantDB](https://github.com/instantdb/instant/tree/main/client/packages/mcp)** — 在现代化Firebase替代品InstantDB上创建、管理和更新应用。 ⭐ 9.8k
- 🔌 **[Supabase MCP Servers](https://github.com/supabase-community/mcp-supabase)** — Supabase MCP服务器集合 ⭐ 2.6k
- 🎯 **[PocketBase Hooks](https://github.com/davila7/claude-code-templates/tree/main/cli-tool/components/skills/pocketbase/pb-hooks)** — PocketBase服务器端JavaScript钩子，扩展逻辑。 `davila7/claude-code-templates`
- 🎯 **[alphafold-database](https://github.com/davila7/claude-code-templates/tree/main/cli-tool/components/skills/scientific/alphafold-database)** — 访问AlphaFold的2亿+ AI预测蛋白质结构，用于药物发现和结构生物学。 `davila7/claude-code-templates`
- 📋 **[Supabase Rules](https://github.com/PatrickJS/awesome-cursorrules/tree/main/rules/supabase)** — Supabase规则：PostgreSQL与边缘函数开发 `精选`
- 📋 **[Backend Dev (Rules 2.1)](https://github.com/Mr-chen-05/rules-2.1-optimized/tree/master/project-rules)** — 后端开发完整工作流 `Rules 2.1`
- 💡 **[编写函数(Python 为例)](https://github.com/langgptai/wonderful-prompts)** — 指导使用ChatGPT编写Python函数（如计算三角形面积）。 `wonderful-prompts`

### 🤖 AI 与 MCP 开发

- 🔌 **[modelcontextprotocol/server-filesystem](https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem)** — 官方参考实现，提供对本地文件系统的直接访问。 ⭐ 83.3k
- 🔌 **[Homebrew](https://github.com/Homebrew/brew/blob/HEAD/Library/Homebrew/mcp_server.rb)** — Homebrew包管理器的MCP服务器 ⭐ 47.2k
- 🔌 **[claude-cookbooks](https://github.com/anthropics/anthropic-cookbook)** — 展示Claude有趣有效使用方式的笔记本/配方集合。 ⭐ 36.6k
- 🔌 **[FastMCP v2 🚀](https://github.com/jlowin/fastmcp)** — 快速构建MCP服务器和客户端的Python工具。 ⭐ 24.0k
- 🎯 **[algorithmic-art](https://github.com/anthropics/skills/tree/main/skills/algorithmic-art)** — 使用p5.js创建算法艺术，支持种子随机和交互参数探索。 `Anthropic 官方`
- 🎯 **[claude-api](https://github.com/anthropics/skills/tree/main/skills/claude-api)** — 使用Claude API或Anthropic SDK构建应用程序。 `Anthropic 官方`
- 📋 **[Super Brain System (Rules 2.1)](https://github.com/Mr-chen-05/rules-2.1-optimized/tree/master/global-rules)** — 超级大脑系统：智能项目管理激活与核心功能 `Rules 2.1`
- 📋 **[Ai Ethical Boundaries (Rules 2.1)](https://github.com/Mr-chen-05/rules-2.1-optimized/tree/master/global-rules)** — AI伦理边界规则 `Rules 2.1`
- 💡 **[混淆代码翻译](https://github.com/langgptai/wonderful-prompts)** — 分析代码功能并翻译重命名为更清晰易懂的版本。 `wonderful-prompts`

> 图例：🔌 MCP Server · 🎯 Skill · 📋 Rule · 💡 Prompt
<!-- README_FEATURED_SECTION:END -->

<a id="catalog-overview"></a>
## 目录概览

| 类型 | 数量 | 说明 |
|------|------:|------|
| MCP Server | <!-- README_COUNT_MCP:START -->1628<!-- README_COUNT_MCP:END --> | Model Context Protocol 服务器 |
| Prompt | <!-- README_COUNT_PROMPT:START -->528<!-- README_COUNT_PROMPT:END --> | 面向开发者的 Prompt |
| Rule | <!-- README_COUNT_RULE:START -->236<!-- README_COUNT_RULE:END --> | 编码规范与 AI 工作流规则 |
| Skill | <!-- README_COUNT_SKILL:START -->1633<!-- README_COUNT_SKILL:END --> | 可复用的 Agent Skill |

### 数据来源

Coding Hub 从多类上游源聚合资源，并通过 GitHub Pages 与 raw GitHub 提供可直接消费的数据接口。

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
costrict-coding-hub/
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
└── openspec/                     # 变更管理产物
```

</details>

<a id="platforms"></a>
## 平台支持

Coding Hub 当前支持四个 AI Coding 平台，共用同一份资源目录，但命令格式与安装路径略有差异。

| | Claude Code | Costrict | Opencode | VSCode Costrict (Roo Code) |
|---|---|---|---|---|
| 搜索 | `/coding-hub:search <kw> [type:mcp]` | `/coding-hub-search <kw> [type:mcp]` | `/coding-hub-search <kw> [type:mcp]` | `/coding-hub-search <kw> [type:mcp]` |
| 浏览 | `/coding-hub:browse [category]` | `/coding-hub-browse [category]` | `/coding-hub-browse [category]` | `/coding-hub-browse [category]` |
| 推荐 | `/coding-hub:recommend` | `/coding-hub-recommend` | `/coding-hub-recommend` | `/coding-hub-recommend` |
| 安装 | `/coding-hub:install <name>` | `/coding-hub-install <name>` | `/coding-hub-install <name>` | `/coding-hub-install <name>` |
| 卸载 | `/coding-hub:uninstall <name>` | `/coding-hub-uninstall <name>` | `/coding-hub-uninstall <name>` | `/coding-hub-uninstall <name>` |
| 更新 | `/coding-hub:update` | `/coding-hub-update` | `/coding-hub-update` | `/coding-hub-update` |

<details>
<summary>平台路径差异</summary>

| | Claude Code | Costrict | VSCode Costrict | Opencode |
|---|---|---|---|---|
| 全局 Skill 路径 | `~/.claude/skills/coding-hub/` | `~/.costrict/skills/coding-hub/` | `~/.costrict/skills/coding-hub/` | `~/.opencode/skills/coding-hub/` |
| 命令路径 | 同一全局目录 | `.costrict/coding-hub/commands/`（项目级） | `~/.roo/commands/`（全局） | `.opencode/command/`（项目级） |
| 分隔符 | `:` | `-` | `-` | `-` |

- **Costrict CLI** 需要在每个项目根目录安装命令文件。
- **VSCode Costrict / Roo Code** 将命令文件安装到全局 `~/.roo/commands/`。
- **Claude Code** 可以从全局技能目录直接加载完整 skill 与子命令。
- **Opencode** 需要在每个项目下安装 `.opencode/command/` 中的命令文件。

</details>

<a id="for-agents"></a>
## 给 Agent 的安装说明

> 如果你是自动安装 Coding Hub 的 AI Agent，请严格按本节操作。

### 第 1 步：运行安装脚本

安装脚本会尽量自动识别你当前所在的平台。

**macOS / Linux**

```bash
curl -fsSL https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/install.sh | bash
```

**Windows (PowerShell)**

```powershell
irm https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/install.ps1 | iex
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
curl -fsSL https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/install.sh | bash -s -- --platform <platform>
```

**Windows (PowerShell)**

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
<summary>备选方案：手动下载文件，不使用 <code>curl | bash</code></summary>

当你不能直接执行安装脚本时，可以按平台分别下载 skill 和命令文件。

**Costrict CLI**（Skill 全局 + Commands 项目级）

```bash
mkdir -p ~/.costrict/skills/coding-hub
curl -fsSL "https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/platforms/costrict/skills/coding-hub/SKILL.md" -o ~/.costrict/skills/coding-hub/SKILL.md
mkdir -p .costrict/coding-hub/commands
for cmd in search browse recommend install uninstall update; do
  curl -fsSL "https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/platforms/costrict/commands/coding-hub/coding-hub-${cmd}.md" -o .costrict/coding-hub/commands/coding-hub-${cmd}.md
done
```

**VSCode Costrict 插件 / Roo Code**（Skill 全局 + Commands 全局）

```bash
mkdir -p ~/.costrict/skills/coding-hub
curl -fsSL "https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/platforms/vscode-costrict/skills/coding-hub/SKILL.md" -o ~/.costrict/skills/coding-hub/SKILL.md
mkdir -p ~/.roo/commands
for cmd in search browse recommend install uninstall update; do
  curl -fsSL "https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/platforms/vscode-costrict/commands/coding-hub/coding-hub-${cmd}.md" -o ~/.roo/commands/coding-hub-${cmd}.md
done
```

**Claude Code**（Skill + Commands 全局安装）

```bash
mkdir -p ~/.claude/skills/coding-hub
curl -fsSL "https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/platforms/claude-code/skills/coding-hub/SKILL.md" -o ~/.claude/skills/coding-hub/SKILL.md
for cmd in search browse recommend install uninstall update; do
  curl -fsSL "https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/platforms/claude-code/commands/coding-hub/${cmd}.md" -o ~/.claude/skills/coding-hub/${cmd}.md
done
```

**Opencode**（Skill 全局 + Commands 项目级）

```bash
mkdir -p ~/.opencode/skills/coding-hub
curl -fsSL "https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/platforms/opencode/skills/coding-hub/SKILL.md" -o ~/.opencode/skills/coding-hub/SKILL.md
mkdir -p .opencode/command
for cmd in search browse recommend install uninstall update; do
  curl -fsSL "https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/platforms/opencode/command/coding-hub-${cmd}.md" -o .opencode/command/coding-hub-${cmd}.md
done
```

</details>

### 第 2 步：验证安装是否成功

运行搜索命令确认命令是否可用：

```text
# Costrict CLI / Opencode
/coding-hub-search typescript

# VSCode Costrict 插件
在聊天窗口发送："用 coding-hub 搜索 typescript"

# Claude Code
/coding-hub:search typescript
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
| 搜索索引 | `https://zgsm-sangfor.github.io/costrict-coding-hub/api/v1/search-index.json` |
| 单条 API | `https://zgsm-sangfor.github.io/costrict-coding-hub/api/v1/{type}/{id}.json` |
| 类型索引 | `https://zgsm-sangfor.github.io/costrict-coding-hub/api/v1/{type}/index.json` |
| 全量索引回退地址 | `https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/catalog/index.json` |

## 为什么推荐 Costrict？

如果你喜欢 Coding Hub 的工作流，也可以试试 **[Costrict](https://github.com/zgsm-ai/costrict)** —— 我们更完整的 AI Coding Agent 平台，适合更强的自动化与团队协作场景。

[立即了解 Costrict →](https://github.com/zgsm-ai/costrict)

<a id="contributing"></a>
## 参与贡献

欢迎提交 PR，为 `catalog/` 下相应目录补充优质资源。提交前请确保：

- 资源与编程或 AI 辅助开发相关，
- `source_url`、`description`、tags 等字段准确，
- 数据格式符合 `catalog/schema.json`。

## 免责声明

Coding Hub 是一个第三方开源资源的索引与安装辅助项目。目录中的 MCP Server、Skill、Rule、Prompt 的版权与责任均归原作者所有。

本仓库 **不对** 第三方资源的安全性、可用性、准确性或合规性作任何保证。请在使用前自行审查源码与许可证；如果发现安全或版权问题，欢迎通过 Issue 反馈。

本项目遵循 [MIT License](LICENSE) 发布。
