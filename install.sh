#!/usr/bin/env bash
set -euo pipefail

# Everything AI Coding installer
# Usage:
#   curl -fsSL .../install.sh | bash -s -- --platform <platform>   (explicit)
#   curl -fsSL .../install.sh | bash                                (auto-detect)
#
# Platforms: claude-code, opencode, costrict, vscode-costrict

DEFAULT_REPO="zgsm-ai/everything-ai-coding"
REPO="$DEFAULT_REPO"
COMMANDS="search browse recommend install uninstall update"

# --- Auto-detect platform via process-injected env vars ---
# These variables are set by each platform's process, NOT by shell profile.
# Priority: VSCode Costrict > Costrict CLI > Claude Code > Opencode

detect_platform() {
  if [ "${COSTRICT_CALLER:-}" = "vscode" ]; then
    echo "vscode-costrict"
  elif [ "${COSTRICT_RUNNING:-}" = "1" ]; then
    echo "costrict"
  elif [ "${CLAUDECODE:-}" = "1" ]; then
    echo "claude-code"
  elif [ "${OPENCODE:-}" = "1" ]; then
    echo "opencode"
  else
    echo ""
  fi
}

# --- Parse arguments ---

PLATFORM=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --platform|-p)
      PLATFORM="$2"
      shift 2
      ;;
    --repo|-r)
      REPO="$2"
      shift 2
      ;;
    claude-code|opencode|costrict|vscode-costrict)
      PLATFORM="$1"
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      echo "" >&2
      echo "Usage: bash install.sh [--platform <platform>] [--repo <owner/repo>]" >&2
      echo "Platforms: claude-code, opencode, costrict, vscode-costrict" >&2
      echo "Omit --platform to auto-detect via environment variables." >&2
      echo "Omit --repo to use the default ($DEFAULT_REPO)." >&2
      exit 1
      ;;
  esac
done

# Derive URLs from repo
BASE_URL="https://raw.githubusercontent.com/${REPO}/main"
REPO_OWNER="${REPO%%/*}"
REPO_NAME="${REPO##*/}"

# Auto-detect if no --platform provided
if [ -z "$PLATFORM" ]; then
  PLATFORM=$(detect_platform)
  if [ -z "$PLATFORM" ]; then
    echo "ERROR: Could not auto-detect platform." >&2
    echo "" >&2
    echo "None of these environment variables were found:" >&2
    echo "  COSTRICT_CALLER=vscode  → vscode-costrict" >&2
    echo "  COSTRICT_RUNNING=1      → costrict" >&2
    echo "  CLAUDECODE=1            → claude-code" >&2
    echo "  OPENCODE=1              → opencode" >&2
    echo "" >&2
    echo "Please specify explicitly:" >&2
    echo "  curl -fsSL .../install.sh | bash -s -- --platform <platform>" >&2
    exit 1
  fi
  echo "Auto-detected platform: $PLATFORM"
else
  echo "Platform: $PLATFORM"
fi

# --- Resolve home directory (WSL-aware) ---
# In WSL, $HOME is /home/user but VSCode extensions expect %USERPROFILE% on the Windows side.
# This function returns the Windows USERPROFILE path (translated to WSL mount) when in WSL,
# or $HOME otherwise.

resolve_home() {
  if grep -qi microsoft /proc/version 2>/dev/null; then
    local win_home
    win_home=$(cmd.exe /c "echo %USERPROFILE%" 2>/dev/null | tr -d '\r')
    if [ -n "$win_home" ]; then
      wslpath -u "$win_home"
      return
    fi
    echo "WARNING: WSL detected but could not resolve Windows USERPROFILE. Falling back to \$HOME." >&2
  fi
  echo "$HOME"
}

# --- Download helper ---

download() {
  local url="$1" dest="$2"
  if ! curl -fsSL "$url" -o "$dest"; then
    echo "ERROR: Failed to download $url" >&2
    exit 1
  fi
}

# --- Rewrite repo references for forks ---

rewrite_repo_urls() {
  local file="$1"
  if [ "$REPO" = "$DEFAULT_REPO" ]; then
    return  # No rewriting needed for the default repo
  fi
  # Replace raw.githubusercontent.com paths
  sed -i.bak "s|raw\.githubusercontent\.com/zgsm-ai/everything-ai-coding|raw.githubusercontent.com/${REPO}|g" "$file"
  # Replace GitHub Pages URL: zgsm-ai.github.io/everything-ai-coding → owner.github.io/repo
  sed -i.bak "s|zgsm-ai\.github\.io/everything-ai-coding|${REPO_OWNER}.github.io/${REPO_NAME}|g" "$file"
  # Replace github.com repo references
  sed -i.bak "s|github\.com/zgsm-ai/everything-ai-coding|github.com/${REPO}|g" "$file"
  rm -f "${file}.bak"
}

# --- Install per platform ---
# SKILL.md → global skills dir (always available)
# Commands → project-level dir (CWD) for opencode/costrict (they only load commands from project dir)
# Claude Code is special: it loads sub .md files from skills dir as slash commands, so all-global works.

