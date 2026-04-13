---
description: 'Install a coding resource. Usage: /everything-ai-coding:install <name>'
---

# Everything AI Coding - Install

$ARGUMENTS

---

## Language Detection

Determine the output language using the following priority chain (first match wins):

1. **Explicit parameter**: if `$ARGUMENTS` contains `lang:zh` or `lang:en`, use that (strip it from arguments)
2. **Conversation signal**: if the user's recent messages are clearly in one language, follow that
3. **System locale fallback**: run `echo $LANG` in Bash — if the value starts with `zh` (e.g. `zh_CN.UTF-8`), use Chinese; otherwise use English

Once determined, apply consistently:
- **All output** (confirmation dialogs, status messages, error messages) MUST be in the detected language.
- Command references and file paths stay as-is regardless of language.

## Data Sources

**Note**: Apply GitHub Network Detection rules (see SKILL.md) to all GitHub URLs below. If `[network-config]` specifies a proxy, rewrite URLs accordingly.

Per-entry API: `https://zgsm-ai.github.io/everything-ai-coding/api/v1/{type}/{id}.json`
Full index (fallback): `https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/catalog/index.json`
Local fallback: `/Volumes/Work/Projects/everything-ai-coding/catalog/index.json`

## Execution Flow

1. Extract resource name from `$ARGUMENTS`
2. Look up entry by ID via per-entry API (requires determining type and id from search index first):
   - Download search index: `curl -sf --compressed https://zgsm-ai.github.io/everything-ai-coding/api/v1/search-index.json`
   - Fuzzy match on name/id with Python to determine the entry's `type` and `id`
   - If exactly one match found, fetch full data: `curl -sf --compressed https://zgsm-ai.github.io/everything-ai-coding/api/v1/{type}/{id}.json`
   - If multiple matches, list them and let the user choose, then fetch the selected one
