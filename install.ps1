#Requires -Version 5.1
<#
.SYNOPSIS
    Everything AI Coding installer for Windows (PowerShell)
.DESCRIPTION
    Usage:
      irm https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/install.ps1 | iex
      # Or with explicit platform:
      & ([scriptblock]::Create((irm https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/install.ps1))) -Platform claude-code
      # Fork usage:
      & ([scriptblock]::Create((irm https://raw.githubusercontent.com/.../install.ps1))) -Platform claude-code -Repo myorg/my-fork
.PARAMETER Platform
    Target platform: claude-code, opencode, costrict, vscode-costrict
    If omitted, auto-detects via environment variables.
.PARAMETER Repo
    GitHub owner/repo. Defaults to zgsm-ai/everything-ai-coding.
    For forks, specify your own repo to rewrite all data URLs.
#>
param(
    [ValidateSet("claude-code", "opencode", "costrict", "vscode-costrict")]
    [string]$Platform,
    [string]$Repo = "zgsm-ai/everything-ai-coding"
)

$ErrorActionPreference = "Stop"

$DefaultRepo = "zgsm-ai/everything-ai-coding"
$BaseUrl = "https://raw.githubusercontent.com/$Repo/main"
$RepoOwner = $Repo.Split("/")[0]
$RepoName = $Repo.Split("/")[1]
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

if ($Repo -ne $DefaultRepo) {
    Write-Host "Using fork: $Repo"
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

# --- Rewrite repo references for forks ---

function Rewrite-RepoUrls {
    param([string]$FilePath)
    if ($Repo -eq $DefaultRepo) { return }
    $content = Get-Content -Path $FilePath -Raw -Encoding UTF8
    $content = $content -replace "raw\.githubusercontent\.com/zgsm-ai/everything-ai-coding", "raw.githubusercontent.com/$Repo"
    $content = $content -replace "zgsm-ai\.github\.io/everything-ai-coding", "$RepoOwner.github.io/$RepoName"
    $content = $content -replace "github\.com/zgsm-ai/everything-ai-coding", "github.com/$Repo"
    Set-Content -Path $FilePath -Value $content -Encoding UTF8 -NoNewline
}

# --- Install per platform ---

function Install-ClaudeCode {
    $skillDir = Join-Path $HOME ".claude/skills/everything-ai-coding"
    New-Item -ItemType Directory -Path $skillDir -Force | Out-Null

    Write-Host "Downloading skill + commands..."
    Download-File "$BaseUrl/platforms/claude-code/skills/everything-ai-coding/SKILL.md" "$skillDir/SKILL.md"
    Rewrite-RepoUrls "$skillDir/SKILL.md"
    foreach ($cmd in $Commands) {
        Download-File "$BaseUrl/platforms/claude-code/commands/everything-ai-coding/$cmd.md" "$skillDir/$cmd.md"
        Rewrite-RepoUrls "$skillDir/$cmd.md"
    }

    Write-Host ""
    Write-Host "=== Everything AI Coding installed (Claude Code) ==="
    Write-Host ""
    Write-Host "Skill + commands: $skillDir/"
    Write-Host ""
    Write-Host "Try:  /everything-ai-coding:search typescript"
}

function Install-Opencode {
    $skillDir = Join-Path $HOME ".opencode/skills/everything-ai-coding"
    $cmdDir = Join-Path (Get-Location) ".opencode/command"
    New-Item -ItemType Directory -Path $skillDir -Force | Out-Null
    New-Item -ItemType Directory -Path $cmdDir -Force | Out-Null

    Write-Host "Downloading skill..."
    Download-File "$BaseUrl/platforms/opencode/skills/everything-ai-coding/SKILL.md" "$skillDir/SKILL.md"
    Rewrite-RepoUrls "$skillDir/SKILL.md"

    Write-Host "Downloading commands to project dir..."
    foreach ($cmd in $Commands) {
        Download-File "$BaseUrl/platforms/opencode/command/everything-ai-coding-$cmd.md" "$cmdDir/everything-ai-coding-$cmd.md"
        Rewrite-RepoUrls "$cmdDir/everything-ai-coding-$cmd.md"
    }

    Write-Host ""
    Write-Host "=== Everything AI Coding installed (Opencode) ==="
    Write-Host ""
    Write-Host "Skill (global): $skillDir/"
    Write-Host "Commands (project): $cmdDir/"
    Write-Host ""
    Write-Host "Note: Commands are installed to the current directory."
    Write-Host "      Run this script again in other projects to add commands there too."
    Write-Host ""
    Write-Host "Try:  /everything-ai-coding-search typescript"
}

function Install-Costrict {
    $skillDir = Join-Path $HOME ".costrict/skills/everything-ai-coding"
    $cmdDir = Join-Path (Get-Location) ".costrict/everything-ai-coding/commands"
    New-Item -ItemType Directory -Path $skillDir -Force | Out-Null
    New-Item -ItemType Directory -Path $cmdDir -Force | Out-Null

    Write-Host "Downloading skill..."
    Download-File "$BaseUrl/platforms/costrict/skills/everything-ai-coding/SKILL.md" "$skillDir/SKILL.md"
    Rewrite-RepoUrls "$skillDir/SKILL.md"

    Write-Host "Downloading commands to project dir..."
    foreach ($cmd in $Commands) {
        Download-File "$BaseUrl/platforms/costrict/commands/everything-ai-coding/everything-ai-coding-$cmd.md" "$cmdDir/everything-ai-coding-$cmd.md"
        Rewrite-RepoUrls "$cmdDir/everything-ai-coding-$cmd.md"
    }

    Write-Host ""
    Write-Host "=== Everything AI Coding installed (Costrict CLI) ==="
    Write-Host ""
    Write-Host "Skill (global): $skillDir/"
    Write-Host "Commands (project): $cmdDir/"
    Write-Host ""
    Write-Host "Note: Commands are installed to the current directory."
    Write-Host "      Run this script again in other projects to add commands there too."
    Write-Host ""
    Write-Host "Try:  /everything-ai-coding-search typescript"
}

function Install-VscodeCostrict {
    $skillDir = Join-Path $HOME ".costrict/skills/everything-ai-coding"
    $cmdDir = Join-Path $HOME ".roo/commands"
    New-Item -ItemType Directory -Path $skillDir -Force | Out-Null
    New-Item -ItemType Directory -Path $cmdDir -Force | Out-Null

    Write-Host "Downloading skill..."
    Download-File "$BaseUrl/platforms/vscode-costrict/skills/everything-ai-coding/SKILL.md" "$skillDir/SKILL.md"
    Rewrite-RepoUrls "$skillDir/SKILL.md"

    Write-Host "Downloading commands (global)..."
    foreach ($cmd in $Commands) {
        Download-File "$BaseUrl/platforms/vscode-costrict/commands/everything-ai-coding/everything-ai-coding-$cmd.md" "$cmdDir/everything-ai-coding-$cmd.md"
        Rewrite-RepoUrls "$cmdDir/everything-ai-coding-$cmd.md"
    }

    Write-Host ""
    Write-Host "=== Everything AI Coding installed (VSCode Costrict) ==="
    Write-Host ""
    Write-Host "Skill (global): $skillDir/"
    Write-Host "Commands (global): $cmdDir/"
    Write-Host ""
    Write-Host "All projects can now use these slash commands."
    Write-Host ""
    Write-Host "Try:  /everything-ai-coding-search typescript"
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
