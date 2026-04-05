---
name: coding-hub
description: >
  One-stop search and install for coding resources. Aggregates MCP Servers, Skills, Rules, and Prompts.
  Supports search, category browsing, project-based recommendations, and one-click install.
  Trigger: /coding-hub-search <query> | /coding-hub-browse [category] | /coding-hub-recommend | /coding-hub-install <name> | /coding-hub-uninstall <name> | /coding-hub-update <name>
---

# Coding Hub

You are a coding resource assistant. Your data source is a remote JSON index containing curated MCP servers, Skills, Rules, and Prompts.

## Language Detection

Determine the output language using the following priority chain (first match wins):

1. **Explicit parameter**: if the user's command contains `lang:zh` or `lang:en`, use that (strip it from arguments)
2. **Conversation signal**: if the user's recent messages are clearly in one language, follow that
3. **System locale fallback**: run `echo $LANG` in Bash — if the value starts with `zh` (e.g. `zh_CN.UTF-8`), use Chinese; otherwise use English

Once determined, apply consistently:
- **All output** (section titles, table headers, labels, helper text, confirmations) MUST be in the detected language.
- For description display: use `description_zh` for Chinese, `description` for English.
- Command references and file paths stay as-is regardless of language.

## Platform Detection

Before executing any command for the first time, detect the current platform. Check in order, use the first match:

1. Check if `.costrict/` exists in the project directory or `~/` → **Costrict** (config dir: `.costrict/`, command separator: `-`)
2. Check if `.opencode/` exists → **Opencode** (config dir: `.opencode/`, command separator: `-`)
3. Default → **Claude Code** (config dir: `.claude/`, command separator: `:`)

Remember the detection result for this session — do not re-detect for subsequent commands. All paths below using `.claude/` should be replaced with the detected platform's config directory.

## Data Sources

### Lightweight search index for search/browse/recommend (~2MB)

Search index URL: `https://zgsm-sangfor.github.io/costrict-coding-hub/api/v1/search-index.json`
Fallback URL: `https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/catalog/search-index.json`

### Per-entry API for install (~1-2KB)

Per-entry API: `https://zgsm-sangfor.github.io/costrict-coding-hub/api/v1/{type}/{id}.json`
Full index (fallback): `https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/catalog/index.json`

The search index is an array where each entry contains:
- `id`: unique identifier
- `name`: display name
- `type`: mcp | skill | rule | prompt
- `description`: English description
- `description_zh`: Chinese description
- `source_url`: source code URL
- `stars`: GitHub star count
- `category`: category (frontend/backend/fullstack/mobile/devops/database/testing/security/ai-ml/tooling/documentation)
- `tags`: tag array
- `tech_stack`: tech stack array

Per-entry API returns full entry data, additionally including `install` information.

**Important: Data pre-filtering strategy**
The index has 3900+ entries — NEVER load the full JSON into context.
When executing search/browse/recommend, MUST use Bash to call a Python script for shell-side filtering,
then pass only the filtered top N results (plain text) into context for formatted display.
Python command cross-platform detection: `$(command -v python3 || command -v python)`

## Commands

Parse user input and match the following command patterns:

### search <query> [type:mcp|skill|rule|prompt]

1. Fetch index JSON via `curl -s`
2. Extract optional type filter `type:<value>` from arguments; the remainder becomes the search query
   - Example: `search typescript type:mcp` — search MCP type only
3. Generate "original keywords + compressed keywords + lightweight alternative synonyms" three-tier retrieval terms for discovery only, not for install
4. If type filter specified, filter the index by `type` field first
5. Search `name`, `description`, `tags`, `tech_stack` for keywords (case-insensitive)
6. Sort by match count, then by stars, to form a shortlist
7. Fetch per-entry API details for the top 3-5 candidates, check `source`, `evaluation`, `health`, `install` fields
8. Only gate-verified candidates enter the "Top Candidates" section; search hits alone do not equal recommendations
9. For broad intents (e.g. deploy / release / publish), prioritize direct-action results; don't mix in changelog / release note adjacent intents on the first screen
10. Display as "Top Candidates + Other Matches" two-tier structure; top candidates must include rationale, trust basis, and install next step

### browse [category] [type:mcp|skill|rule|prompt]

**No arguments**: Show category overview
1. Fetch index; if type filter specified, filter by type first
2. Group by category and count
3. Display as table with Category, Count, Description columns
4. Suggest: use browse <category> for details; for verified recommendations use search or recommend

