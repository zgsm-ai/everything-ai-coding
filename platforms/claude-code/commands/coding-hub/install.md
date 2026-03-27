---
description: '安装指定 coding 资源。用法: /coding-hub:install <name>'
---

# Coding Hub - Install

$ARGUMENTS

---

## 数据源

索引 URL: `https://raw.githubusercontent.com/zgsm-sangfor/costrict-skills-repo/main/catalog/index.json`
本地备用: `/Volumes/Work/Projects/costrict-skills-repo/catalog/index.json`

用 Bash 执行: `curl -s <URL>` 获取 JSON，如果失败则用 Read 读取本地备用路径。

## 执行流程

1. 从 `$ARGUMENTS` 中提取资源名
2. 获取索引，按 `id` 或 `name`（模糊匹配）查找条目
3. 如果匹配多条，列出让用户选择
4. 展示安装预览：

```
## 安装确认

- 名称: xxx
- 类型: MCP Server
- 描述: xxx
- 来源: xxx
- 目标: .claude/settings.json (项目级)

确认安装？(Y/n/全局)
```

5. 根据用户确认和类型执行安装：

### MCP (type == "mcp")
- 默认写入 `.claude/settings.json`，用户选 "全局" 则写入 `~/.claude/settings.json`
- 读取现有 settings.json（不存在则创建 `{}`）
- 根据 `install.method` 分三种情况处理：

#### method == "mcp_config"
- 将 `install.config` 直接合并到 `mcpServers` 字段
- 如果 key 已存在，询问是否覆盖

#### method == "mcp_config_template"
- 将 `install.config` 写入 `mcpServers` 字段
- **安装后提示用户需要替换占位符**，展示 `install.placeholder_hints` 中的每个占位符及说明
- 格式示例：
```
⚠️ 该 MCP 需要配置以下参数才能正常使用：

- FIGMA_API_KEY: Set your FIGMA_API_KEY
- PATH_TO_API_DOT_JSON: Replace with actual path to api dot json

请编辑配置文件替换以上占位符。
```

#### method == "manual"
索引中没有预置安装配置，需要从项目 README 推断安装方式。按以下步骤执行：

**Step 1: 获取 README**
- 从 `source_url` 构造 raw URL 并用 curl 获取：
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
- 用户确认后，按 `mcp_config` 或 `mcp_config_template` 流程写入
- 如果有占位符/环境变量，提示用户填写

**Step 3: 兜底（README 无法获取或无法判断安装方式）**
```
该 MCP 需要手动配置，请参考项目文档：
🔗 https://github.com/xxx/yyy

请按照 README 中的说明配置 mcpServers。
```

### Skill (type == "skill")
- 如果 `install.repo` 存在，执行 sparse checkout 或 clone + 复制
- 目标: `~/.claude/skills/<id>/`
- 如果目录已存在，询问是否覆盖

### Rule (type == "rule")
- 下载 `install.files` 中的文件
- 默认保存到 `.claude/rules/<id>.md`，用户选 "全局" 则保存到 `~/.claude/rules/<id>.md`
- 如果是 .cursorrules 格式，保持原文本内容

### Prompt (type == "prompt")
- 同 Rule 的安装逻辑
- 保存到 `.claude/rules/<id>.md`

6. 安装完成后显示结果和使用说明

## 错误处理

- 如果 curl 获取索引失败，告知用户网络问题并建议重试
- 如果安装目标文件写入失败，显示权限错误
- 如果找不到资源，建议使用 `/coding-hub:search` 搜索
