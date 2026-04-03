---
description: '基于当前项目技术栈推荐 coding 资源。用法: /coding-hub:recommend [type:mcp|skill|rule|prompt]'
---

# Coding Hub - Recommend

$ARGUMENTS

---

## 数据处理（重要：用 Bash 预过滤，避免全量 JSON 进入上下文）

索引 URL: `https://zgsm-sangfor.github.io/costrict-coding-hub/api/v1/search-index.json`
Fallback URL: `https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/catalog/search-index.json`
本地备用: `/Volumes/Work/Projects/costrict-coding-hub/catalog/search-index.json`
单条 API: `https://zgsm-sangfor.github.io/costrict-coding-hub/api/v1/{type}/{id}.json`
全量索引 fallback: `https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/catalog/index.json`

## 执行流程

1. 从 `$ARGUMENTS` 中提取可选的类型过滤参数
   - 支持 `type:mcp`、`type:skill`、`type:rule`、`type:prompt` 过滤
   - 示例: `/coding-hub:recommend type:mcp` — 只推荐 MCP 类型
   - 如果参数中包含 `type:<值>`，提取为过滤条件
2. 分析当前项目技术栈：
   - 读取 `package.json` → 提取 dependencies 中的框架名 (react, next, vue, express, etc.)
   - 读取 `requirements.txt` / `pyproject.toml` → 提取 Python 包名
   - 读取 `go.mod` → 提取 Go module
   - 读取 `Cargo.toml` → 提取 Rust crate
   - 读取 `Gemfile` → 提取 Ruby gem
   - 检查文件后缀: `.tsx`→react, `.vue`→vue, `.py`→python, `.go`→go, `.rs`→rust, `.swift`→swift, `.kt`→kotlin
   - 检查配置文件: `Dockerfile`→docker, `.github/workflows/`→ci-cd, `tsconfig.json`→typescript
3. 基于识别到的技术栈生成轻量推荐关键词：
   - 保留检测到的技术栈标签
   - 将“框架 + 任务”压缩成更适合索引匹配的短词，如 `react performance`、`fastapi docs`、`docker ci-cd`
   - 如果用户额外给了上下文（如只要 skill / 只要 mcp），保留该约束，不要被改写覆盖
   - **默认偏好规则**：如果用户没有显式指定 `type:mcp`，优先考虑更直接服务于当前项目实现/约束/流程的 `skill`、`rule`、`prompt`；只有当某个 MCP 明显就是该场景的核心工作流工具时，才把它放进优先候选
4. 下载索引到临时文件: `curl -sf --compressed <索引 URL> -o "$TMPDIR/coding-hub-index.json"`，如果失败则尝试 Fallback URL，仍失败则用本地备用路径
5. 用 python 脚本预过滤（跨平台：macOS/Linux 用 python3，Windows 用 python，探测命令 `$(command -v python3 || command -v python)`）:
   - 读取 JSON 文件
   - 将检测到的项目 tags 与每条的 `tags` + `tech_stack` 做交集匹配，并补充轻量推荐关键词匹配
   - 如果指定了 type 过滤，先按 type 字段过滤
   - 先按匹配标签数排序，再按 stars 排序
   - 输出 top 15，每行格式: `id\tname\ttype\tmatched_tags\tstars\tinstall_method\tsource_url\tdescription`（TSV 纯文本）
6. 从 shortlist 中选出前 3-5 个候选，用单条 API 获取详情做候选验证：
   - 优先读取 `source`、`evaluation`、`health`、`install`、`source_url`
   - 结合当前项目栈判断“是否真的适合当前项目”，而不仅是标签碰巧命中
7. **候选验证门（必须执行）**
   - **禁止**把所有匹配结果都称为“推荐”
   - 只有同时满足下面这条简化规则时，才可进入“优先候选”区：**项目匹配明确 + 至少 1 个可信信号 + 至少 1 个可执行信号**
   - 可信信号示例：官方/精选、知名来源、较明显的质量/健康信号
   - 可执行信号示例：安装方式明确、单条 API 提供了完整安装信息
   - 如果做不到这条规则，就输出“项目匹配结果”或“值得先看”的候选，而不是强行称为推荐
   - **类型偏置校正**：在没有 `type:mcp` 约束时，不要因为 MCP 条目有更强的官方/安装信号，就自动压过更贴合项目实现的 skill/prompt/rule
   - **稀疏命中规则（尤其是 `type:mcp`）**：如果当前栈没有明显的专项候选，优先返回“2 个强匹配 + 明确说明覆盖较薄”，不要用条件性很强或场景依赖项（如仅在 MySQL / 自建 MCP 服务时才成立的条目）去把列表凑满
8. 将结果格式化为“优先候选 + 其他匹配结果”两层输出，并遵守以下约束：
   - `优先候选` 默认只给 2-3 个，除非结果非常接近且难以区分
   - `其他匹配结果` 默认只给 2-4 个补充项，不要展开成长列表
   - **不要**在主回答里直接暴露原始评分字段或内部排序字段，只翻译成用户能理解的短依据
   - **不要**在每个条目下重复安装命令，把安装动作收敛到最后的“默认安装建议”

## 输出格式

```
## 项目推荐

检测到技术栈: Python, FastAPI, Docker, PostgreSQL

推荐关键词：fastapi backend, docker ci-cd

### 优先候选（仅展示通过候选验证门的候选；如果没有则写“暂无高置信候选”）

1. <名称>（<类型>）
   - 为什么适合当前项目：<与项目技术栈或当前默认场景的直接关系>
   - 为什么值得先看：<官方来源 / 安装明确 / 更贴合当前栈等简短依据>

### 其他匹配结果

| # | 名称 | 类型 | 匹配标签 | Stars | 安装方式 | 描述 |
|---|------|------|----------|-------|----------|------|
| 1 | xxx  | MCP  | python, fastapi | 1234 | mcp_config | xxx |
```

9. 提示：
   - 如果存在优先候选：在最后给出 1-2 个默认安装建议，例如“如果你只先装一个，先试 `/coding-hub:install <名称>`”
   - 如果没有高置信候选："我找到了若干与项目相关的候选，但暂时没有足够高置信的优先候选。你可以继续限定类型/场景，或先查看候选详情"