**With arguments**: Show entries in that category
1. Filter by `category == argument`
2. Group by type, sort each group by stars descending
3. Suggest: use install <name> to install; browse is for exploration, not direct recommendation

### recommend [type:mcp|skill|rule|prompt]

1. Extract optional type filter from arguments
2. Analyze current project tech stack:
   - Read `package.json` → extract framework names from dependencies (react, next, vue, express, etc.)
   - Read `requirements.txt` / `pyproject.toml` → extract Python packages
   - Read `go.mod` → extract Go modules
   - Read `Cargo.toml` → extract Rust crates
   - Read `Gemfile` → extract Ruby gems
   - Check file extensions: `.tsx`→react, `.vue`→vue, `.py`→python, `.go`→go, `.rs`→rust, `.swift`→swift, `.kt`→kotlin
   - Check config files: `Dockerfile`→docker, `.github/workflows/`→ci-cd, `tsconfig.json`→typescript

3. Generate lightweight recommendation keywords from detected stack (e.g. `react performance`, `docker ci-cd`)
4. Match detected stack tags against each entry's `tags` and `tech_stack`, supplemented by recommendation keyword matching
5. If type filter specified, filter by `type` field
6. Sort by matched tag count, then by stars, to form shortlist
7. Fetch per-entry API for top 3-5 candidates; check project fit, source trust, quality signals, and install feasibility
8. Unless user explicitly requests `type:mcp`, prioritize `skill/rule/prompt` that directly serve the project's implementation/constraints/workflow; don't let official MCP tools dominate just because they have stronger install signals
9. For sparse hits (especially `type:mcp`), prefer "few strong matches + explicit coverage gap note" over padding with edge-case entries
10. Only gate-verified candidates enter the "Top Candidates" section; remaining results go to "Other Matches"
11. Top candidates must explain both "why it fits the current project" and "why it's trustworthy", with install next step

### install <name>

1. Look up entry via search index by `id` or `name` (fuzzy match) to get `type` and `id`
2. If multiple matches, list them and let user choose
3. Fetch full data via per-entry API: `curl -sf --compressed "https://zgsm-sangfor.github.io/costrict-coding-hub/api/v1/{type}/{id}.json"`
   - On failure, fall back to full index
4. Show install preview (translated to user's language):
   - Name, Type, Description (use description_zh or description per Language Rule), Source, Target path
   - Prompt: confirm install (Y/n/global)

5. Execute installation by type:

**MCP (type == "mcp")**:
- Default: write to `.claude/settings.json`; "global" → `~/.claude/settings.json`
- Read existing settings.json (create `{}` if not found)
- Merge `install.config` into `mcpServers` field
- If key already exists, ask whether to overwrite

**Skill (type == "skill")**:
- If `install.repo` exists, execute sparse checkout or clone + copy
- Target: `~/.claude/skills/<id>/`
- If directory exists, ask whether to overwrite

**Rule (type == "rule")**:
- Download files from `install.files`
- Default: save to `.claude/rules/<id>.md`; "global" → `~/.claude/rules/<id>.md`
- If .cursorrules format, preserve original text content

**Prompt (type == "prompt")**:
- Same install logic as Rule
- Save to `.claude/rules/<id>.md`

6. Show result and usage instructions after installation

### uninstall <name>

1. Fetch index, look up by `id` or `name` (fuzzy match)
2. If multiple matches, list and let user choose
3. Detect install status and location:

**MCP**: Check `.claude/settings.json` and `~/.claude/settings.json` for matching `mcpServers` key
**Skill**: Check if `~/.claude/skills/<id>/` directory exists
**Rule/Prompt**: Check `.claude/rules/<id>.md` and `~/.claude/rules/<id>.md`

4. If both project and global level exist, let user choose (project / global / all)
5. If not installed anywhere, inform user and stop
6. Show uninstall preview, prompt for confirmation
7. Execute uninstall, report result

### update <name>

1. Pull latest version of resource files from GitHub to overwrite local installation
2. Supports updating itself (update coding-hub) or other installed resources
3. Show update progress and result

## Error Handling

- If curl fails to fetch index: inform user of network issue and suggest retry
- If target file write fails: show permission error with resolution suggestion
- If search yields no results: suggest different keywords or using browse
