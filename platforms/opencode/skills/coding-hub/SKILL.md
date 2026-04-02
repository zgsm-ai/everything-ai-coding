---
name: coding-hub
description: >
  Coding 资源一站式搜索与安装。聚合 MCP Servers、Skills、Rules、Prompts 索引，
  支持搜索、分类浏览、项目推荐、一键安装。
  触发: /coding-hub-search <query> | /coding-hub-browse [category] | /coding-hub-recommend | /coding-hub-install <name> | /coding-hub-uninstall <name> | /coding-hub-update <name>
license: MIT
metadata:
  author: costrict
  version: "1.0"
---

# Coding Hub

你是一个 coding 资源助手。你的数据源是一个远端 JSON 索引，包含精选的 MCP servers、Skills、Rules 和 Prompts。

## 平台检测

首次执行任何命令前，先检测当前运行平台。按以下顺序检查，使用第一个匹配的结果：

1. 检查当前项目目录或 `~/` 下是否存在 `.costrict/` → **Costrict**（配置目录: `.costrict/`，命令分隔符: `-`）
2. 检查是否存在 `.opencode/` → **Opencode**（配置目录: `.opencode/`，命令分隔符: `-`）
3. 默认 → **Claude Code**（配置目录: `.claude/`，命令分隔符: `:`）

检测结果在本次会话中记住，后续命令不再重复检测。以下所有路径中的 `.opencode/` 自动替换为检测到的平台配置目录。

## 数据源

### 搜索/浏览/推荐用轻量搜索索引（~2MB）

搜索索引 URL: `https://zgsm-sangfor.github.io/costrict-coding-hub/api/v1/search-index.json`
Fallback URL: `https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/catalog/search-index.json`

### 安装用单条 API（~1-2KB）

单条 API: `https://zgsm-sangfor.github.io/costrict-coding-hub/api/v1/{type}/{id}.json`
全量索引 (fallback): `https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/catalog/index.json`

搜索索引是一个数组，每个条目包含：
- `id`: 唯一标识
- `name`: 显示名称
- `type`: mcp | skill | rule | prompt
- `description`: 描述
- `source_url`: 源码地址
- `stars`: GitHub star 数
- `category`: 分类 (frontend/backend/fullstack/mobile/devops/database/testing/security/ai-ml/tooling/documentation)
- `tags`: 标签数组
- `tech_stack`: 技术栈数组

单条 API 返回完整条目数据，额外包含 `install` 安装信息。

**重要：数据预过滤策略**
索引文件有 3900+ 条目，禁止将全量 JSON 读入上下文。
执行 search/browse/recommend 时，必须用 Bash 调用 python 脚本在 shell 侧完成过滤，
只将过滤后的 top N 结果（纯文本）送入上下文进行格式化展示。
Python 命令跨平台探测: `$(command -v python3 || command -v python)`

## 命令

解析用户输入，匹配以下命令模式：

### search <query> [type:mcp|skill|rule|prompt]

1. 用 `curl -s` 获取索引 JSON
2. 从参数中提取可选的类型过滤 `type:<值>`，剩余部分作为搜索关键词
   - 示例: `search typescript type:mcp` — 只搜索 MCP 类型
3. 如果指定了类型过滤，先按 `type` 字段过滤索引
4. 在 `name`、`description`、`tags` 中搜索关键词（不区分大小写）
5. 结果按匹配度（匹配字段数量）+ stars 降序排列
6. 展示前 10 条结果，格式：

```
## 搜索结果: "<query>"

| # | 名称 | 类型 | 分类 | Stars | 描述 |
|---|------|------|------|-------|------|
| 1 | xxx  | MCP  | xxx  | 1234  | xxx  |
```

5. 询问用户: "输入 `/coding-hub-install <名称>` 安装，或输入新的搜索词"

### browse [category] [type:mcp|skill|rule|prompt]

**无参数时**: 展示分类概览
1. 获取索引，如果指定了 `type:` 过滤则先按 type 过滤
2. 按 category 分组计数
2. 展示：

```
## 资源分类

| 分类 | 数量 | 描述 |
|------|------|------|
| frontend | 42 | 前端框架与工具 |
| backend | 38 | 后端框架与语言 |
...
```

3. 询问: "输入分类名查看详情"

