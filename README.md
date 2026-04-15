<div align="center">
<img src="assets/logo.png" alt="Everything AI Coding logo" width="600" />
<p><strong><!-- README_APPROX_COUNT:START -->4000<!-- README_APPROX_COUNT:END -->+ curated AI coding resources — browse, evaluate, install</strong><br/>MCP Servers · Skills · Rules · Prompts</p>

<p>
  <a href="https://github.com/zgsm-ai/everything-ai-coding/stargazers"><img src="https://img.shields.io/github/stars/zgsm-ai/everything-ai-coding?style=flat-square&color=4A90D9" alt="Stars" /></a>
  <a href="https://github.com/zgsm-ai/everything-ai-coding/blob/main/LICENSE"><img src="https://img.shields.io/github/license/zgsm-ai/everything-ai-coding?style=flat-square" alt="License" /></a>
  <a href="https://github.com/zgsm-ai/everything-ai-coding/commits/main"><img src="https://img.shields.io/github/last-commit/zgsm-ai/everything-ai-coding?style=flat-square" alt="Last Commit" /></a>
  <img src="https://img.shields.io/badge/resources-4049-2ECC71?style=flat-square" alt="Resources" />
</p>

<p>
  <a href="./README.md"><strong>English</strong></a> ·
  <a href="./README.zh-CN.md">简体中文</a>
</p>

<p>
  <a href="#knowledge-base">Knowledge Base</a> ·
  <a href="https://zgsm-ai.github.io/everything-ai-coding/">Browse Catalog</a> ·
  <a href="#data-sources--quality">Data Sources</a> ·
  <a href="#coding-hub">Coding Hub</a> ·
  <a href="#contributing">Contributing</a>
</p>
<img src="assets/title-card.jpg" alt="Everything AI Coding title card" width="900" />

</div>

## Why Everything AI Coding?

AI coding agents are improving fast, but the ecosystem around them is still fragmented. Finding a reliable MCP server, reusable skill, practical rule set, or prompt collection usually means searching across multiple repositories and formats.

