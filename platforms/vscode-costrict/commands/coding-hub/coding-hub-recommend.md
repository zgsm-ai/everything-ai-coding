---
description: 'Recommend coding resources based on current project stack. Usage: /coding-hub-recommend [type:mcp|skill|rule|prompt]'
argument-hint: type filter
---

# Coding Hub - Recommend

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
- For candidate detail text (why-it-fits, basis): generate in the detected language.
- Command references (e.g. `/coding-hub-install <name>`) stay as-is regardless of language.

## Data Sources

Search index URL: `https://zgsm-sangfor.github.io/costrict-coding-hub/api/v1/search-index.json`
Fallback URL: `https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/catalog/search-index.json`
Per-entry API: `https://zgsm-sangfor.github.io/costrict-coding-hub/api/v1/{type}/{id}.json`
Full index fallback: `https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/catalog/index.json`

## Execution Flow

1. Extract optional type filter from `$ARGUMENTS`
   - Supports `type:mcp`, `type:skill`, `type:rule`, `type:prompt` filters
   - Example: `/coding-hub-recommend type:mcp` — recommend MCP type only
   - If `type:<value>` is present, extract it as a filter
2. Analyze current project tech stack:
   - Read `package.json` → extract framework names from dependencies (react, next, vue, express, etc.)
   - Read `requirements.txt` / `pyproject.toml` → extract Python packages
   - Read `go.mod` → extract Go modules
   - Read `Cargo.toml` → extract Rust crates
   - Read `Gemfile` → extract Ruby gems
   - Check file extensions: `.tsx`→react, `.vue`→vue, `.py`→python, `.go`→go, `.rs`→rust, `.swift`→swift, `.kt`→kotlin
   - Check config files: `Dockerfile`→docker, `.github/workflows/`→ci-cd, `tsconfig.json`→typescript
3. Generate lightweight recommendation keywords from detected stack:
   - Retain detected tech stack tags
   - Compress "framework + task" into index-friendly short terms, e.g. `react performance`, `fastapi docs`, `docker ci-cd`
   - If user provided extra context (e.g. skill-only or mcp-only), preserve that constraint — do not overwrite with rewrites
   - **Default preference rule**: unless user explicitly specifies `type:mcp`, prioritize `skill`, `rule`, `prompt` that directly serve project implementation/constraints/workflow; only include MCP entries when one is clearly the core workflow tool for the scenario
4. Download index to temp file: `curl -sf --compressed <index URL> -o "$TMPDIR/coding-hub-index.json"`, on failure try Fallback URL, then local fallback
5. Pre-filter with Python (cross-platform: use `$(command -v python3 || command -v python)`):
   - Load JSON file
   - Match detected project tags against each entry's `tags` + `tech_stack`, supplement with lightweight recommendation keyword matching
   - If type filter specified, filter by `type` field first
   - Sort by matched tag count, then by stars
   - Output top 15, each line: `id\tname\ttype\tmatched_tags\tstars\tinstall_method\tsource_url\tdescription\tdescription_zh` (TSV plain text)
6. From shortlist, select top 3-5 candidates and fetch per-entry API for verification:
   - Prefer `source`, `evaluation`, `health`, `install`, `source_url`
   - Combine with current project stack to judge "does this truly fit the current project" — not just coincidental tag matches
7. **Candidate Verification Gate (mandatory)**
   - NEVER label all matches as "recommendations"
   - A candidate enters the "Top Candidates" section ONLY when it satisfies: **clear project match + ≥1 trust signal + ≥1 actionable signal**
   - Trust signal examples: official/curated source, well-known origin, notable quality/health signals
   - Actionable signal examples: install method is defined, per-entry API provides complete install info
   - If the gate is not met, output "project matches" or "worth checking" — never force the label "recommendation"
   - **Type bias correction**: without `type:mcp` constraint, do not let MCP entries dominate over more project-relevant skill/prompt/rule just because MCP has stronger official/install signals
   - **Sparse hit rule (especially `type:mcp`)**: if the current stack has no obvious specialized candidates, prefer "2 strong matches + explicit thin-coverage note" over padding the list with edge-case entries
8. Format results as "Top Candidates + Other Matches" two-tier output, with these constraints:
   - Top Candidates: default 2-3 items, unless results are very close and hard to distinguish
   - Other Matches: default 2-4 supplementary items, do not expand into a long list
   - NEVER expose raw scoring fields or internal sort fields in the main response — translate into brief user-understandable rationale
   - NEVER repeat install commands under each entry — consolidate install actions into a final "suggested install" section

## Output Structure

Output the following structure in the user's conversation language. The labels below are structural identifiers — translate them naturally.

```
Section: "Project Recommendations"

Line: "Detected stack: {stack list}"
Line: "Recommendation keywords: {keywords}"

Section: "Top Candidates"
  (Only show gate-verified candidates. If none pass: "No high-confidence candidates yet")
  Per item:
    - Name (Type)
    - Why it fits the current project: direct relationship with project stack or default scenario
    - Why worth checking: brief rationale (official source / clear install / best stack fit)

Section: "Other Matches" (table)
  Columns: # | Name | Type | Matched Tags | Stars | Install Method | Description
  (Use description_zh for Chinese users, description for others)
```

9. Footer prompt:
   - If top candidates exist: suggest installing the top one, e.g. "To get started, try `/coding-hub-install <name>`"
   - If no high-confidence candidates: explain that matches were found but none pass the confidence gate, suggest refining type/scenario or browsing candidates
