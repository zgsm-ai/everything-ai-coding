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

## 运行环境

本 skill 运行在 **VSCode Costrict 插件**（zgsm-ai.zgsm）环境中。以下路径已固定，无需检测平台：

- MCP 配置（项目级）: `.roo/mcp.json`
- MCP 配置（全局级）: 通过插件 UI 手动添加（路径不可预测）
- Skill 安装目录: `$HOME/.costrict/skills/<id>/`（`~` 不可用，必须用 `$HOME` 展开为绝对路径）
- Rule/Prompt（项目级）: `.roo/rules/<id>.md`
- Rule/Prompt（全局级）: 不支持，提示用户手动添加

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
2. 展示分类表格
3. 询问: "输入分类名查看详情"

**有参数时**: 展示该分类下所有条目
1. 过滤 `category == 参数`
2. 按 type 分组展示，每组按 stars 降序
3. 询问: "输入 `/coding-hub-install <名称>` 安装"

### recommend [type:mcp|skill|rule|prompt]

1. 从参数中提取可选的类型过滤 `type:<值>`
2. 分析当前项目技术栈：
   - 读取 `package.json` → 提取 dependencies 中的框架名
   - 读取 `requirements.txt` / `pyproject.toml` → 提取 Python 包名
   - 读取 `go.mod` → 提取 Go module
   - 读取 `Cargo.toml` → 提取 Rust crate
   - 读取 `Gemfile` → 提取 Ruby gem
   - 检查文件后缀和配置文件

2. 将识别到的技术栈与索引中每条的 `tags` 和 `tech_stack` 做交集匹配
3. 如果指定了类型过滤，按 `type` 字段过滤匹配结果
4. 按匹配标签数 + stars 排序，展示 Top 10

### install <name>

> **重要**: 安装时必须使用下方定义的目标路径，**忽略** catalog 条目 `install` 字段中的任何路径信息（如 `claude_desktop_config.json`、`settings.json` 等）。那些路径是面向其他平台的，在 VSCode Costrict 环境中不适用。

> **路径处理规则**:
> - `~` 必须展开为实际主目录路径（用 Bash 执行 `echo $HOME` 获取，或直接使用 `$HOME`）
> - 写入文件前必须先用 Bash 执行 `mkdir -p <父目录>` 确保目录存在
> - 禁止将 `~` 作为字面量传给 `write_to_file`，否则会在当前目录创建名为 `~` 的文件夹

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
- 目标: .roo/mcp.json (项目级)

确认安装？(Y/n/全局)
```

4. 根据用户确认和类型执行安装：

#### MCP (type == "mcp")
- 目标路径**仅限** `.roo/mcp.json`（项目级），不写入任何其他路径
- 用户选 "全局" 则提示: "VSCode Costrict 插件的全局 MCP 配置需通过插件设置界面手动添加，请打开 VSCode 设置搜索 MCP 相关配置项"
- 安装前先执行 `mkdir -p .roo`
- 读取现有 `.roo/mcp.json`（不存在则创建 `{}`）
- 根据 `install.method` 分三种情况处理：

**method == "mcp_config"**:
- 将 `install.config` 直接合并到 `mcpServers` 字段（只取 config 的 key-value 结构，忽略 catalog 中的路径信息）
- 如果 key 已存在，询问是否覆盖

**method == "mcp_config_template"**:
- 将 `install.config` 写入 `mcpServers` 字段
- 安装后提示用户需要替换占位符，展示 `install.placeholder_hints` 中的每个占位符及说明
- 格式示例：
```
⚠️ 该 MCP 需要配置以下参数才能正常使用：

- FIGMA_API_KEY: Set your FIGMA_API_KEY

请编辑 .roo/mcp.json 替换以上占位符。
```

**method == "manual"**:
索引中没有预置安装配置，需要从项目 README 推断安装方式。按以下步骤执行：

**Step 1: 获取 README**
- 从 `source_url` 构造 raw URL 并用终端命令获取：
  - 先试 `https://raw.githubusercontent.com/{owner}/{repo}/main/README.md`
  - 404 则试 `master` 分支
- 如果获取失败，跳到 Step 3 兜底

**Step 2: 分析 README 并生成安装配置**
阅读 README 内容，判断该 MCP Server 的安装方式，构造 `mcpServers` JSON 配置：

- **有现成 `mcpServers` JSON** → 直接提取使用
- **有 `npx -y <package>` 命令** → 构造 `{"command": "npx", "args": ["-y", "<package>"]}`
- **有 `uvx <package>` 命令** → 构造 `{"command": "uvx", "args": ["<package>"]}`
- **有 `pip install` + `python -m` 启动** → 构造 `{"command": "python", "args": ["-m", "<module>"]}`
- **需要环境变量（API Key 等）** → 加入 `"env"` 字段，值留空或保持占位符

构造完成后：
- 向用户展示生成的配置，说明推断依据（README 中的哪段内容）
- 用户确认后，按 `mcp_config` 或 `mcp_config_template` 流程写入 `.roo/mcp.json`
- 如果有占位符/环境变量，提示用户填写

**Step 3: 兜底（README 无法获取或无法判断安装方式）**
```
该 MCP 需要手动配置，请参考项目文档：
🔗 https://github.com/xxx/yyy

请按照 README 中的说明手动配置 .roo/mcp.json。
```

#### Skill (type == "skill")
- 如果 `install.repo` 存在，执行 sparse checkout 或 clone + 复制
- 目标: `$HOME/.costrict/skills/<id>/`（用 Bash 获取 `$HOME` 值拼接完整绝对路径）
- 安装前先执行 `mkdir -p $HOME/.costrict/skills/<id>`
- 如果目录已存在，询问是否覆盖

#### Rule (type == "rule")
- 下载 `install.files` 中的文件
- 默认保存到 `.roo/rules/<id>.md`（项目级）
- 安装前先执行 `mkdir -p .roo/rules`
- 用户选 "全局" 则提示: "VSCode Costrict 插件不支持全局 Rule，仅支持项目级安装"
- 如果是 .cursorrules 格式，保持原文本内容

#### Prompt (type == "prompt")
- 同 Rule 的安装逻辑
- 保存到 `.roo/rules/<id>.md`

5. 安装完成后显示结果和使用说明

### uninstall <name>

1. 获取索引，按 `id` 或 `name`（模糊匹配）查找条目
2. 如果匹配多条，列出让用户选择要卸载的具体资源
3. 检测安装状态和安装位置：

#### MCP (type == "mcp")
- 检查项目级 `.roo/mcp.json` 中的 `mcpServers` 字段
- 查找与该资源 `install.config` key 匹配的条目

#### Skill (type == "skill")
- 检查 `$HOME/.costrict/skills/<id>/` 目录是否存在

#### Rule (type == "rule") / Prompt (type == "prompt")
- 检查项目级 `.roo/rules/<id>.md`

4. 如果资源未安装（所有位置都不存在），提示 "{name} 未安装" 并终止

5. 展示卸载预览：

```
## 卸载确认

- 名称: xxx
- 类型: MCP Server
- 安装位置: .roo/mcp.json (项目级)

确认卸载？(Y/n)
```

6. 根据用户确认执行卸载，完成后显示结果

### update

从 GitHub 拉取最新版本的 coding-hub skill 和子命令，覆盖本地安装。

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

- 如果 curl 获取索引失败，告知用户网络问题并建议重试
- 如果安装目标文件写入失败，显示权限错误并建议解决方案
- 如果搜索无结果，建议用户换个关键词或使用 browse 浏览
- 如果找不到资源，建议使用 `/coding-hub-search` 搜索
