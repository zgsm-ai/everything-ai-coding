---
description: '更新 coding-hub skill 和子命令到最新版本。用法: /coding-hub-update <name>'
argument-hint: <name>
---

# Coding Hub - Update

$ARGUMENTS

从 GitHub 拉取最新版本的 coding-hub skill 和子命令，覆盖本地安装。

## 源地址

基础 URL: `https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main`

## 执行流程

1. **检测当前平台**

   按以下顺序检测，使用第一个匹配的平台：
   - 检查 `~/.costrict/skills/coding-hub/SKILL.md` 是否存在 → Costrict
   - 如果都不存在，默认使用 Costrict

2. **下载最新文件**

   用 Bash 执行以下命令，从 GitHub 下载文件并覆盖本地：

   ```bash
   # Skill（全局）
   curl -sfL "https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/platforms/costrict/skills/coding-hub/SKILL.md" -o ~/.costrict/skills/coding-hub/SKILL.md

   # 子命令（项目级）
   mkdir -p .costrict/coding-hub/commands/
   for cmd in search browse recommend install uninstall update; do
     curl -sfL "https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/platforms/costrict/commands/coding-hub/coding-hub-${cmd}.md" -o ".costrict/coding-hub/commands/coding-hub-${cmd}.md"
   done
   ```

3. **报告结果**

   展示更新了哪些文件：

   ```
   ## 更新完成

   已从 GitHub 拉取最新版本：

   - ~/.costrict/skills/coding-hub/SKILL.md
   - .costrict/coding-hub/commands/coding-hub-search.md
   - .costrict/coding-hub/commands/coding-hub-browse.md
   - .costrict/coding-hub/commands/coding-hub-recommend.md
   - .costrict/coding-hub/commands/coding-hub-install.md
   - .costrict/coding-hub/commands/coding-hub-uninstall.md
   - .costrict/coding-hub/commands/coding-hub-update.md
   ```

## 错误处理

- 如果 curl 下载失败（`-f` 标志会让 curl 在 HTTP 错误如 404/500 时返回非零退出码），提示用户检查网络并重试
- 如果目标目录不存在（未安装过），提示用户先执行安装
