# Coding Hub

<div align="center">
<img src="assets/title-card.jpg" alt="Coding Hub" />

<p><strong><!-- README_APPROX_COUNT:START -->4000<!-- README_APPROX_COUNT:END -->+ curated developer resources in one index</strong><br/>MCP Servers · Skills · Rules · Prompts</p>

<p>
  <a href="https://github.com/zgsm-sangfor/costrict-coding-hub/stargazers"><img src="https://img.shields.io/github/stars/zgsm-sangfor/costrict-coding-hub?style=flat-square&color=4A90D9" alt="Stars" /></a>
  <a href="https://github.com/zgsm-sangfor/costrict-coding-hub/blob/main/LICENSE"><img src="https://img.shields.io/github/license/zgsm-sangfor/costrict-coding-hub?style=flat-square" alt="License" /></a>
  <a href="https://github.com/zgsm-sangfor/costrict-coding-hub/commits/main"><img src="https://img.shields.io/github/last-commit/zgsm-sangfor/costrict-coding-hub?style=flat-square" alt="Last Commit" /></a>
  <img src="https://img.shields.io/badge/resources-4025-2ECC71?style=flat-square" alt="Resources" />
</p>

<p>
  <a href="./README.md"><strong>English</strong></a> ·
  <a href="./README.zh-CN.md">简体中文</a>
</p>

<p>
  <a href="#quick-start">Quick Start</a> ·
  <a href="#featured-picks">Featured Picks</a> ·
  <a href="#catalog-overview">Catalog Overview</a> ·
  <a href="#platforms">Platforms</a> ·
  <a href="#for-agents">For Agents</a> ·
  <a href="#contributing">Contributing</a>
</p>

</div>

## Why Coding Hub?

AI coding agents are improving fast, but the ecosystem around them is still fragmented. Finding a reliable MCP server, reusable skill, practical rule set, or prompt collection usually means searching across multiple repositories and formats.

Coding Hub turns that scattered discovery process into a single searchable catalog. It continuously syncs from curated upstream sources, deduplicates entries, enriches metadata, scores quality signals, and packages the results so humans and agents can **search and install resources with one command**.

<a id="quick-start"></a>
## Quick Start

Install Coding Hub for your platform with one command:

**macOS / Linux**

```bash
# Costrict CLI (run from your project root)
curl -fsSL https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/install.sh | bash -s -- --platform costrict

# VSCode Costrict extension
curl -fsSL https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/install.sh | bash -s -- --platform vscode-costrict

# Claude Code
curl -fsSL https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/install.sh | bash -s -- --platform claude-code

# Opencode (run from your project root)
curl -fsSL https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/install.sh | bash -s -- --platform opencode
```

**Windows (PowerShell)**

```powershell
# Costrict CLI
irm https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/install.ps1 | iex

# Specify the platform manually if auto-detection fails
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/install.ps1))) -Platform costrict
```

After installation, try a search command:

```bash
# Claude Code
/coding-hub:search typescript

# Opencode / Costrict CLI / VSCode Costrict (Roo Code)
/coding-hub-search typescript
```

<video src="https://github.com/user-attachments/assets/e58f0b08-73c0-4fba-ac95-138c8087a917" controls width="100%"></video>

You can also hand the installation off to another agent with this prompt:

```text
You are an installation assistant. Open the following URL, read the "For Agents" section,
and follow it exactly to install Coding Hub for the platform you are currently running on.

Do not clone the repository. Only read this raw file:
https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/README.md

After installation, report which platform path was used and whether verification succeeded.
```

<a id="featured-picks"></a>
<!-- README_FEATURED_SECTION:START -->
## ⭐ Featured Picks

> Curated by use case from 4025+ resources. After installation, use `/coding-hub:search` to explore the full index or `/coding-hub:recommend` for project-aware suggestions.

### 🌐 Browser & Automation

