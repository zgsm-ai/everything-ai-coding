---
description: '更新 coding-hub skill 和子命令到最新版本。用法: /coding-hub-update <name>'
---

# Coding Hub - Update

$ARGUMENTS

从 GitHub 拉取最新版本的 coding-hub skill 和子命令，覆盖本地安装。

## 源地址

基础 URL: `https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main`

## 执行流程

1. **下载最新文件**

   用 Bash 执行以下命令：

   ```bash
   # Skill（全局）— 注意用 $HOME 展开路径
   mkdir -p $HOME/.costrict/skills/coding-hub
   curl -sfL "https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/platforms/vscode-costrict/skills/coding-hub/SKILL.md" -o $HOME/.costrict/skills/coding-hub/SKILL.md

   # 子命令（全局）— 安装到 $HOME/.roo/commands/
   mkdir -p $HOME/.roo/commands
   for cmd in search browse recommend install uninstall update; do
     curl -sfL "https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/platforms/vscode-costrict/commands/coding-hub/coding-hub-${cmd}.md" -o "$HOME/.roo/commands/coding-hub-${cmd}.md"
   done
   ```

2. **报告结果**

   ```
   ## 更新完成

   已从 GitHub 拉取最新版本：

   - $HOME/.costrict/skills/coding-hub/SKILL.md
   - $HOME/.roo/commands/coding-hub-search.md
   - $HOME/.roo/commands/coding-hub-browse.md
   - $HOME/.roo/commands/coding-hub-recommend.md
   - $HOME/.roo/commands/coding-hub-install.md
   - $HOME/.roo/commands/coding-hub-uninstall.md
   - $HOME/.roo/commands/coding-hub-update.md
   ```

## 错误处理

- 如果 curl 下载失败（`-f` 标志会让 curl 在 HTTP 错误如 404/500 时返回非零退出码），提示用户检查网络并重试
- 如果目标目录不存在（未安装过），提示用户先执行安装