3. If Pages API unavailable, fall back to full index: `curl -s <full index URL>`, on failure use Read on local fallback path
4. Show install preview (in user's language):

```
Structure:
  Section: "Install Confirmation"
  - Name: xxx
  - Type: MCP Server
  - Description: (use description_zh or description per Language Rule)
  - Source: xxx
  - Target: .claude/settings.json (project-level)
  - [if type is rule/prompt/skill]: "✨ Supports customization — you can tailor this to your project after install"

  Prompt: "Confirm install? (Y/n/global)"
```

Do NOT show the customization hint for MCP type.

5. Execute installation based on user confirmation and resource type:

### MCP (type == "mcp")
- Default: write to `.claude/settings.json`; if user chooses "global", write to `~/.claude/settings.json`
- Read existing settings.json (create `{}` if not found)
- Handle by `install.method`:

#### method == "mcp_config"
- Merge `install.config` directly into the `mcpServers` field
- If key already exists, ask whether to overwrite
- If `install.config.env` contains any values → run **Post-Install Configuration Guide** (see below)

#### method == "mcp_config_template"
- Write `install.config` into `mcpServers` field first (so entry exists even if user skips config)
- Then run **Post-Install Configuration Guide** (see below)

#### Post-Install Configuration Guide

When the installed MCP config contains `env` fields (API keys, tokens, connection strings, etc.):

1. **Detect unconfigured env vars** — any env value that is empty, contains `<`, `YOUR_`, or placeholder-like patterns
2. **Fetch the project README for setup guidance**:
   - **Note**: Apply GitHub Network Detection rules (see SKILL.md) to `source_url` before fetching.
   - Use WebFetch on the entry's `source_url` with prompt: "Extract: 1) What API keys or environment variables are needed 2) How to obtain them (signup URL, steps) 3) Example configuration. Be concise, bullet points only."
   - If `source_url` is a GitHub monorepo subpath and fetch fails, try the repo root URL instead
3. **Present actionable guidance** to the user (in detected language):
```
Structure:
  Section: "Configuration Required"
  Per env var:
    - KEY_NAME: [guidance extracted from README — how to obtain, signup URL, etc.]
  Action: "Would you like me to help you fill in these values now?"
```
4. **If user provides values**, update the settings.json entry directly
5. **If README is unavailable**, fall back to showing env var names and `source_url` link

#### method == "manual"
No pre-built install config in the index — infer install method from project README. Steps:

**Step 1: Fetch README**
- Construct raw URL from `source_url` (**Note**: Apply GitHub Network Detection rules from SKILL.md to these URLs):
  - Try `https://raw.githubusercontent.com/{owner}/{repo}/main/README.md`
  - If 404, try `master` branch
- If fetch fails, go to Step 3 fallback

**Step 2: Analyze README and generate install config**
Read README content, determine the MCP Server's install method, construct `mcpServers` JSON config:

- **Has existing `mcpServers` JSON** → extract and use directly
- **Has `npx -y <package>` command** → construct `{"command": "npx", "args": ["-y", "<package>"]}`
- **Has `uvx <package>` command** → construct `{"command": "uvx", "args": ["<package>"]}`
- **Has `pip install` + `python -m` startup** → construct `{"command": "python", "args": ["-m", "<module>"]}`
- **Requires env vars (API keys etc.)** → add `"env"` field with empty values or placeholders

After construction:
- Show the generated config to user, explain the inference basis (which part of README)
- On user confirmation, write using `mcp_config` or `mcp_config_template` flow
- If placeholders/env vars present, prompt user to fill them

**Step 3: Fallback (README unavailable or cannot determine install method)**
```
Structure:
  Message: "This MCP requires manual configuration. Please refer to the project docs:"
  Link: source_url
  Instruction: "Follow the README instructions to configure mcpServers."
```

### Skill (type == "skill")
- If `install.repo` exists, execute sparse checkout or clone + copy
- Target: `~/.claude/skills/<id>/`
- If directory already exists, ask whether to overwrite

### Rule (type == "rule")
- Download files from `install.files`
- Default: save to `.claude/rules/<id>.md`; if user chooses "global", save to `~/.claude/rules/<id>.md`
- If .cursorrules format, preserve original text content

### Prompt (type == "prompt")
- Same install logic as Rule
- Save to `.claude/rules/<id>.md`

6. **Post-Install Customization** (skip for MCP type)

After the file is written to disk, offer customization based on resource type. The original file is already saved — customization modifies in place, so the user can always revert.

### Rules / Prompts (passive ask)

**Note**: If the user chose "global" install, warn them that customization will modify the global copy and affect all projects. Suggest they proceed only if the customization is broadly applicable.

Ask the user:
```
"Customize this [rule/prompt] for your project? (Y/n)"
```

- If **Y** → ask: "Describe what to adjust:" and collect the user's instruction, then proceed to **Modification Execution** below
- If **n** → go to step 7

### Skills (active project-fit detection)

**Important**: Skills are installed globally to `~/.claude/skills/<id>/`. Customization modifies this shared copy. If the user uses this skill across multiple projects, warn them that changes will apply everywhere. Suggest they proceed only if the customization is broadly applicable, or note they can manually copy to a project-local path if needed.

Perform automatic project-fit analysis before asking:

**Step A: Gather context**
- Read the installed SKILL.md content (the file just written to `~/.claude/skills/<id>/`)
- Scan the current project directory for signals:
  - `package.json` → Node/frontend stack, dependencies, scripts
  - `pyproject.toml` / `requirements.txt` → Python stack, dependencies
  - `CLAUDE.md` → existing project conventions and instructions
  - Directory structure → `src/`, `app/`, `tests/`, `lib/`, framework-specific folders
- Extract the skill's assumed tech stack and conventions from its content

**Step B: Assess fit**
Compare the skill's assumptions against project signals. Classify into one of four outcomes:

1. **High fit** — skill matches project stack and conventions well
   → Tell the user the skill is a good fit
   → Still ask: "Customize it further for your project? (Y/n)"
2. **Partial mismatch** — skill mostly fits but some sections assume different tools/conventions
   → Tell the user what mismatches were found (e.g., "The skill assumes Jest but your project uses Vitest")
   → Suggest specific adjustments
   → Ask: "Want me to apply these adjustments? (Y/n/edit)"
3. **Severe mismatch** — skill assumes a fundamentally different stack
   → Warn the user about the mismatches
   → Suggest specific adjustments or recommend skipping customization
   → Ask: "Want me to try adapting this skill? (Y/n/edit)"
4. **No signals** — project directory has no recognizable tech stack indicators
   → Ask passively (same as Rules/Prompts flow above)

If the user confirms (Y) or provides edit instructions → proceed to **Modification Execution** below.

### Modification Execution

Apply these guardrails when modifying content:

- **Preserve original structure** — keep the same heading hierarchy, section order, and formatting
- **Only modify relevant sections** — do not touch unrelated rules or instructions
- **Maintain original language and tone** — if the original is in English, keep modifications in English
- **Do not delete content** — adjust or augment, never remove sections wholesale unless the user explicitly asks
- **Skill frontmatter protection** — NEVER modify anything between the opening `---` and closing `---` frontmatter delimiters in skill files. Only modify body content below the frontmatter.

Wrap every modified section with HTML comment markers (except `.cursorrules` format — see below):
```
<!-- [customized]: "brief summary of what was changed and why" -->
(modified content here)
<!-- [/customized] -->
```

These markers:
- Document what was customized and the instruction that drove it
- Allow future tools or users to identify customized sections
- Must wrap the smallest meaningful section that changed (a paragraph, a list, a code block), not the entire file

**Exception**: If the resource was originally in `.cursorrules` format, do NOT insert HTML comment markers — `.cursorrules` files may be parsed by tools that don't support HTML comments. Instead, silently apply the modifications without markers.

### Diff Preview and Confirmation

After generating modifications, present a **semantic summary** (not a line-by-line diff):

```
Structure:
  Section: "Customization Preview"
  Per changed area:
    - "[Section/topic name]: [what changed and why]"
  Example:
    - "Testing conventions: Changed Jest references to Vitest to match your project"
    - "File paths: Updated import paths from src/ to app/ per your project structure"

  Prompt: "Apply changes? (Y/n/edit)"
```

Handle the response:
- **Y** → write the modified content to disk, go to step 7
- **n** → discard modifications, keep original file, go to step 7
- **edit** → ask the user for additional instructions, loop back to **Modification Execution** with the new instructions appended to the original ones

7. After installation (and optional customization), show result and usage instructions (in user's language)

## Error Handling

- If curl fails to fetch index: inform user of network issue and suggest retry
- If writing to target file fails: show permission error
- If resource not found: suggest using `/everything-ai-coding:search` to search