- 🔌 **[microsoft/playwright-mcp](https://github.com/microsoft/playwright-mcp)** — Using Playwright for browser automation and data scraping is directly… ⭐ 30.5k
- 🔌 **[ScrapeGraphAI](https://github.com/ScrapeGraphAI/Scrapegraph-ai)** — AI-powered web scraping library that creates scraping pipelines using… ⭐ 23.3k
- 🔌 **[Skyvern](https://github.com/Skyvern-AI/skyvern/tree/main/integrations/mcp)** — MCP Server to let Claude / your AI control the browser ⭐ 21.1k
- 🔌 **[Agent Reach](https://github.com/Panniantong/Agent-Reach)** — Tool for connecting AI agents to multiple platforms (social media,… ⭐ 16.5k
- 🎯 **[webapp-testing](https://github.com/anthropics/skills/tree/main/skills/webapp-testing)** — Toolkit for interacting with and testing local web applications using… `Anthropic official`
- 🎯 **[audit-library-health](https://github.com/skillcreatorai/Ai-Agent-Skills/tree/main/skills/audit-library-health)** — Use when checking the overall health of a skills library. Run doctor,… `Community curated`
- 📋 **[Ai Powered Code Review (Rules 2.1)](https://github.com/Mr-chen-05/rules-2.1-optimized/tree/master/project-rules)** — Core dev tool for code quality with a clear description of AI-driven… `Rules 2.1`
- 📋 **[Commit (Rules 2.1)](https://github.com/Mr-chen-05/rules-2.1-optimized/tree/master/project-rules)** — Core dev tool for Git with a clear description of unified commit… `Rules 2.1`
- 💡 **[资深编程专家 CAN](https://github.com/langgptai/wonderful-prompts)** — Positions as a senior programming expert ('code anything now'),… `wonderful-prompts`

### 🐙 Git & Collaboration

- 🔌 **[github/github-mcp-server](https://github.com/github/github-mcp-server)** — Core dev tool for deep GitHub API integration to automate workflows,… ⭐ 28.7k
- 🔌 **[idosal/git-mcp](https://github.com/idosal/git-mcp)** — Directly aids coding by connecting to GitHub repositories for… ⭐ 7.9k
- 🔌 **[Chart](https://github.com/antvis/mcp-server-chart)** — 🤖 A Model Context Protocol server for generating visual charts using… ⭐ 3.9k
- 🔌 **[julien040/anyquery](https://github.com/julien040/anyquery)** — Querying 40+ applications and databases via SQL is a core data access… ⭐ 1.7k
- 🎯 **[changelog-generator](https://github.com/skillcreatorai/Ai-Agent-Skills/tree/main/skills/changelog-generator)** — Automatically creates user-facing changelogs from git commits by… `Community curated`
- 🎯 **[address-github-comments](https://github.com/sickn33/antigravity-awesome-skills/tree/main/skills/address-github-comments)** — Use when you need to address review or issue comments on an open… `antigravity-skills`
- 📋 **[Analyze Issue (Rules 2.1)](https://github.com/Mr-chen-05/rules-2.1-optimized/tree/master/project-rules)** — Core dev tool for issue tracking with a clear description of analysis… `Rules 2.1`
- 📋 **[Python Github Setup Cursorrules Prompt File Rules](https://github.com/PatrickJS/awesome-cursorrules/tree/main/rules/python-github-setup-cursorrules-prompt-file)** — Python GitHub Setup .cursorrules prompt file `CursorRules`
- 💡 **[Commit Message Preparation](https://github.com/f/prompts.chat)** — # Git Commit Guidelines for AI Language Models  ## Core Principles … `prompts.chat`

### 🚀 DevOps & Security

- 🔌 **[FastAPI-MCP](https://github.com/tadata-org/fastapi_mcp)** — Expose your FastAPI endpoints as Model Context Protocol (MCP) tools,… ⭐ 11.7k
- 🔌 **[Nginx UI](https://github.com/0xJacky/nginx-ui)** — Yet another WebUI for Nginx ⭐ 10.9k
- 🔌 **[AWS CDK](https://github.com/awslabs/mcp/tree/main/src/cdk-mcp-server)** — Get prescriptive CDK advice, explain CDK Nag rules, check… ⭐ 8.7k
- 🔌 **[ghidraMCP](https://github.com/LaurieWired/GhidraMCP)** — MCP Server for Ghidra ⭐ 8.1k
- 🎯 **[doc-coauthoring](https://github.com/anthropics/skills/tree/main/skills/doc-coauthoring)** — Guide users through a structured workflow for co-authoring… `Anthropic official`
- 🎯 **[ask-questions-if-underspecified](https://github.com/skillcreatorai/Ai-Agent-Skills/tree/main/skills/ask-questions-if-underspecified)** — Clarify requirements before implementing. Do not use automatically,… `Community curated`
- 📋 **[Security Audit Rules](https://github.com/Mr-chen-05/rules-2.1-optimized/tree/master/project-rules)** — AI-assisted security review rules covering OWASP, input validation,… `Curated`
- 📋 **[Permission Control System (Rules 2.1)](https://github.com/Mr-chen-05/rules-2.1-optimized/tree/master/global-rules)** — Permission control and audit systems are fundamental to application… `Rules 2.1`
- 💡 **[模拟 Linux 终端](https://github.com/langgptai/wonderful-prompts)** — The prompt directly aids coding by simulating a Linux terminal for… `wonderful-prompts`

### 📚 Documentation & Knowledge

- 🔌 **[microsoft/markitdown](https://github.com/microsoft/markitdown/tree/main/packages/markitdown-mcp)** — File format conversion to Markdown directly aids code documentation… ⭐ 94.4k
- 🔌 **[Context 7](https://github.com/upstash/context7-mcp)** — Context7 MCP - Up-to-date Docs For Any Cursor Prompt ⭐ 52.1k
- 🔌 **[Mastra/mcp-docs-server](https://github.com/mastra-ai/mastra/tree/main/packages/mcp-docs-server)** — Provides AI assistants with direct access to Mastra.ai's complete… ⭐ 22.8k
- 🔌 **[cognee-mcp](https://github.com/topoteretes/cognee/tree/main/cognee-mcp)** — GraphRAG memory server with custom ingestion directly supports AI… ⭐ 15.0k
- 🎯 **[slack-gif-creator](https://github.com/anthropics/skills/tree/main/skills/slack-gif-creator)** — Knowledge and utilities for creating animated GIFs optimized for… `Anthropic official`
- 🎯 **[theme-factory](https://github.com/anthropics/skills/tree/main/skills/theme-factory)** — Toolkit for styling artifacts with a theme. These artifacts can be… `Anthropic official`
- 📋 **[Technical Documentation Rules](https://github.com/Mr-chen-05/rules-2.1-optimized/tree/master/project-rules)** — AI rules for generating and maintaining technical documentation `Curated`
- 📋 **[Mermaid (Rules 2.1)](https://github.com/Mr-chen-05/rules-2.1-optimized/tree/master/project-rules)** — Tangentially related to coding via diagram generation, with a clear… `Rules 2.1`
- 💡 **["Explain It Like I Built It"  Technical Documentation for Non-Technical Founders](https://github.com/f/prompts.chat)** — You are a senior technical writer who specializes in making complex… `prompts.chat`

### 🎨 Frontend & Design

- 🔌 **[mediar-ai/screenpipe](https://github.com/mediar-ai/screenpipe)** — Tangentially related to coding via screen capture and AI agent… ⭐ 18.1k
- 🔌 **[Framelink Figma MCP Server](https://github.com/GLips/Figma-Context-MCP)** — MCP server to provide Figma layout information to AI coding agents… ⭐ 14.0k
- 🔌 **[Inbox Zero](https://github.com/elie222/inbox-zero/tree/main/apps/mcp-server)** — Gmail-based personal email assistant is a general productivity tool… ⭐ 10.4k
- 🔌 **[Lingo.dev](https://github.com/lingodotdev/lingo.dev/blob/main/mcp.md)** — Make your AI agent speak every language on the planet, using… ⭐ 5.4k
- 🎯 **[brand-guidelines](https://github.com/anthropics/skills/tree/main/skills/brand-guidelines)** — Applies Anthropic's official brand colors and typography to any sort… `Anthropic official`
- 🎯 **[canvas-design](https://github.com/anthropics/skills/tree/main/skills/canvas-design)** — Create beautiful visual art in .png and .pdf documents using design… `Anthropic official`
- 📋 **[Frontend Rules (Rules 2.1)](https://github.com/Mr-chen-05/rules-2.1-optimized/tree/master/global-rules)** — Frontend development with modern tech stacks is central to software… `Rules 2.1`
- 📋 **[Frontend Dev (Rules 2.1)](https://github.com/Mr-chen-05/rules-2.1-optimized/tree/master/project-rules)** — Core dev tool for frontend workflows with a clear description of… `Rules 2.1`
- 💡 **[Fullstack Software Developer](https://github.com/f/prompts.chat)** — Act as a fullstack developer with expertise in both frontend and… `Curated`

### ⚙️ Backend & Databases

- 🔌 **[pydantic/pydantic-ai/mcp-run-python](https://github.com/pydantic/pydantic-ai/tree/main/mcp-run-python)** — Running Python code in a secure sandbox is a core tool for developing… ⭐ 16.2k
- 🔌 **[googleapis/genai-toolbox](https://github.com/googleapis/genai-toolbox)** — Core dev tool as an official Google MCP server providing simple,… ⭐ 14.0k
- 🔌 **[InstantDB](https://github.com/instantdb/instant/tree/main/client/packages/mcp)** — Create, manage, and update applications on InstantDB, the modern… ⭐ 9.8k
- 🔌 **[Supabase MCP Servers](https://github.com/supabase-community/mcp-supabase)** — A collection of MCP servers that connect LLMs to Supabase ⭐ 2.6k
- 🎯 **[PocketBase Hooks](https://github.com/davila7/claude-code-templates/tree/main/cli-tool/components/skills/pocketbase/pb-hooks)** — Server-side JavaScript hooks for PocketBase (pb_hooks). Use when… `davila7/claude-code-templates`
- 🎯 **[alphafold-database](https://github.com/davila7/claude-code-templates/tree/main/cli-tool/components/skills/scientific/alphafold-database)** — Access AlphaFold's 200M+ AI-predicted protein structures. Retrieve… `davila7/claude-code-templates`
- 📋 **[Supabase Rules](https://github.com/PatrickJS/awesome-cursorrules/tree/main/rules/supabase)** — Cursor rules for Supabase with PostgreSQL and Edge Functions `Curated`
- 📋 **[Backend Dev (Rules 2.1)](https://github.com/Mr-chen-05/rules-2.1-optimized/tree/master/project-rules)** — Core dev tool for backend workflows with a clear description of… `Rules 2.1`
- 💡 **[编写函数(Python 为例)](https://github.com/langgptai/wonderful-prompts)** — Instructs writing a Python function for triangle area calculation, a… `wonderful-prompts`

### 🤖 AI & MCP Development

- 🔌 **[modelcontextprotocol/server-filesystem](https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem)** — Official filesystem access implementation is a core development tool… ⭐ 83.3k
- 🔌 **[Homebrew](https://github.com/Homebrew/brew/blob/HEAD/Library/Homebrew/mcp_server.rb)** — An MCP server for the Homebrew package manager. ⭐ 47.2k
- 🔌 **[claude-cookbooks](https://github.com/anthropics/anthropic-cookbook)** — A collection of notebooks/recipes showcasing some fun and effective… ⭐ 36.6k
- 🔌 **[FastMCP v2 🚀](https://github.com/jlowin/fastmcp)** — 🚀 The fast, Pythonic way to build MCP servers and clients ⭐ 24.0k
- 🎯 **[algorithmic-art](https://github.com/anthropics/skills/tree/main/skills/algorithmic-art)** — Creating algorithmic art using p5.js with seeded randomness and… `Anthropic official`
- 🎯 **[claude-api](https://github.com/anthropics/skills/tree/main/skills/claude-api)** — Anthropic skill: claude-api `Anthropic official`
- 📋 **[Super Brain System (Rules 2.1)](https://github.com/Mr-chen-05/rules-2.1-optimized/tree/master/global-rules)** — The 'super brain' metaphor for project management is not a recognized… `Rules 2.1`
- 📋 **[Ai Ethical Boundaries (Rules 2.1)](https://github.com/Mr-chen-05/rules-2.1-optimized/tree/master/global-rules)** — Ethical standards are not directly related to software development… `Rules 2.1`
- 💡 **[混淆代码翻译](https://github.com/langgptai/wonderful-prompts)** — The prompt directly aids coding by analyzing, translating, and… `wonderful-prompts`

> Legend: 🔌 MCP Server · 🎯 Skill · 📋 Rule · 💡 Prompt
<!-- README_FEATURED_SECTION:END -->

<a id="catalog-overview"></a>
## Catalog Overview

| Type | Count | Description |
|------|------:|-------------|
| MCP Server | <!-- README_COUNT_MCP:START -->1628<!-- README_COUNT_MCP:END --> | Model Context Protocol servers |
| Prompt | <!-- README_COUNT_PROMPT:START -->528<!-- README_COUNT_PROMPT:END --> | Developer-focused prompts |
| Rule | <!-- README_COUNT_RULE:START -->236<!-- README_COUNT_RULE:END --> | Coding rules and AI workflow conventions |
| Skill | <!-- README_COUNT_SKILL:START -->1633<!-- README_COUNT_SKILL:END --> | Reusable agent skills |

### Data sources

Coding Hub aggregates data from multiple upstream sources, then republishes the cleaned catalog through GitHub Pages and raw GitHub endpoints.

| Type | Sources |
|------|---------|
| MCP | [awesome-mcp-servers](https://github.com/wong2/awesome-mcp-servers) · [Awesome-MCP-ZH](https://github.com/yzfly/Awesome-MCP-ZH) · [mcp.so](https://mcp.so) |
| Skills | Tier 1: [anthropics/skills](https://github.com/anthropics/skills) · [Ai-Agent-Skills](https://github.com/skillcreatorai/Ai-Agent-Skills) · [antigravity-awesome-skills](https://github.com/sickn33/antigravity-awesome-skills) · [ai-agents-public](https://github.com/vasilyu1983/ai-agents-public)<br/>Tier 2: [awesome-repo-configs / skill_repos.json](https://github.com/Chat2AnyLLM/awesome-repo-configs) · [awesome-openclaw-skills](https://github.com/VoltAgent/awesome-openclaw-skills) · [openclaw/skills](https://github.com/openclaw/skills)<br/>Tier 3: `catalog/skills/curated.json` |
| Rules | [awesome-cursorrules](https://github.com/PatrickJS/awesome-cursorrules) · [rules-2.1-optimized](https://github.com/Mr-chen-05/rules-2.1-optimized) |
| Prompts | [prompts.chat](https://github.com/f/prompts.chat) · [wonderful-prompts](https://github.com/langgptai/wonderful-prompts) |

### Pipeline at a glance

1. **Sync** — `scripts/sync_*.py` pull MCPs, skills, rules, and prompts from upstream sources.
2. **Merge** — `scripts/merge_index.py` deduplicates entries, enriches metadata, applies governance, and writes the merged catalog.
3. **Evaluate** — scoring combines source trust, relevance, content quality, freshness, and installability signals.
4. **Publish** — GitHub Actions refresh the catalog weekly, generate lightweight API files, and update both README languages.

<details>
<summary>Repository structure</summary>

```text
costrict-coding-hub/
├── install.sh                    # One-command installer for macOS/Linux
├── install.ps1                   # One-command installer for Windows
├── catalog/                      # Generated catalog data
│   ├── index.json                # Full merged index
│   ├── search-index.json         # Lightweight search index
│   ├── mcp/ skills/ rules/ prompts/
│   └── maintenance/              # Incremental recrawl state
├── docs/api/                     # Generated static API for GitHub Pages
├── platforms/                    # Per-platform skill + command definitions
├── scripts/                      # Sync, merge, scoring, and publishing scripts
├── .github/workflows/            # CI automation
└── openspec/                     # Change-management artifacts
```

</details>

<a id="platforms"></a>
## Platforms

Coding Hub supports four AI coding platforms. The resource catalog is shared, while command names and installation paths vary slightly by platform.

| | Claude Code | Costrict | Opencode | VSCode Costrict (Roo Code) |
|---|---|---|---|---|
| Search | `/coding-hub:search <kw> [type:mcp]` | `/coding-hub-search <kw> [type:mcp]` | `/coding-hub-search <kw> [type:mcp]` | `/coding-hub-search <kw> [type:mcp]` |
| Browse | `/coding-hub:browse [category]` | `/coding-hub-browse [category]` | `/coding-hub-browse [category]` | `/coding-hub-browse [category]` |
| Recommend | `/coding-hub:recommend` | `/coding-hub-recommend` | `/coding-hub-recommend` | `/coding-hub-recommend` |
| Install | `/coding-hub:install <name>` | `/coding-hub-install <name>` | `/coding-hub-install <name>` | `/coding-hub-install <name>` |
| Uninstall | `/coding-hub:uninstall <name>` | `/coding-hub-uninstall <name>` | `/coding-hub-uninstall <name>` | `/coding-hub-uninstall <name>` |
| Update | `/coding-hub:update` | `/coding-hub-update` | `/coding-hub-update` | `/coding-hub-update` |

<details>
<summary>Platform path differences</summary>

| | Claude Code | Costrict | VSCode Costrict | Opencode |
|---|---|---|---|---|
| Global skill path | `~/.claude/skills/coding-hub/` | `~/.costrict/skills/coding-hub/` | `~/.costrict/skills/coding-hub/` | `~/.opencode/skills/coding-hub/` |
| Command path | same global dir | `.costrict/coding-hub/commands/` (project) | `~/.roo/commands/` (global) | `.opencode/command/` (project) |
| Separator | `:` | `-` | `-` | `-` |

- **Costrict CLI** installs command files per project, so run the installer in each repository root.
- **VSCode Costrict / Roo Code** installs command files globally under `~/.roo/commands/`.
- **Claude Code** can load the full skill and subcommands from the global skills directory.
- **Opencode** installs commands per project under `.opencode/command/`.

</details>

<a id="for-agents"></a>
## For Agents

> If you are an AI agent installing Coding Hub automatically, follow this section exactly.

### Step 1: Run the installer

The install scripts auto-detect the host platform when possible.

**macOS / Linux**

```bash
curl -fsSL https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/install.sh | bash
```

**Windows (PowerShell)**

```powershell
irm https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/install.ps1 | iex
```

Auto-detection uses process-level environment variables that each platform injects at startup:

| Environment variable | Platform |
|----------------------|----------|
| `COSTRICT_CALLER=vscode` | VSCode Costrict extension |
| `COSTRICT_RUNNING=1` | Costrict CLI |
| `CLAUDECODE=1` | Claude Code |
| `OPENCODE=1` | Opencode |

If auto-detection fails, specify the platform manually.

**macOS / Linux**

```bash
curl -fsSL https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/install.sh | bash -s -- --platform <platform>
```

**Windows (PowerShell)**

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/install.ps1))) -Platform <platform>
```

Examples:

```bash
# Claude Code (macOS/Linux)
curl -fsSL https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/install.sh | bash -s -- --platform claude-code

# Opencode (run from the project root)
curl -fsSL https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/install.sh | bash -s -- --platform opencode
```

```powershell
# Claude Code (Windows)
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/install.ps1))) -Platform claude-code
```

<details>
<summary>Fallback: manual installation without <code>curl | bash</code></summary>

Run the platform-specific commands below if you need to download the files directly.

**Costrict CLI** (global skill + project commands)

```bash
mkdir -p ~/.costrict/skills/coding-hub
curl -fsSL "https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/platforms/costrict/skills/coding-hub/SKILL.md" -o ~/.costrict/skills/coding-hub/SKILL.md
mkdir -p .costrict/coding-hub/commands
for cmd in search browse recommend install uninstall update; do
  curl -fsSL "https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/platforms/costrict/commands/coding-hub/coding-hub-${cmd}.md" -o .costrict/coding-hub/commands/coding-hub-${cmd}.md
done
```

**VSCode Costrict extension / Roo Code** (global skill + global commands)

```bash
mkdir -p ~/.costrict/skills/coding-hub
curl -fsSL "https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/platforms/vscode-costrict/skills/coding-hub/SKILL.md" -o ~/.costrict/skills/coding-hub/SKILL.md
mkdir -p ~/.roo/commands
for cmd in search browse recommend install uninstall update; do
  curl -fsSL "https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/platforms/vscode-costrict/commands/coding-hub/coding-hub-${cmd}.md" -o ~/.roo/commands/coding-hub-${cmd}.md
done
```

**Claude Code** (global skill + global commands)

```bash
mkdir -p ~/.claude/skills/coding-hub
curl -fsSL "https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/platforms/claude-code/skills/coding-hub/SKILL.md" -o ~/.claude/skills/coding-hub/SKILL.md
for cmd in search browse recommend install uninstall update; do
  curl -fsSL "https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/platforms/claude-code/commands/coding-hub/${cmd}.md" -o ~/.claude/skills/coding-hub/${cmd}.md
done
```

**Opencode** (global skill + project commands)

```bash
mkdir -p ~/.opencode/skills/coding-hub
curl -fsSL "https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/platforms/opencode/skills/coding-hub/SKILL.md" -o ~/.opencode/skills/coding-hub/SKILL.md
mkdir -p .opencode/command
for cmd in search browse recommend install uninstall update; do
  curl -fsSL "https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/platforms/opencode/command/coding-hub-${cmd}.md" -o .opencode/command/coding-hub-${cmd}.md
done
```

</details>

### Step 2: Verify the installation

Run a search command to confirm that the commands are available:

```text
# Costrict CLI / Opencode
/coding-hub-search typescript

# VSCode Costrict extension
Send this in the chat: "Search typescript with coding-hub"

# Claude Code
/coding-hub:search typescript
```

Expected result: a Markdown table of matching resources. If the command is missing, the installation did not land in the correct platform path.

### Available commands

| Command | Description |
|---------|-------------|
| `search <keyword> [type:mcp\|skill\|rule\|prompt]` | Search resources, optionally filtered by type |
| `browse [category] [type:...]` | Browse by category |
| `recommend [type:...]` | Recommend resources based on the current project stack |
| `install <name>` | Install a resource |
| `uninstall <name>` | Uninstall a resource |
| `update` | Pull the latest Coding Hub files |

### Data endpoints

Search, browse, and recommend operate on a lightweight search index. Installation fetches a per-entry API document.

| Purpose | URL |
|---------|-----|
| Search index | `https://zgsm-sangfor.github.io/costrict-coding-hub/api/v1/search-index.json` |
| Entry API | `https://zgsm-sangfor.github.io/costrict-coding-hub/api/v1/{type}/{id}.json` |
| Type index | `https://zgsm-sangfor.github.io/costrict-coding-hub/api/v1/{type}/index.json` |
| Full index fallback | `https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/catalog/index.json` |

## Why Costrict?

If you like the Coding Hub workflow, try **[Costrict](https://github.com/zgsm-ai/costrict)** — our broader AI coding agent platform built for stronger automation and team workflows.

[Explore Costrict →](https://github.com/zgsm-ai/costrict)

<a id="contributing"></a>
## Contributing

Contributions are welcome. Open a PR against the appropriate directory under `catalog/` and make sure the resource:

- is relevant to coding or AI-assisted development,
- has an accurate `source_url`, `description`, and tags,
- follows `catalog/schema.json`.

## Disclaimer

Coding Hub is an index and installation helper for third-party open-source resources. Every MCP server, skill, rule, and prompt listed in the catalog remains the property of its original author.

This repository does **not** guarantee the safety, availability, accuracy, or compliance of third-party resources. Review source code and licenses before use, and open an issue if you find security or copyright problems.

Coding Hub is released under the [MIT License](LICENSE).
