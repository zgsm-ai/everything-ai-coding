#Requires -Version 5.1
<#
.SYNOPSIS
    Coding Hub installer for Windows (PowerShell)
.DESCRIPTION
    Usage:
      irm https://raw.githubusercontent.com/zgsm-sangfor/costrict-skills-repo/main/install.ps1 | iex
      # Or with explicit platform:
      & ([scriptblock]::Create((irm https://raw.githubusercontent.com/zgsm-sangfor/costrict-skills-repo/main/install.ps1))) -Platform claude-code
.PARAMETER Platform
    Target platform: claude-code, opencode, costrict, vscode-costrict
    If omitted, auto-detects via environment variables.
#>
param(
    [ValidateSet("claude-code", "opencode", "costrict", "vscode-costrict")]
    [string]$Platform
)

$ErrorActionPreference = "Stop"

$BaseUrl = "https://raw.githubusercontent.com/zgsm-sangfor/costrict-skills-repo/main"
$Commands = @("search", "browse", "recommend", "install", "uninstall", "update")

# --- Auto-detect platform ---

function Detect-Platform {
    if ($env:COSTRICT_CALLER -eq "vscode") { return "vscode-costrict" }
    if ($env:COSTRICT_RUNNING -eq "1")     { return "costrict" }
    if ($env:CLAUDECODE -eq "1")           { return "claude-code" }
    if ($env:OPENCODE -eq "1")             { return "opencode" }
    return ""
}

if (-not $Platform) {
    $Platform = Detect-Platform
    if (-not $Platform) {
        Write-Error @"
ERROR: Could not auto-detect platform.

None of these environment variables were found:
  COSTRICT_CALLER=vscode  -> vscode-costrict
  COSTRICT_RUNNING=1      -> costrict
  CLAUDECODE=1            -> claude-code
  OPENCODE=1              -> opencode

Please specify explicitly:
  & ([scriptblock]::Create((irm $BaseUrl/install.ps1))) -Platform <platform>
"@
        return
    }
    Write-Host "Auto-detected platform: $Platform"
} else {
    Write-Host "Platform: $Platform"
}

# --- Download helper ---

function Download-File {
    param([string]$Url, [string]$Dest)
    try {
        $dir = Split-Path -Parent $Dest
        if ($dir -and -not (Test-Path $dir)) {
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
        }
        Invoke-WebRequest -Uri $Url -OutFile $Dest -UseBasicParsing
    } catch {
        Write-Error "Failed to download $Url : $_"
        return
    }
}

# --- Install per platform ---

function Install-ClaudeCode {
    $skillDir = Join-Path $HOME ".claude/skills/coding-hub"
    New-Item -ItemType Directory -Path $skillDir -Force | Out-Null

    Write-Host "Downloading skill + commands..."
    Download-File "$BaseUrl/platforms/claude-code/skills/coding-hub/SKILL.md" "$skillDir/SKILL.md"
    foreach ($cmd in $Commands) {
        Download-File "$BaseUrl/platforms/claude-code/commands/coding-hub/$cmd.md" "$skillDir/$cmd.md"
    }

    Write-Host ""
    Write-Host "=== Coding Hub installed (Claude Code) ==="
    Write-Host ""
    Write-Host "Skill + commands: $skillDir/"
    Write-Host ""
    Write-Host "Try:  /coding-hub:search typescript"
}

function Install-Opencode {
    $skillDir = Join-Path $HOME ".opencode/skills/coding-hub"
    $cmdDir = Join-Path (Get-Location) ".opencode/command"
    New-Item -ItemType Directory -Path $skillDir -Force | Out-Null
    New-Item -ItemType Directory -Path $cmdDir -Force | Out-Null

    Write-Host "Downloading skill..."
    Download-File "$BaseUrl/platforms/opencode/skills/coding-hub/SKILL.md" "$skillDir/SKILL.md"

    Write-Host "Downloading commands to project dir..."
    foreach ($cmd in $Commands) {
        Download-File "$BaseUrl/platforms/opencode/command/coding-hub-$cmd.md" "$cmdDir/coding-hub-$cmd.md"
    }

    Write-Host ""
    Write-Host "=== Coding Hub installed (Opencode) ==="
    Write-Host ""
    Write-Host "Skill (global): $skillDir/"
    Write-Host "Commands (project): $cmdDir/"
    Write-Host ""
    Write-Host "Note: Commands are installed to the current directory."
    Write-Host "      Run this script again in other projects to add commands there too."
    Write-Host ""
    Write-Host "Try:  /coding-hub-search typescript"
}

function Install-Costrict {
    $skillDir = Join-Path $HOME ".costrict/skills/coding-hub"
    $cmdDir = Join-Path (Get-Location) ".costrict/coding-hub/commands"
    New-Item -ItemType Directory -Path $skillDir -Force | Out-Null
    New-Item -ItemType Directory -Path $cmdDir -Force | Out-Null

    Write-Host "Downloading skill..."
    Download-File "$BaseUrl/platforms/costrict/skills/coding-hub/SKILL.md" "$skillDir/SKILL.md"

    Write-Host "Downloading commands to project dir..."
    foreach ($cmd in $Commands) {
        Download-File "$BaseUrl/platforms/costrict/commands/coding-hub/coding-hub-$cmd.md" "$cmdDir/coding-hub-$cmd.md"
    }

    Write-Host ""
    Write-Host "=== Coding Hub installed (Costrict CLI) ==="
    Write-Host ""
    Write-Host "Skill (global): $skillDir/"
    Write-Host "Commands (project): $cmdDir/"
    Write-Host ""
    Write-Host "Note: Commands are installed to the current directory."
    Write-Host "      Run this script again in other projects to add commands there too."
    Write-Host ""
    Write-Host "Try:  /coding-hub-search typescript"
}

function Install-VscodeCostrict {
    $skillDir = Join-Path $HOME ".costrict/skills/coding-hub"
    New-Item -ItemType Directory -Path $skillDir -Force | Out-Null

    Write-Host "Downloading skill..."
    Download-File "$BaseUrl/platforms/vscode-costrict/skills/coding-hub/SKILL.md" "$skillDir/SKILL.md"

    Write-Host ""
    Write-Host "=== Coding Hub installed (VSCode Costrict) ==="
    Write-Host ""
    Write-Host "Skill: $skillDir/"
    Write-Host ""
    Write-Host "Try:  ask your assistant to 'search typescript with coding-hub'"
}

# --- Main ---

Write-Host ""

switch ($Platform) {
    "claude-code"     { Install-ClaudeCode }
    "opencode"        { Install-Opencode }
    "costrict"        { Install-Costrict }
    "vscode-costrict" { Install-VscodeCostrict }
    default {
        Write-Error "Unknown platform '$Platform'. Valid: claude-code, opencode, costrict, vscode-costrict"
    }
}
