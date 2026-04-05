---
description: 'Browse coding resource categories. Usage: /coding-hub-browse [category] [type:mcp|skill|rule|prompt]'
argument-hint: category name
---

# Coding Hub - Browse

$ARGUMENTS

---

## Language Detection

Determine the output language using the following priority chain (first match wins):

1. **Explicit parameter**: if `$ARGUMENTS` contains `lang:zh` or `lang:en`, use that (strip it from arguments)
2. **Conversation signal**: if the user's recent messages are clearly in one language, follow that
3. **System locale fallback**: run `echo $LANG` in Bash — if the value starts with `zh` (e.g. `zh_CN.UTF-8`), use Chinese; otherwise use English

Once determined, apply consistently:
- **All output** (section titles, table headers, labels, helper text) MUST be in the detected language.
- For the Description column in tables: use `description_zh` for Chinese, `description` for English.
- Command references (e.g. `/coding-hub-install <name>`) stay as-is regardless of language.

## Data Sources

Search index URL: `https://zgsm-sangfor.github.io/costrict-coding-hub/api/v1/search-index.json`
Fallback URL: `https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/catalog/search-index.json`

Extract optional category argument and `type:<value>` filter from $ARGUMENTS, then run Bash pre-filtering. **Note: browse is for exploration, not recommendation — do not label category listings as "recommended" unless high-confidence basis is provided.**

## Execution Flow

1. Download index to temp file: `curl -sf --compressed <index URL> -o "$TMPDIR/coding-hub-index.json"`, on failure try Fallback URL, then use Read to load local fallback and save to the same temp file

2. Pre-filter with Python (cross-platform: use `$(command -v python3 || command -v python)`)

### No arguments: Category Overview

Run the following inline Python script via Bash:

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

Format TSV output as a table:

| Category | Count | Description |
|----------|-------|-------------|
| ... | ... | (add brief description based on category name, in user's language) |

Footer: suggest using `/coding-hub-browse <category>` for details; for verified recommendations, use `/coding-hub-search` or `/coding-hub-recommend`

### With arguments: Show entries in that category

Run the following inline Python script via Bash:

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
    print(f\"{x.get('name','')}\t{x.get('type','')}\t{x.get('stars') or 0}\t{x.get('description','')}\t{x.get('description_zh','')}\")
" "${CATEGORY}" "${TYPE_FILTER}"
```

Format TSV output as a table. If the category has obvious top entries with high confidence, prepend up to 3 "worth checking first" items with brief rationale (e.g. official source, significantly higher stars, clear install method).

Output table columns: Name | Type | Stars | Description
(Use `description_zh` for Chinese users, `description` for others — both are provided in the TSV as the last two columns)

Footer: suggest `/coding-hub-install <name>` to install; for verified recommendations, use `/coding-hub-search` or `/coding-hub-recommend`