Everything AI Coding is a **curated knowledge base** that continuously collects, deduplicates, enriches, and scores resources from 9+ upstream sources. Every entry includes quality signals — source trust, coding relevance, content quality, freshness, and community popularity — so you can evaluate before you install. Browse right here on GitHub, explore interactively with the [web catalog](https://zgsm-ai.github.io/everything-ai-coding/), or search and install with one command using the [Coding Hub](#coding-hub) tool.

<a id="knowledge-base"></a>
## 📚 Knowledge Base

### [🔌 MCP Servers](./catalog/mcp/) — <!-- README_COUNT_MCP:START -->1627<!-- README_COUNT_MCP:END --> entries

Model Context Protocol servers that connect AI agents to external tools, databases, and services.

| Name | ⭐ Stars | Score | Description |
|------|----------|-------|-------------|
| [server-filesystem](https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem) | 83.6k | 93 | Official reference — local filesystem access |
| [playwright-mcp](https://github.com/microsoft/playwright-mcp) | 30.5k | 82 | Browser automation and testing by Microsoft |
| [github-mcp-server](https://github.com/github/github-mcp-server) | 28.7k | 88 | Deep GitHub API integration for workflows |
| [pydantic-ai/mcp-run-python](https://github.com/pydantic/pydantic-ai/tree/main/mcp-run-python) | 16.3k | 97 | Run Python in a secure sandbox |
| [FastAPI-MCP](https://github.com/tadata-org/fastapi_mcp) | 11.7k | 82 | Expose FastAPI endpoints as MCP tools |

[Browse all MCP servers →](./catalog/mcp/) · [Browse interactively →](https://zgsm-ai.github.io/everything-ai-coding/#/browse?type=mcp)

---

### [🎯 Skills](./catalog/skills/) — <!-- README_COUNT_SKILL:START -->1651<!-- README_COUNT_SKILL:END --> entries

Reusable agent capabilities and workflows for AI coding assistants.

| Name | Source | Score | Description |
|------|--------|-------|-------------|
| [claude-api](https://github.com/anthropics/skills/tree/main/skills/claude-api) | Anthropic Official | 96 | Build and debug Claude API / Anthropic SDK apps |
| [mcp-builder](https://github.com/anthropics/skills/tree/main/skills/mcp-builder) | Anthropic Official | 96 | Guide for creating high-quality MCP servers |
| [webapp-testing](https://github.com/anthropics/skills/tree/main/skills/webapp-testing) | Anthropic Official | 96 | Test local web apps with Playwright |
| [acceptance-orchestrator](https://github.com/sickn33/antigravity-awesome-skills/tree/main/skills/acceptance-orchestrator) | Antigravity Skills | 92 | End-to-end from requirements to deploy verification |
| [agentic-actions-auditor](https://github.com/sickn33/antigravity-awesome-skills/tree/main/skills/agentic-actions-auditor) | Antigravity Skills | 92 | Audit GitHub Actions for AI agent security |

[Browse all skills →](./catalog/skills/) · [Browse interactively →](https://zgsm-ai.github.io/everything-ai-coding/#/browse?type=skill)

---

### [📋 Rules](./catalog/rules/) — <!-- README_COUNT_RULE:START -->236<!-- README_COUNT_RULE:END --> entries

Coding conventions and AI behavior guidelines for consistent development.

| Name | Source | Score | Category |
|------|--------|-------|----------|
| [Security Audit Rules](https://github.com/Mr-chen-05/rules-2.1-optimized/tree/master/project-rules) | Curated | 94 | security |
| [Flutter & Dart Rules](https://github.com/PatrickJS/awesome-cursorrules/tree/main/rules/flutter-dart) | CursorRules | 90 | mobile |
| [Supabase Rules](https://github.com/PatrickJS/awesome-cursorrules/tree/main/rules/supabase) | CursorRules | 90 | database |
| [Disaster Recovery Plan](https://github.com/Mr-chen-05/rules-2.1-optimized/tree/master/global-rules) | Rules 2.1 | 88 | tooling |
| [Performance Monitoring System](https://github.com/Mr-chen-05/rules-2.1-optimized/tree/master/global-rules) | Rules 2.1 | 88 | devops |

[Browse all rules →](./catalog/rules/) · [Browse interactively →](https://zgsm-ai.github.io/everything-ai-coding/#/browse?type=rule)

---

### [💡 Prompts](./catalog/prompts/) — <!-- README_COUNT_PROMPT:START -->535<!-- README_COUNT_PROMPT:END --> entries

Developer-focused prompt templates for common coding tasks.

| Name | Source | Score | Category |
|------|--------|-------|----------|
| [Linux Script Developer](https://github.com/f/prompts.chat) | prompts.chat | 91 | documentation |
| [AI2sql SQL Model — Query Generator](https://github.com/f/prompts.chat) | prompts.chat | 91 | database |
| [Django Unit Test Generator](https://github.com/f/prompts.chat) | prompts.chat | 91 | backend |
| [Repository Analysis & Bug Fixing](https://github.com/f/prompts.chat) | prompts.chat | 91 | security |
| [Ultrathinker](https://github.com/f/prompts.chat) | prompts.chat | 91 | backend |

[Browse all prompts →](./catalog/prompts/) · [Browse interactively →](https://zgsm-ai.github.io/everything-ai-coding/#/browse?type=prompt)

---

<a id="data-sources--quality"></a>
## Data Sources & Quality

Everything AI Coding aggregates data from multiple upstream sources, then enriches, scores, and republishes the cleaned catalog.

| Type | Sources |
|------|---------|
| MCP | [awesome-mcp-servers](https://github.com/wong2/awesome-mcp-servers) · [Awesome-MCP-ZH](https://github.com/yzfly/Awesome-MCP-ZH) · [mcp.so](https://mcp.so) |
| Skills | Tier 1: [anthropics/skills](https://github.com/anthropics/skills) · [Ai-Agent-Skills](https://github.com/skillcreatorai/Ai-Agent-Skills) · [antigravity-awesome-skills](https://github.com/sickn33/antigravity-awesome-skills) · [ai-agents-public](https://github.com/vasilyu1983/ai-agents-public)<br/>Tier 2: [awesome-repo-configs](https://github.com/Chat2AnyLLM/awesome-repo-configs) · [awesome-openclaw-skills](https://github.com/VoltAgent/awesome-openclaw-skills) · [openclaw/skills](https://github.com/openclaw/skills)<br/>Tier 3: `catalog/skills/curated.json` |
| Rules | [awesome-cursorrules](https://github.com/PatrickJS/awesome-cursorrules) · [rules-2.1-optimized](https://github.com/Mr-chen-05/rules-2.1-optimized) |
| Prompts | [prompts.chat](https://github.com/f/prompts.chat) · [wonderful-prompts](https://github.com/langgptai/wonderful-prompts) |

### Quality scoring

Every entry is scored on a 0-100 composite scale:

- **Coding relevance** (1-5) — How directly useful for development
- **Content quality** (1-5) — Documentation, maintenance, completeness
- **Source trust** (1-5) — Upstream reputation (e.g., Anthropic Official = 5, mcp.so = 2)
- **Community signals** — GitHub stars, freshness (🟢 Active / 🟡 Stale / 🔴 Abandoned), installability

Each sub-directory README shows the Top 100 entries ranked by this composite score.

### Pipeline

1. **Sync** — `scripts/sync_*.py` pull from upstream sources weekly
2. **Merge** — `scripts/merge_index.py` deduplicates, enriches metadata, applies governance
3. **Evaluate** — LLM + heuristic scoring for relevance, quality, and specificity
4. **Publish** — GitHub Actions refresh the catalog, generate README tables, and update the web catalog

<details>
<summary>Repository structure</summary>

```text
everything-ai-coding/
├── install.sh / install.ps1      # One-command installers
├── catalog/                      # Generated catalog data
│   ├── index.json                # Full merged index (4000+ entries)
│   ├── search-index.json         # Lightweight search index
│   ├── mcp/                      # MCP servers — index + README
│   ├── skills/                   # Skills — index + README
│   ├── rules/                    # Rules — index + README
│   └── prompts/                  # Prompts — index + README
├── platforms/                    # Per-platform skill + command definitions
├── scripts/                      # Sync, merge, scoring, and generation scripts
└── .github/workflows/            # CI automation
```

</details>

---

<a id="coding-hub"></a>
## 🛠 Coding Hub — Search & Install

Everything AI Coding also ships as a CLI tool that lets you search, browse, and install resources directly from your AI coding agent.

### Quick Start

Install for your platform with one command:

**macOS / Linux**

```bash
# Costrict CLI (run from your project root)
curl -fsSL https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/install.sh | bash -s -- --platform costrict

# VSCode Costrict extension
curl -fsSL https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/install.sh | bash -s -- --platform vscode-costrict

# Claude Code
curl -fsSL https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/install.sh | bash -s -- --platform claude-code

# Opencode (run from your project root)
curl -fsSL https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/install.sh | bash -s -- --platform opencode
```

**Windows (PowerShell)**

```powershell
# Costrict CLI
irm https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/install.ps1 | iex

# Specify the platform manually if auto-detection fails
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/install.ps1))) -Platform costrict
```

After installation, try a search command:

```bash
# Claude Code
/everything-ai-coding:search typescript

# Opencode / Costrict CLI / VSCode Costrict (Roo Code)
/everything-ai-coding-search typescript
```

<video src="https://github.com/user-attachments/assets/e58f0b08-73c0-4fba-ac95-138c8087a917" controls width="100%"></video>

You can also hand the installation off to another agent with this prompt:

```text
You are an installation assistant. Open the following URL, read the "For Agents" section,
and follow it exactly to install Everything AI Coding for the platform you are currently running on.

Do not clone the repository. Only read this raw file:
https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/README.md

After installation, report which platform path was used and whether verification succeeded.
```

### Platforms

Everything AI Coding supports four AI coding platforms. The resource catalog is shared, while command names and installation paths vary slightly by platform.

| | Claude Code | Costrict | Opencode | VSCode Costrict (Roo Code) |
|---|---|---|---|---|
| Search | `/everything-ai-coding:search <kw> [type:mcp]` | `/everything-ai-coding-search <kw> [type:mcp]` | `/everything-ai-coding-search <kw> [type:mcp]` | `/everything-ai-coding-search <kw> [type:mcp]` |
| Browse | `/everything-ai-coding:browse [category]` | `/everything-ai-coding-browse [category]` | `/everything-ai-coding-browse [category]` | `/everything-ai-coding-browse [category]` |
| Recommend | `/everything-ai-coding:recommend` | `/everything-ai-coding-recommend` | `/everything-ai-coding-recommend` | `/everything-ai-coding-recommend` |
| Install | `/everything-ai-coding:install <id>` | `/everything-ai-coding-install <id>` | `/everything-ai-coding-install <id>` | `/everything-ai-coding-install <id>` |
| Uninstall | `/everything-ai-coding:uninstall <id>` | `/everything-ai-coding-uninstall <id>` | `/everything-ai-coding-uninstall <id>` | `/everything-ai-coding-uninstall <id>` |
| Update | `/everything-ai-coding:update` | `/everything-ai-coding-update` | `/everything-ai-coding-update` | `/everything-ai-coding-update` |

<details>
<summary>Platform path differences</summary>

| | Claude Code | Costrict | VSCode Costrict | Opencode |
|---|---|---|---|---|
| Global skill path | `~/.claude/skills/everything-ai-coding/` | `~/.costrict/skills/everything-ai-coding/` | `~/.costrict/skills/everything-ai-coding/` | `~/.opencode/skills/everything-ai-coding/` |
| Command path | same global dir | `.costrict/everything-ai-coding/commands/` (project) | `~/.roo/commands/` (global) | `.opencode/command/` (project) |
| Separator | `:` | `-` | `-` | `-` |

- **Costrict CLI** installs command files per project, so run the installer in each repository root.
- **VSCode Costrict / Roo Code** installs command files globally under `~/.roo/commands/`.
- **Claude Code** can load the full skill and subcommands from the global skills directory.
- **Opencode** installs commands per project under `.opencode/command/`.

</details>

<a id="for-agents"></a>
### For Agents

> If you are an AI agent installing Everything AI Coding automatically, follow this section exactly.

#### Step 1: Run the installer

The install scripts auto-detect the host platform when possible.

**macOS / Linux**

```bash
curl -fsSL https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/install.sh | bash
```

**Windows (PowerShell)**

```powershell
irm https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/install.ps1 | iex
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
curl -fsSL https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/install.sh | bash -s -- --platform <platform>
```

**Windows (PowerShell)**

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/install.ps1))) -Platform <platform>
```

Examples:

```bash
# Claude Code (macOS/Linux)
curl -fsSL https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/install.sh | bash -s -- --platform claude-code

# Opencode (run from the project root)
curl -fsSL https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/install.sh | bash -s -- --platform opencode
```

```powershell
# Claude Code (Windows)
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/install.ps1))) -Platform claude-code
```

<details>
<summary>Fallback: manual installation without <code>curl | bash</code></summary>

Run the platform-specific commands below if you need to download the files directly.

**Costrict CLI** (global skill + project commands)

```bash
mkdir -p ~/.costrict/skills/everything-ai-coding
curl -fsSL "https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/platforms/costrict/skills/everything-ai-coding/SKILL.md" -o ~/.costrict/skills/everything-ai-coding/SKILL.md
mkdir -p .costrict/everything-ai-coding/commands
for cmd in search browse recommend install uninstall update; do
  curl -fsSL "https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/platforms/costrict/commands/everything-ai-coding/everything-ai-coding-${cmd}.md" -o .costrict/everything-ai-coding/commands/everything-ai-coding-${cmd}.md
done
```

**VSCode Costrict extension / Roo Code** (global skill + global commands)

```bash
mkdir -p ~/.costrict/skills/everything-ai-coding
curl -fsSL "https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/platforms/vscode-costrict/skills/everything-ai-coding/SKILL.md" -o ~/.costrict/skills/everything-ai-coding/SKILL.md
mkdir -p ~/.roo/commands
for cmd in search browse recommend install uninstall update; do
  curl -fsSL "https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/platforms/vscode-costrict/commands/everything-ai-coding/everything-ai-coding-${cmd}.md" -o ~/.roo/commands/everything-ai-coding-${cmd}.md
done
```

**Claude Code** (global skill + global commands)

```bash
mkdir -p ~/.claude/skills/everything-ai-coding
curl -fsSL "https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/platforms/claude-code/skills/everything-ai-coding/SKILL.md" -o ~/.claude/skills/everything-ai-coding/SKILL.md
for cmd in search browse recommend install uninstall update; do
  curl -fsSL "https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/platforms/claude-code/commands/everything-ai-coding/${cmd}.md" -o ~/.claude/skills/everything-ai-coding/${cmd}.md
done
```

**Opencode** (global skill + project commands)

```bash
mkdir -p ~/.opencode/skills/everything-ai-coding
curl -fsSL "https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/platforms/opencode/skills/everything-ai-coding/SKILL.md" -o ~/.opencode/skills/everything-ai-coding/SKILL.md
mkdir -p .opencode/command
for cmd in search browse recommend install uninstall update; do
  curl -fsSL "https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/platforms/opencode/command/everything-ai-coding-${cmd}.md" -o .opencode/command/everything-ai-coding-${cmd}.md
done
```

</details>

#### Step 2: Verify the installation

Run a search command to confirm that the commands are available:

```text
# Costrict CLI / Opencode
/everything-ai-coding-search typescript

# VSCode Costrict extension
Send this in the chat: "Search typescript with everything-ai-coding"

# Claude Code
/everything-ai-coding:search typescript
```

Expected result: a Markdown table of matching resources. If the command is missing, the installation did not land in the correct platform path.

#### Available commands

| Command | Description |
|---------|-------------|
| `search <keyword> [type:mcp\|skill\|rule\|prompt]` | Search resources, optionally filtered by type |
| `browse [category] [type:...]` | Browse by category |
| `recommend [type:...]` | Recommend resources based on the current project stack |
| `install <id>` | Install a resource |
| `uninstall <id>` | Uninstall a resource |
| `update` | Pull the latest Everything AI Coding files |

#### Data endpoints

Search, browse, and recommend operate on a lightweight search index. Installation fetches a per-entry API document.

| Purpose | URL |
|---------|-----|
| Search index | `https://zgsm-ai.github.io/everything-ai-coding/api/v1/search-index.json` |
| Entry API | `https://zgsm-ai.github.io/everything-ai-coding/api/v1/{type}/{id}.json` |
| Type index | `https://zgsm-ai.github.io/everything-ai-coding/api/v1/{type}/index.json` |
| Full index fallback | `https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/catalog/index.json` |

## Why Costrict?

If you like the Everything AI Coding workflow, try **[Costrict](https://github.com/zgsm-ai/costrict)** — our broader AI coding agent platform built for stronger automation and team workflows.

[Explore Costrict →](https://github.com/zgsm-ai/costrict)

<a id="contributing"></a>
## Contributing

Contributions are welcome. Open a PR against the appropriate directory under `catalog/` and make sure the resource:

- is relevant to coding or AI-assisted development,
- has an accurate `source_url`, `description`, and tags,
- follows `catalog/schema.json`.

If you need maintainers' context instead of quick-start instructions, see the repository wiki in [`docs/wiki/`](./docs/wiki/README.md).

## Disclaimer

Everything AI Coding is an index and installation helper for third-party open-source resources. Every MCP server, skill, rule, and prompt listed in the catalog remains the property of its original author.

This repository does **not** guarantee the safety, availability, accuracy, or compliance of third-party resources. Review source code and licenses before use, and open an issue if you find security or copyright problems.

Everything AI Coding is released under the [MIT License](LICENSE).
