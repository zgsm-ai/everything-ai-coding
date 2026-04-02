---
description: '搜索 coding 资源（MCP/Skills/Rules/Prompts）。用法: /coding-hub-search <query>'
argument-hint: search keywords
---

# Coding Hub - Search

$ARGUMENTS

---

## 数据处理（重要：用 Bash 预过滤，避免全量 JSON 进入上下文）

索引 URL: `https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/catalog/search-index.json`

将搜索关键词和可选 type 过滤从 $ARGUMENTS 中提取后，用 Bash 执行预过滤：

1. 从 `$ARGUMENTS` 中提取搜索关键词和可选的类型过滤参数
   - 支持 `type:mcp`、`type:skill`、`type:rule`、`type:prompt` 过滤
   - 示例: `/coding-hub-search typescript type:mcp` — 只搜索 MCP 类型
   - 如果参数中包含 `type:<值>`，提取为过滤条件，剩余部分作为搜索关键词
2. 下载索引到临时文件: `curl -s <URL> -o "$TMPDIR/coding-hub-index.json"`
3. 用 python 脚本过滤（跨平台：macOS/Linux 用 python3，Windows 用 python，探测命令 `$(command -v python3 || command -v python)`）:
   - 读取 JSON 文件
   - 在 name、description、tags 中搜索关键词（不区分大小写）
   - 如果指定了 type 过滤，先按 type 字段过滤
   - 按匹配字段数 + stars 降序排序
   - 输出 top 10，每行格式: `name\ttype\tcategory\tstars\tdescription`（TSV 纯文本）
4. 将 bash 输出的 TSV 结果格式化为表格展示给用户

## 输出格式

```
## 搜索结果: "<query>"

| # | 名称 | 类型 | 分类 | Stars | 描述 |
|---|------|------|------|-------|------|
| 1 | xxx  | MCP  | xxx  | 1234  | xxx  |
```

5. 提示用户: "输入 `/coding-hub-install <名称>` 安装，或继续搜索"