install_claude_code() {
  local skill_dir="$HOME/.claude/skills/everything-ai-coding"
  local cmd_dir="$HOME/.claude/commands/everything-ai-coding"
  mkdir -p "$skill_dir" "$cmd_dir"

  echo "Downloading skill..."
  download "$BASE_URL/platforms/claude-code/skills/everything-ai-coding/SKILL.md" "$skill_dir/SKILL.md"
  rewrite_repo_urls "$skill_dir/SKILL.md"

  echo "Downloading commands..."
  for cmd in $COMMANDS; do
    download "$BASE_URL/platforms/claude-code/commands/everything-ai-coding/${cmd}.md" "$cmd_dir/${cmd}.md"
    rewrite_repo_urls "$cmd_dir/${cmd}.md"
  done

  echo ""
  echo "=== Everything AI Coding installed (Claude Code) ==="
  echo ""
  echo "Skill:    $skill_dir/"
  echo "Commands: $cmd_dir/"
  echo ""
  echo "Try:  /everything-ai-coding:search typescript"
}

install_opencode() {
  local skill_dir="$HOME/.opencode/skills/everything-ai-coding"
  local cmd_dir=".opencode/command"
  mkdir -p "$skill_dir" "$cmd_dir"

  echo "Downloading skill..."
  download "$BASE_URL/platforms/opencode/skills/everything-ai-coding/SKILL.md" "$skill_dir/SKILL.md"
  rewrite_repo_urls "$skill_dir/SKILL.md"

  echo "Downloading commands to project dir..."
  for cmd in $COMMANDS; do
    download "$BASE_URL/platforms/opencode/command/everything-ai-coding-${cmd}.md" "$cmd_dir/everything-ai-coding-${cmd}.md"
    rewrite_repo_urls "$cmd_dir/everything-ai-coding-${cmd}.md"
  done

  echo ""
  echo "=== Everything AI Coding installed (Opencode) ==="
  echo ""
  echo "Skill (global): $skill_dir/"
  echo "Commands (project): $(pwd)/$cmd_dir/"
  echo ""
  echo "Note: Commands are installed to the current directory."
  echo "      Run this script again in other projects to add commands there too."
  echo ""
  echo "Try:  /everything-ai-coding-search typescript"
}

install_costrict() {
  local skill_dir="$HOME/.costrict/skills/everything-ai-coding"
  local cmd_dir=".costrict/everything-ai-coding/commands"
  mkdir -p "$skill_dir" "$cmd_dir"

  echo "Downloading skill..."
  download "$BASE_URL/platforms/costrict/skills/everything-ai-coding/SKILL.md" "$skill_dir/SKILL.md"
  rewrite_repo_urls "$skill_dir/SKILL.md"

  echo "Downloading commands to project dir..."
  for cmd in $COMMANDS; do
    download "$BASE_URL/platforms/costrict/commands/everything-ai-coding/everything-ai-coding-${cmd}.md" "$cmd_dir/everything-ai-coding-${cmd}.md"
    rewrite_repo_urls "$cmd_dir/everything-ai-coding-${cmd}.md"
  done

  echo ""
  echo "=== Everything AI Coding installed (Costrict CLI) ==="
  echo ""
  echo "Skill (global): $skill_dir/"
  echo "Commands (project): $(pwd)/$cmd_dir/"
  echo ""
  echo "Note: Commands are installed to the current directory."
  echo "      Run this script again in other projects to add commands there too."
  echo ""
  echo "Try:  /everything-ai-coding-search typescript"
}

install_vscode_costrict() {
  local home_dir
  home_dir=$(resolve_home)
  local skill_dir="$home_dir/.costrict/skills/everything-ai-coding"
  local cmd_dir="$home_dir/.roo/commands"
  mkdir -p "$skill_dir" "$cmd_dir"

  echo "Downloading skill..."
  download "$BASE_URL/platforms/vscode-costrict/skills/everything-ai-coding/SKILL.md" "$skill_dir/SKILL.md"
  rewrite_repo_urls "$skill_dir/SKILL.md"

  echo "Downloading commands (global)..."
  for cmd in $COMMANDS; do
    download "$BASE_URL/platforms/vscode-costrict/commands/everything-ai-coding/everything-ai-coding-${cmd}.md" "$cmd_dir/everything-ai-coding-${cmd}.md"
    rewrite_repo_urls "$cmd_dir/everything-ai-coding-${cmd}.md"
  done

  echo ""
  echo "=== Everything AI Coding installed (VSCode Costrict / Roo Code) ==="
  echo ""
  echo "Skill (global): $skill_dir/"
  echo "Commands (global): $cmd_dir/"
  echo ""
  echo "All projects can now use these slash commands."
  echo ""
  echo "Try:  /everything-ai-coding-search typescript"
}

# --- Main ---

echo ""

case "$PLATFORM" in
  claude-code)       install_claude_code ;;
  opencode)          install_opencode ;;
  costrict)          install_costrict ;;
  vscode-costrict)   install_vscode_costrict ;;
  *)
    echo "ERROR: Unknown platform '$PLATFORM'" >&2
    echo "Valid platforms: claude-code, opencode, costrict, vscode-costrict" >&2
    exit 1
    ;;
esac
