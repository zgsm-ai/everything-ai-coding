---
description: '浏览 coding 资源分类。用法: /coding-hub-browse [category] [type:mcp|skill|rule|prompt]'
argument-hint: category name
---

# Coding Hub - Browse

$ARGUMENTS

---

## 数据处理（重要：用 Bash 预过滤，避免全量 JSON 进入上下文）

索引 URL: `https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/catalog/search-index.json`

从 `$ARGUMENTS` 中提取可选的分类参数和 `type:<值>` 过滤条件后，用 Bash 执行预过滤：

1. 下载索引到临时文件: `curl -s <URL> -o "$TMPDIR/coding-hub-index.json"`
2. 用 python 脚本处理（跨平台：macOS/Linux 用 python3，Windows 用 python，探测命令 `$(command -v python3 || command -v python)`）

### 无参数时：分类概览

用 Bash 执行以下 python 脚本（内联 `-c`）：

```bash
PY=$(command -v python3 || command -v python)
$PY -c "
import json, sys
from collections import Counter
data = json.load(open('$TMPDIR/coding-hub-index.json'))
type_filter = sys.argv[1] if len(sys.argv) > 1 else ''
if type_filter:
    data = [x for x in data if x.get('type') == type_filter]
counts = Counter(x.get('category','unknown') for x in data)
for cat, cnt in sorted(counts.items(), key=lambda x: -x[1]):
    print(f'{cat}\t{cnt}')
" "${TYPE_FILTER}"
```

将 TSV 输出格式化为表格：

| 分类 | 数量 | 描述 |
|------|------|------|
| ... | ... | （根据分类名补充中文描述） |

提示: "输入 `/coding-hub-browse <分类名>` 查看详情"

### 有参数时：展示该分类下条目

用 Bash 执行以下 python 脚本（内联 `-c`）：

```bash
PY=$(command -v python3 || command -v python)
$PY -c "
import json, sys
data = json.load(open('$TMPDIR/coding-hub-index.json'))
category = sys.argv[1]
type_filter = sys.argv[2] if len(sys.argv) > 2 else ''
items = [x for x in data if x.get('category') == category]
if type_filter:
    items = [x for x in items if x.get('type') == type_filter]
items.sort(key=lambda x: -(x.get('stars') or 0))
for x in items:
    print(f\"{x.get('name','')}\t{x.get('type','')}\t{x.get('stars') or 0}\t{x.get('description','')}\")
" "${CATEGORY}" "${TYPE_FILTER}"
```

将 TSV 输出格式化为表格：

| 名称 | 类型 | Stars | 描述 |
|------|------|-------|------|
| ... | ... | ... | ... |

提示: "输入 `/coding-hub-install <名称>` 安装"
