---
description: '基于当前项目技术栈推荐 coding 资源。用法: /coding-hub-recommend [type:mcp|skill|rule|prompt]'
---

# Coding Hub - Recommend

$ARGUMENTS

---

## 数据处理（重要：用 Bash 预过滤，避免全量 JSON 进入上下文）

索引 URL: `https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/catalog/search-index.json`

## 执行流程

1. 从 `$ARGUMENTS` 中提取可选的类型过滤参数
   - 支持 `type:mcp`、`type:skill`、`type:rule`、`type:prompt` 过滤
   - 示例: `/coding-hub-recommend type:mcp` — 只推荐 MCP 类型
   - 如果参数中包含 `type:<值>`，提取为过滤条件
2. 分析当前项目技术栈：
   - 读取 `package.json` → 提取 dependencies 中的框架名 (react, next, vue, express, etc.)
   - 读取 `requirements.txt` / `pyproject.toml` → 提取 Python 包名
   - 读取 `go.mod` → 提取 Go module
   - 读取 `Cargo.toml` → 提取 Rust crate
   - 读取 `Gemfile` → 提取 Ruby gem
   - 检查文件后缀: `.tsx`→react, `.vue`→vue, `.py`→python, `.go`→go, `.rs`→rust, `.swift`→swift, `.kt`→kotlin
   - 检查配置文件: `Dockerfile`→docker, `.github/workflows/`→ci-cd, `tsconfig.json`→typescript
3. 下载索引到临时文件: `curl -s <URL> -o "$TMPDIR/coding-hub-index.json"`
4. 用 python 脚本预过滤（跨平台：macOS/Linux 用 python3，Windows 用 python，探测命令 `$(command -v python3 || command -v python)`）:
   - 读取 JSON 文件
   - 将检测到的项目 tags 与每条的 `tags` + `tech_stack` 做交集匹配
   - 如果指定了 type 过滤，先按 type 字段过滤
   - 按匹配标签数 + stars 降序排序
   - 输出 top 10，每行格式: `name\ttype\tmatched_tags\tstars\tdescription`（TSV 纯文本）
5. 将 bash 输出的 TSV 结果格式化为表格展示给用户

## 输出格式

```
## 项目推荐

检测到技术栈: Python, FastAPI, Docker, PostgreSQL

| # | 名称 | 类型 | 匹配标签 | Stars | 描述 |
|---|------|------|----------|-------|------|
| 1 | xxx  | MCP  | python, fastapi | 1234 | xxx |
```

6. 提示: "输入 `/coding-hub-install <名称>` 安装"
