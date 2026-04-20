<div align="center">
<img src="assets/logo.png" alt="Everything AI Coding logo" width="600" />
<p><strong><!-- README_APPROX_COUNT:START -->4000<!-- README_APPROX_COUNT:END -->+ curated AI coding resources — browse, evaluate, install</strong><br/>MCP Servers · Skills · Rules · Prompts</p>

<p>
  <a href="https://github.com/zgsm-ai/everything-ai-coding/stargazers"><img src="https://img.shields.io/github/stars/zgsm-ai/everything-ai-coding?style=flat-square&color=4A90D9" alt="Stars" /></a>
  <a href="https://github.com/zgsm-ai/everything-ai-coding/blob/main/LICENSE"><img src="https://img.shields.io/github/license/zgsm-ai/everything-ai-coding?style=flat-square" alt="License" /></a>
  <a href="https://github.com/zgsm-ai/everything-ai-coding/commits/main"><img src="https://img.shields.io/github/last-commit/zgsm-ai/everything-ai-coding?style=flat-square" alt="Last Commit" /></a>
  <img src="https://img.shields.io/badge/resources-4077-2ECC71?style=flat-square" alt="Resources" />
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

Everything AI Coding is a **curated knowledge base** that continuously collects, deduplicates, enriches, and scores resources from 9+ upstream sources. Every entry includes quality signals — LLM-scored coding relevance, documentation quality, specificity, plus health metrics like freshness and community popularity — so you can evaluate before you install. Browse right here on GitHub, explore interactively with the [web catalog](https://zgsm-ai.github.io/everything-ai-coding/), or search and install with one command using the [Coding Hub](#coding-hub) tool.

<a id="knowledge-base"></a>
## 📚 Knowledge Base

### [🔌 MCP Servers](./catalog/mcp/) — <!-- README_COUNT_MCP:START -->1628<!-- README_COUNT_MCP:END --> entries

Model Context Protocol servers that connect AI agents to external tools, databases, and services.

<!-- README_TOP5_MCP:START -->
| Name | ⭐ Stars | Score | Description |
|------|----------|-------|-------------|
| [MCP Inspector](https://github.com/modelcontextprotocol/inspector) | 9.2k | 99 | A developer tool for visually testing and debugging Model Context Pro… |
| [Desktop Commander MCP](https://github.com/wonderwhy-er/DesktopCommanderMCP) | 5.8k | 99 | MCP server enabling AI assistants to control terminals, edit files, a… |
| [Context 7](https://github.com/upstash/context7-mcp) | 53.2k | 98 | MCP server that fetches up-to-date library documentation and code exa… |
| [microsoft/playwright-mcp](https://github.com/microsoft/playwright-mcp) | 31.1k | 98 | An MCP server that enables AI agents to automate web browsers using P… |
| [github/github-mcp-server](https://github.com/github/github-mcp-server) | 29.1k | 98 | An official MCP server that connects AI agents to GitHub for reposito… |
<!-- README_TOP5_MCP:END -->

[Browse all MCP servers →](./catalog/mcp/) · [Browse interactively →](https://zgsm-ai.github.io/everything-ai-coding/#/browse?type=mcp)

---

### [🎯 Skills](./catalog/skills/) — <!-- README_COUNT_SKILL:START -->1671<!-- README_COUNT_SKILL:END --> entries

Reusable agent capabilities and workflows for AI coding assistants.

<!-- README_TOP5_SKILL:START -->
| Name | Source | Score | Description |
|------|--------|-------|-------------|
| [MCP Integration](https://github.com/anthropics/claude-code/tree/main/plugins/plugin-dev/skills/mcp-integration) | Anthropic Official | 97 | Guide for integrating Model Context Protocol (MCP) servers into Claud… |
| [skill-creator](https://github.com/anthropics/skills/tree/main/skills/skill-creator) | Anthropic Official | 96 | An AI skill for creating, testing, and optimizing other AI skills thr… |
| [slack-gif-creator](https://github.com/anthropics/skills/tree/main/skills/slack-gif-creator) | Anthropic Official | 96 | A Python toolkit for creating and optimizing animated GIFs specifical… |
| [xlsx](https://github.com/anthropics/skills/tree/main/skills/xlsx) | Anthropic Official | 96 | An AI skill for creating, editing, and analyzing spreadsheet files (E… |
| [ui-ux-pro-max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill/tree/main/.claude/skills/ui-ux-pro-max) | nextlevelbuilder/ui-ux-pro-max-skill | 95 | A comprehensive AI skill providing UI/UX design intelligence, guideli… |
<!-- README_TOP5_SKILL:END -->

[Browse all skills →](./catalog/skills/) · [Browse interactively →](https://zgsm-ai.github.io/everything-ai-coding/#/browse?type=skill)

---

### [📋 Rules](./catalog/rules/) — <!-- README_COUNT_RULE:START -->236<!-- README_COUNT_RULE:END --> entries

Coding conventions and AI behavior guidelines for consistent development.

<!-- README_TOP5_RULE:START -->
| Name | Source | Score | Category |
|------|--------|-------|----------|
| [Backend Rules (Rules 2.1)](https://github.com/Mr-chen-05/rules-2.1-optimized/blob/master/global-rules/backend-rules.mdc) | Rules 2.1 | 89 | ai-ml |
| [Feedback Enhanced (Rules 2.1)](https://github.com/Mr-chen-05/rules-2.1-optimized/blob/master/project-rules/feedback-enhanced.mdc) | Rules 2.1 | 88 | tooling |
| [Bug Fix (Rules 2.1)](https://github.com/Mr-chen-05/rules-2.1-optimized/blob/master/project-rules/bug-fix.mdc) | Rules 2.1 | 86 | tooling |
| [Mcp Intelligent Strategy (Rules 2.1)](https://github.com/Mr-chen-05/rules-2.1-optimized/blob/master/project-rules/mcp-intelligent-strategy.mdc) | Rules 2.1 | 86 | tooling |
| [File Generation Safety Rules (Rules 2.1)](https://github.com/Mr-chen-05/rules-2.1-optimized/blob/master/global-rules/file-generation-safety-rules.mdc) | Rules 2.1 | 86 | ai-ml |
<!-- README_TOP5_RULE:END -->

[Browse all rules →](./catalog/rules/) · [Browse interactively →](https://zgsm-ai.github.io/everything-ai-coding/#/browse?type=rule)

---

### [💡 Prompts](./catalog/prompts/) — <!-- README_COUNT_PROMPT:START -->542<!-- README_COUNT_PROMPT:END --> entries

Developer-focused prompt templates for common coding tasks.

<!-- README_TOP5_PROMPT:START -->
| Name | Source | Score | Category |
|------|--------|-------|----------|
| [Comprehensive repository analysis](https://github.com/f/prompts.chat/blob/HEAD/PROMPTS.md#comprehensive-repository-analysis) | prompts.chat | 96 | security |
| [Rapid Prototyper](https://github.com/f/prompts.chat/blob/HEAD/PROMPTS.md#rapid-prototyper) | prompts.chat | 96 | backend |
| [Multiplayer 3D Plane Game](https://github.com/f/prompts.chat/blob/HEAD/PROMPTS.md#multiplayer-3d-plane-game) | prompts.chat | 92 | frontend |
| [Todo List](https://github.com/f/prompts.chat/blob/HEAD/PROMPTS.md#todo-list) | prompts.chat | 92 | frontend |
| [Django Unit Test Generator for Viewsets](https://github.com/f/prompts.chat/blob/HEAD/PROMPTS.md#django-unit-test-generator-for-viewsets) | prompts.chat | 92 | backend |
<!-- README_TOP5_PROMPT:END -->

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

Every entry is scored on a 0–100 composite scale: `final_score = LLM × 0.85 + health × 0.15`.

**LLM dimensions** (1–5, up to 6 per type): coding relevance, doc completeness, description accuracy, writing quality, specificity, install clarity (MCP & Skills only)

**Health signals**: freshness (🟢 Active / 🟡 Stale / 🔴 Abandoned), popularity (GitHub stars), source trust (upstream reputation)

**Decisions**: accept (≥ 65) · review (50–64) · reject (< 50)

Each sub-directory README shows the Top 100 entries ranked by this composite score.

### Pipeline

1. **Sync** — `scripts/sync_*.py` pull from upstream sources weekly
2. **Merge** — `scripts/merge_index.py` deduplicates across sources, merges metadata
3. **Evaluate** — Single LLM call: 6-dimension scoring + enrichment (tags, summary, tech_stack) + health signals
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
/eac:search typescript

# Opencode / Costrict CLI / VSCode Costrict (Roo Code)
/eac-search typescript
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
| Search | `/eac:search <kw> [type:mcp]` | `/eac-search <kw> [type:mcp]` | `/eac-search <kw> [type:mcp]` | `/eac-search <kw> [type:mcp]` |
| Browse | `/eac:browse [category]` | `/eac-browse [category]` | `/eac-browse [category]` | `/eac-browse [category]` |
| Recommend | `/eac:recommend` | `/eac-recommend` | `/eac-recommend` | `/eac-recommend` |
| Install | `/eac:install <id>` | `/eac-install <id>` | `/eac-install <id>` | `/eac-install <id>` |
| Uninstall | `/eac:uninstall <id>` | `/eac-uninstall <id>` | `/eac-uninstall <id>` | `/eac-uninstall <id>` |
| Update | `/eac:update` | `/eac-update` | `/eac-update` | `/eac-update` |
| Evo | `/eac:evo <id>` | `/eac-evo <id>` | `/eac-evo <id>` | `/eac-evo <id>` |

<details>
<summary>Platform path differences</summary>

| | Claude Code | Costrict | VSCode Costrict | Opencode |
|---|---|---|---|---|
| Global skill path | `~/.claude/skills/eac/` | `~/.costrict/skills/eac/` | `~/.costrict/skills/eac/` | `~/.opencode/skills/eac/` |
| Command path | same global dir | `.costrict/eac/commands/` (project) | `~/.roo/commands/` (global) | `.opencode/command/` (project) |
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
mkdir -p ~/.costrict/skills/eac
curl -fsSL "https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/platforms/costrict/skills/eac/SKILL.md" -o ~/.costrict/skills/eac/SKILL.md
mkdir -p .costrict/eac/commands
for cmd in search browse recommend install uninstall update; do
  curl -fsSL "https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/platforms/costrict/commands/eac/eac-${cmd}.md" -o .costrict/eac/commands/eac-${cmd}.md
done
```

**VSCode Costrict extension / Roo Code** (global skill + global commands)

```bash
mkdir -p ~/.costrict/skills/eac
curl -fsSL "https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/platforms/vscode-costrict/skills/eac/SKILL.md" -o ~/.costrict/skills/eac/SKILL.md
mkdir -p ~/.roo/commands
for cmd in search browse recommend install uninstall update; do
  curl -fsSL "https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/platforms/vscode-costrict/commands/eac/eac-${cmd}.md" -o ~/.roo/commands/eac-${cmd}.md
done
```

**Claude Code** (global skill + global commands)

```bash
mkdir -p ~/.claude/skills/eac
curl -fsSL "https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/platforms/claude-code/skills/eac/SKILL.md" -o ~/.claude/skills/eac/SKILL.md
for cmd in search browse recommend install uninstall update; do
  curl -fsSL "https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/platforms/claude-code/commands/eac/${cmd}.md" -o ~/.claude/skills/eac/${cmd}.md
done
```

**Opencode** (global skill + project commands)

```bash
mkdir -p ~/.opencode/skills/eac
curl -fsSL "https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/platforms/opencode/skills/eac/SKILL.md" -o ~/.opencode/skills/eac/SKILL.md
mkdir -p .opencode/command
for cmd in search browse recommend install uninstall update; do
  curl -fsSL "https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/platforms/opencode/command/eac-${cmd}.md" -o .opencode/command/eac-${cmd}.md
done
```

</details>

#### Step 2: Verify the installation

Run a search command to confirm that the commands are available:

```text
# Costrict CLI / Opencode
/eac-search typescript

# VSCode Costrict extension
Send this in the chat: "Search typescript with eac"

# Claude Code
/eac:search typescript
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
| `evo <id>` | Evolve a locally installed skill / prompt / rule via a 7-dimension quality rubric (adapted from [darwin-skill](https://github.com/alchaincyf/darwin-skill)) |

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

## Acknowledgments

The `/eac:evo` command's quality rubric is adapted from **[darwin-skill](https://github.com/alchaincyf/darwin-skill)** by 花叔 (MIT License) — an autonomous skill optimization system inspired by Karpathy's autoresearch. darwin-skill first systematized a "structure + effectiveness" dual-evaluation framework for SKILL.md files with a ratchet mechanism for keeping only measurable improvements. Everything AI Coding simplifies it for on-demand client-side use: the dynamic live-testing dimension and the ratchet are deferred; the core dimensions (workflow clarity, instruction specificity, edge-case coverage, checkpoint design, overall architecture, etc.) are preserved and rewritten for our on-demand evo context. See [`docs/wiki/evo-rubric.md`](./docs/wiki/evo-rubric.md) for the full rubric specification.

Thanks to 花叔 for making the ideas and the original skill publicly available.

## Disclaimer

Everything AI Coding is an index and installation helper for third-party open-source resources. Every MCP server, skill, rule, and prompt listed in the catalog remains the property of its original author.

This repository does **not** guarantee the safety, availability, accuracy, or compliance of third-party resources. Review source code and licenses before use, and open an issue if you find security or copyright problems.

Everything AI Coding is released under the [MIT License](LICENSE).
