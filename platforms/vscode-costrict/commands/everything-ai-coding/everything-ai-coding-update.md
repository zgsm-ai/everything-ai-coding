---
description: 'Update everything-ai-coding skill and sub-commands to latest version. Usage: /everything-ai-coding-update'
argument-hint: resource name
---

# Everything AI Coding - Update

$ARGUMENTS

## Language Detection

Determine the output language using the following priority chain (first match wins):

1. **Explicit parameter**: if `$ARGUMENTS` contains `lang:zh` or `lang:en`, use that (strip it from arguments)
2. **Conversation signal**: if the user's recent messages are clearly in one language, follow that
3. **System locale fallback**: run `echo $LANG` in Bash — if the value starts with `zh` (e.g. `zh_CN.UTF-8`), use Chinese; otherwise use English

Once determined, apply consistently:
- **All output** (status messages, file lists, error messages) MUST be in the detected language.

Pull the latest version of everything-ai-coding skill and sub-commands from GitHub, overwriting the local installation.

## Source

**Note**: Apply GitHub Network Detection rules (see SKILL.md) to all GitHub URLs below. If `[network-config]` specifies a proxy, rewrite URLs accordingly.

Base URL: `https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main`

## Execution Flow

1. **Detect current platform**

   Check in order, use the first match:
   - Check if `$HOME/.costrict/skills/everything-ai-coding/SKILL.md` exists → VSCode Costrict
   - If none match, default to VSCode Costrict

2. **Download latest files**

   Run the following Bash commands to download from GitHub and overwrite local files:

   ```bash
   # Skill (global) — use $HOME to expand path
   mkdir -p $HOME/.costrict/skills/everything-ai-coding
   curl -sfL "https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/platforms/vscode-costrict/skills/everything-ai-coding/SKILL.md" -o $HOME/.costrict/skills/everything-ai-coding/SKILL.md

   # Sub-commands (global) — install to $HOME/.roo/commands/
   mkdir -p $HOME/.roo/commands
   for cmd in search browse recommend install uninstall update; do
     curl -sfL "https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/platforms/vscode-costrict/commands/everything-ai-coding/everything-ai-coding-${cmd}.md" -o "$HOME/.roo/commands/everything-ai-coding-${cmd}.md"
   done
   ```

3. **Report result** (in user's language)

   Show which files were updated:

   ```
   Structure:
     Section: "Update Complete"
     Message: "Pulled latest version from GitHub:"
     File list:
       - $HOME/.costrict/skills/everything-ai-coding/SKILL.md
       - $HOME/.roo/commands/everything-ai-coding-search.md
       - $HOME/.roo/commands/everything-ai-coding-browse.md
       - $HOME/.roo/commands/everything-ai-coding-recommend.md
       - $HOME/.roo/commands/everything-ai-coding-install.md
       - $HOME/.roo/commands/everything-ai-coding-uninstall.md
       - $HOME/.roo/commands/everything-ai-coding-update.md
   ```

4. **Reset network detection**: After SKILL.md is re-downloaded, delete the `[network-config]` marker at the end of the old file if it was preserved, so a fresh network probe runs on the next session.

## Error Handling

- If curl download fails (network issue or HTTP error like 404/500): prompt user to check network and retry
- If target directory does not exist (never installed before): prompt user to install first
