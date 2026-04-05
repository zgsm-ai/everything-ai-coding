---
description: 'Update coding-hub skill and sub-commands to latest version. Usage: /coding-hub-update'
argument-hint: resource name
---

# Coding Hub - Update

$ARGUMENTS

## Language Detection

Determine the output language using the following priority chain (first match wins):

1. **Explicit parameter**: if `$ARGUMENTS` contains `lang:zh` or `lang:en`, use that (strip it from arguments)
2. **Conversation signal**: if the user's recent messages are clearly in one language, follow that
3. **System locale fallback**: run `echo $LANG` in Bash — if the value starts with `zh` (e.g. `zh_CN.UTF-8`), use Chinese; otherwise use English

Once determined, apply consistently:
- **All output** (status messages, file lists, error messages) MUST be in the detected language.

Pull the latest version of coding-hub skill and sub-commands from GitHub, overwriting the local installation.

## Source

Base URL: `https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main`

## Execution Flow

1. **Detect current platform**

   Check in order, use the first match:
   - Check if `~/.claude/skills/coding-hub/SKILL.md` exists → Claude Code
   - If none match, default to Claude Code

2. **Download latest files**

   Run the following Bash commands to download from GitHub and overwrite local files:

   ```bash
   # Skill (global)
   curl -sfL "https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/platforms/claude-code/skills/coding-hub/SKILL.md" -o ~/.claude/skills/coding-hub/SKILL.md

   # Sub-commands (project-level)
   mkdir -p .claude/commands/coding-hub/
   for cmd in search browse recommend install uninstall update; do
     curl -sfL "https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/platforms/claude-code/commands/coding-hub/${cmd}.md" -o ".claude/commands/coding-hub/${cmd}.md"
   done
   ```

3. **Report result** (in user's language)

   Show which files were updated:

   ```
   Structure:
     Section: "Update Complete"
     Message: "Pulled latest version from GitHub:"
     File list:
       - ~/.claude/skills/coding-hub/SKILL.md
       - .claude/commands/coding-hub/search.md
       - .claude/commands/coding-hub/browse.md
       - .claude/commands/coding-hub/recommend.md
       - .claude/commands/coding-hub/install.md
       - .claude/commands/coding-hub/uninstall.md
       - .claude/commands/coding-hub/update.md
   ```

## Error Handling

- If curl download fails (network issue or HTTP error like 404/500): prompt user to check network and retry
- If target directory does not exist (never installed before): prompt user to install first
