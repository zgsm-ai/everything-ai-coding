---
description: 'Uninstall an installed coding resource. Usage: /coding-hub:uninstall <name>'
---

# Coding Hub - Uninstall

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

Index URL: `https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/catalog/index.json`
Local fallback: `/Volumes/Work/Projects/costrict-coding-hub/catalog/index.json`

Fetch via Bash: `curl -s <URL>`, on failure use Read on local fallback path.

## Execution Flow

1. Extract resource name from `$ARGUMENTS`
2. Fetch index, look up by `id` or `name` (fuzzy match)
3. If multiple matches, list them and let user choose which to uninstall
4. Detect install status and location:

### MCP (type == "mcp")
- Check project-level `.claude/settings.json` and global `~/.claude/settings.json` for `mcpServers` field
- Find entries matching the resource's `install.config` key
- If found in both levels, let user choose which to uninstall (project / global / all)

### Skill (type == "skill")
- Check if `~/.claude/skills/<id>/` directory exists

### Rule (type == "rule") / Prompt (type == "prompt")
- Check project-level `.claude/rules/<id>.md` and global `~/.claude/rules/<id>.md`
- If found in both levels, let user choose which to uninstall (project / global / all)

5. If resource is not installed (not found in any location), inform user and stop

6. Show uninstall preview (in user's language):

```
Structure:
  Section: "Uninstall Confirmation"
  - Name: xxx
  - Type: MCP Server
  - Location: .claude/settings.json (project-level)

  Prompt: "Confirm uninstall? (Y/n)"
```

7. Execute uninstall on user confirmation, show result

## Error Handling

- If curl fails to fetch index: inform user of network issue and suggest retry
- If resource not found: suggest using `/coding-hub:search` to search
