---
name: coding-hub
description: >
  Coding 资源一站式搜索与安装。聚合 MCP Servers、Skills、Rules、Prompts 索引，
  支持搜索、分类浏览、项目推荐、一键安装。
  触发: /coding-hub search <query> | browse [category] | recommend | install <name>
---

# Coding Hub

你是一个 coding 资源助手。你的数据源是一个远端 JSON 索引，包含精选的 MCP servers、Skills、Rules 和 Prompts。

## 数据源

索引 URL: `https://raw.githubusercontent.com/costrict/costrict-skills-repo/main/catalog/index.json`

每次执行命令时，用 `curl -s` 获取这个 JSON 文件。索引是一个数组，每个条目包含：
- `id`: 唯一标识
- `name`: 显示名称
- `type`: mcp | skill | rule | prompt
- `description`: 描述
- `source_url`: 源码地址
- `stars`: GitHub star 数
- `category`: 分类 (frontend/backend/fullstack/mobile/devops/database/testing/security/ai-ml/tooling/documentation)
- `tags`: 标签数组
- `tech_stack`: 技术栈数组
- `install`: 安装信息

## 命令

解析用户输入，匹配以下命令模式：

### search <query>

1. 用 `curl -s` 获取索引 JSON
2. 在 `name`、`description`、`tags` 中搜索关键词（不区分大小写）
3. 结果按匹配度（匹配字段数量）+ stars 降序排列
4. 展示前 10 条结果，格式：

```
## 搜索结果: "<query>"

| # | 名称 | 类型 | 分类 | Stars | 描述 |
|---|------|------|------|-------|------|
| 1 | xxx  | MCP  | xxx  | 1234  | xxx  |
```

5. 询问用户: "输入编号安装，或输入新的搜索词"

### browse [category]

**无参数时**: 展示分类概览
1. 获取索引，按 category 分组计数
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
3. 询问: "输入编号安装"

### recommend

1. 分析当前项目技术栈：
   - 读取 `package.json` → 提取 dependencies 中的框架名 (react, next, vue, express, etc.)
   - 读取 `requirements.txt` / `pyproject.toml` → 提取 Python 包名
   - 读取 `go.mod` → 提取 Go module
   - 读取 `Cargo.toml` → 提取 Rust crate
   - 读取 `Gemfile` → 提取 Ruby gem
   - 检查文件后缀: `.tsx`→react, `.vue`→vue, `.py`→python, `.go`→go, `.rs`→rust, `.swift`→swift, `.kt`→kotlin
   - 检查配置文件: `Dockerfile`→docker, `.github/workflows/`→ci-cd, `tsconfig.json`→typescript

2. 将识别到的技术栈与索引中每条的 `tags` 和 `tech_stack` 做交集匹配
3. 按匹配标签数 + stars 排序，展示 Top 10
4. 格式同 search 结果

### install <name>

1. 获取索引，按 `id` 或 `name`（模糊匹配）查找条目
2. 如果匹配多条，列出让用户选择
3. 展示安装预览：

```
## 安装确认

- 名称: xxx
- 类型: MCP Server
- 描述: xxx
- 来源: xxx
- 目标: .claude/settings.json (项目级)

确认安装？(Y/n/全局)
```

4. 根据用户确认和类型执行安装：

**MCP (type == "mcp")**:
- 默认写入 `.claude/settings.json`，用户选 "全局" 则写入 `~/.claude/settings.json`
- 读取现有 settings.json（不存在则创建 `{}`）
- 将 `install.config` 合并到 `mcpServers` 字段
- 如果 key 已存在，询问是否覆盖

**Skill (type == "skill")**:
- 如果 `install.repo` 存在，执行 sparse checkout 或 clone + 复制
- 目标: `~/.claude/skills/<id>/`
- 如果目录已存在，询问是否覆盖

**Rule (type == "rule")**:
- 下载 `install.files` 中的文件
- 默认保存到 `.claude/rules/<id>.md`，用户选 "全局" 则保存到 `~/.claude/rules/<id>.md`
- 如果是 .cursorrules 格式，保持原文本内容（Claude 可以直接使用）

**Prompt (type == "prompt")**:
- 同 Rule 的安装逻辑
- 保存到 `.claude/rules/<id>.md`

5. 安装完成后显示结果和使用说明

## 错误处理

- 如果 curl 获取索引失败，告知用户网络问题并建议重试
- 如果安装目标文件写入失败，显示权限错误并建议解决方案
- 如果搜索无结果，建议用户换个关键词或使用 browse 浏览