**有参数时**: 展示该分类下所有条目
1. 过滤 `category == 参数`
2. 按 type 分组展示，每组按 stars 降序
3. 询问: "输入 `/coding-hub-install <名称>` 安装"

### recommend [type:mcp|skill|rule|prompt]

1. 从参数中提取可选的类型过滤 `type:<值>`
2. 分析当前项目技术栈：
   - 读取 `package.json` → 提取 dependencies 中的框架名 (react, next, vue, express, etc.)
   - 读取 `requirements.txt` / `pyproject.toml` → 提取 Python 包名
   - 读取 `go.mod` → 提取 Go module
   - 读取 `Cargo.toml` → 提取 Rust crate
   - 读取 `Gemfile` → 提取 Ruby gem
   - 检查文件后缀: `.tsx`→react, `.vue`→vue, `.py`→python, `.go`→go, `.rs`→rust, `.swift`→swift, `.kt`→kotlin
   - 检查配置文件: `Dockerfile`→docker, `.github/workflows/`→ci-cd, `tsconfig.json`→typescript

2. 将识别到的技术栈与索引中每条的 `tags` 和 `tech_stack` 做交集匹配
3. 如果指定了类型过滤，按 `type` 字段过滤匹配结果
4. 按匹配标签数 + stars 排序，展示 Top 10
4. 格式同 search 结果

### install <name>

1. 先用搜索索引按 `id` 或 `name`（模糊匹配）定位条目，获取 `type` 和 `id`
2. 如果匹配多条，列出让用户选择
3. 用单条 API 获取完整数据: `curl -sf "https://zgsm-sangfor.github.io/costrict-coding-hub/api/v1/{type}/{id}.json"`
   - 如果失败，fallback 到全量索引: `curl -sf "https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/catalog/index.json"` 并从中筛选
4. 展示安装预览：

```
## 安装确认

- 名称: xxx
- 类型: MCP Server
- 描述: xxx
- 来源: xxx
- 目标: .opencode/settings.json (项目级)

确认安装？(Y/n/全局)
```

4. 根据用户确认和类型执行安装：

**MCP (type == "mcp")**:
- 默认写入 `.opencode/settings.json`，用户选 "全局" 则写入 `~/.opencode/settings.json`
- 读取现有 settings.json（不存在则创建 `{}`）
- 将 `install.config` 合并到 `mcpServers` 字段
- 如果 key 已存在，询问是否覆盖

**Skill (type == "skill")**:
- 如果 `install.repo` 存在，执行 sparse checkout 或 clone + 复制
- 目标: `~/.opencode/skills/<id>/`
- 如果目录已存在，询问是否覆盖

**Rule (type == "rule")**:
- 下载 `install.files` 中的文件
- 默认保存到 `.opencode/rules/<id>.md`，用户选 "全局" 则保存到 `~/.opencode/rules/<id>.md`
- 如果是 .cursorrules 格式，保持原文本内容（Claude 可以直接使用）

**Prompt (type == "prompt")**:
- 同 Rule 的安装逻辑
- 保存到 `.opencode/rules/<id>.md`

5. 安装完成后显示结果和使用说明

### uninstall <name>

1. 获取索引，按 `id` 或 `name`（模糊匹配）查找条目
2. 如果匹配多条，列出让用户选择要卸载的具体资源
3. 检测安装状态和安装位置：

**MCP (type == "mcp")**:
- 检查项目级 `.opencode/settings.json` 和全局 `~/.opencode/settings.json` 中的 `mcpServers` 字段
- 查找与该资源 `install.config` key 匹配的条目
- 如果两个层级都存在，列出两个安装位置，让用户选择卸载哪个（项目级/全局/全部）

**Skill (type == "skill")**:
- 检查 `~/.opencode/skills/<id>/` 目录是否存在

**Rule (type == "rule") / Prompt (type == "prompt")**:
- 检查项目级 `.opencode/rules/<id>.md` 和全局 `~/.opencode/rules/<id>.md`
- 如果两个层级都存在，让用户选择卸载哪个（项目级/全局/全部）

4. 如果资源未安装（所有位置都不存在），提示 "{name} is not installed" 并终止

5. 展示卸载预览并执行

## 错误处理

- 如果 curl 获取索引失败，告知用户网络问题并建议重试
- 如果安装目标文件写入失败，显示权限错误并建议解决方案
- 如果搜索无结果，建议用户换个关键词或使用 browse 浏览
