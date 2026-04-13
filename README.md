<div align="center">
<img src="assets/logo.png" alt="Everything AI Coding logo" width="600" />
<p><strong><!-- README_APPROX_COUNT:START -->4000<!-- README_APPROX_COUNT:END -->+ curated developer resources in one index</strong><br/>MCP Servers · Skills · Rules · Prompts</p>

<p>
  <a href="https://github.com/zgsm-ai/everything-ai-coding/stargazers"><img src="https://img.shields.io/github/stars/zgsm-ai/everything-ai-coding?style=flat-square&color=4A90D9" alt="Stars" /></a>
  <a href="https://github.com/zgsm-ai/everything-ai-coding/blob/main/LICENSE"><img src="https://img.shields.io/github/license/zgsm-ai/everything-ai-coding?style=flat-square" alt="License" /></a>
  <a href="https://github.com/zgsm-ai/everything-ai-coding/commits/main"><img src="https://img.shields.io/github/last-commit/zgsm-ai/everything-ai-coding?style=flat-square" alt="Last Commit" /></a>
  <img src="https://img.shields.io/badge/resources-4040-2ECC71?style=flat-square" alt="Resources" />
</p>

<p>
  <a href="./README.md"><strong>English</strong></a> ·
  <a href="./README.zh-CN.md">简体中文</a>
</p>

<p>
  <a href="#quick-start">Quick Start</a> ·
  <a href="https://zgsm-ai.github.io/everything-ai-coding/">Browse Catalog</a> ·
  <a href="#catalog-overview">Catalog Overview</a> ·
  <a href="#platforms">Platforms</a> ·
  <a href="#for-agents">For Agents</a> ·
  <a href="#contributing">Contributing</a>
</p>
<img src="assets/title-card.jpg" alt="Everything AI Coding title card" width="900" />

</div>

## Why Everything AI Coding?

AI coding agents are improving fast, but the ecosystem around them is still fragmented. Finding a reliable MCP server, reusable skill, practical rule set, or prompt collection usually means searching across multiple repositories and formats.

Everything AI Coding turns that scattered discovery process into a single searchable catalog. It continuously syncs from curated upstream sources, deduplicates entries, enriches metadata, scores quality signals, and packages the results so humans and agents can **search and install resources with one command**.

<a id="quick-start"></a>
## Quick Start

Install Everything AI Coding for your platform with one command:

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

<div align="center">
<h3><a href="https://zgsm-ai.github.io/everything-ai-coding/">Browse the full catalog →</a></h3>
<p>Search, filter, and explore all 4000+ resources with the interactive web catalog.</p>
</div>

<a id="catalog-overview"></a>
## Catalog Overview

| Type | Count | Description |
|------|------:|-------------|
| MCP Server | <!-- README_COUNT_MCP:START -->1627<!-- README_COUNT_MCP:END --> | Model Context Protocol servers |
| Prompt | <!-- README_COUNT_PROMPT:START -->532<!-- README_COUNT_PROMPT:END --> | Developer-focused prompts |
| Rule | <!-- README_COUNT_RULE:START -->236<!-- README_COUNT_RULE:END --> | Coding rules and AI workflow conventions |
| Skill | <!-- README_COUNT_SKILL:START -->1645<!-- README_COUNT_SKILL:END --> | Reusable agent skills |

### Data sources

Everything AI Coding aggregates data from multiple upstream sources, then republishes the cleaned catalog through GitHub Pages and raw GitHub endpoints.

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
everything-ai-coding/
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
```

</details>

<a id="platforms"></a>
## Platforms

Everything AI Coding supports four AI coding platforms. The resource catalog is shared, while command names and installation paths vary slightly by platform.

| | Claude Code | Costrict | Opencode | VSCode Costrict (Roo Code) |
|---|---|---|---|---|
| Search | `/everything-ai-coding:search <kw> [type:mcp]` | `/everything-ai-coding-search <kw> [type:mcp]` | `/everything-ai-coding-search <kw> [type:mcp]` | `/everything-ai-coding-search <kw> [type:mcp]` |
| Browse | `/everything-ai-coding:browse [category]` | `/everything-ai-coding-browse [category]` | `/everything-ai-coding-browse [category]` | `/everything-ai-coding-browse [category]` |
| Recommend | `/everything-ai-coding:recommend` | `/everything-ai-coding-recommend` | `/everything-ai-coding-recommend` | `/everything-ai-coding-recommend` |
| Install | `/everything-ai-coding:install <name>` | `/everything-ai-coding-install <name>` | `/everything-ai-coding-install <name>` | `/everything-ai-coding-install <name>` |
| Uninstall | `/everything-ai-coding:uninstall <name>` | `/everything-ai-coding-uninstall <name>` | `/everything-ai-coding-uninstall <name>` | `/everything-ai-coding-uninstall <name>` |
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
## For Agents

> If you are an AI agent installing Everything AI Coding automatically, follow this section exactly.

### Step 1: Run the installer

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

### Step 2: Verify the installation

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

### Available commands

| Command | Description |
|---------|-------------|
| `search <keyword> [type:mcp\|skill\|rule\|prompt]` | Search resources, optionally filtered by type |
| `browse [category] [type:...]` | Browse by category |
| `recommend [type:...]` | Recommend resources based on the current project stack |
| `install <name>` | Install a resource |
| `uninstall <name>` | Uninstall a resource |
| `update` | Pull the latest Everything AI Coding files |

### Data endpoints

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
