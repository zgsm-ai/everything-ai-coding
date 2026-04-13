---
description: 'Search coding resources (MCP/Skills/Rules/Prompts). Usage: /everything-ai-coding-search <query>'
argument-hint: search keywords
---

# Everything AI Coding - Search

$ARGUMENTS

---

## Language Detection

Determine the output language using the following priority chain (first match wins):

1. **Explicit parameter**: if `$ARGUMENTS` contains `lang:zh` or `lang:en`, use that (strip it from the search query)
2. **Conversation signal**: if the user's recent messages are clearly in one language, follow that
3. **System locale fallback**: run `echo $LANG` in Bash — if the value starts with `zh` (e.g. `zh_CN.UTF-8`), use Chinese; otherwise use English

Once determined, apply consistently:
- **All output** (section titles, table headers, labels, helper text) MUST be in the detected language.
- For the Description column in tables: use `description_zh` for Chinese, `description` for English.
- For candidate detail text (why-it-fits, basis): generate in the detected language.
- Command references (e.g. `/everything-ai-coding-install <name>`) stay as-is regardless of language.

## Data Sources

**Note**: Apply GitHub Network Detection rules (see SKILL.md) to all GitHub URLs below. If `[network-config]` specifies a proxy, rewrite URLs accordingly.

Search index URL: `https://zgsm-ai.github.io/everything-ai-coding/api/v1/search-index.json`
Fallback URL: `https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/catalog/search-index.json`
Per-entry API: `https://zgsm-ai.github.io/everything-ai-coding/api/v1/{type}/{id}.json`
Full index fallback: `https://raw.githubusercontent.com/zgsm-ai/everything-ai-coding/main/catalog/index.json`

## Execution Flow

Extract the search query and optional type filter from $ARGUMENTS, then run Bash pre-filtering. **Note: search hits are NOT recommendations — only gate-verified candidates may be labeled as such.**

1. Extract search keywords and optional type filter from `$ARGUMENTS`
   - Supports `type:mcp`, `type:skill`, `type:rule`, `type:prompt` filters
   - Example: `/everything-ai-coding-search typescript type:mcp` — search MCP type only
   - If `type:<value>` is present, extract it as a filter; the rest becomes the search query
2. Generate up to 3 retrieval keyword sets for discovery:
   - **Original keywords**: the user's actual query
   - **Compressed keywords**: strip filler words (e.g. "help me", "I want", "please find", "帮我", "怎么", "有没有", "想找", "请问"), keep "domain + task" core terms
   - **Alternative synonyms**: add one lightweight alternative only when obvious, e.g. `deploy → deployment/ci-cd/release/publish`, `pr review → code review/pull request review`, `readme → docs`
   - NEVER rewrite install targets for aesthetics; rewrites are for search recall only
   - **Broad intent suppression**: for head queries like "deploy / release / publish", prioritize direct-action results (deploy workflows, CI/CD, platform publishing); push changelog / release notes to the supplementary section unless the query explicitly mentions "release notes"
3. Download index to temp file: `curl -sf --compressed <index URL> -o "$TMPDIR/everything-ai-coding-index.json"`
   - If curl fails, try Fallback URL: `curl -sf --compressed <Fallback URL> -o "$TMPDIR/everything-ai-coding-index.json"`
4. Pre-filter with Python (cross-platform: use `$(command -v python3 || command -v python)`):
   - Load JSON file
   - If entries have a `search_text` field, match all keywords against `search_text` (case-insensitive)
   - Otherwise fall back to matching against `name`, `description`, `tags`, `tech_stack` separately (backward compatible)
   - If type filter specified, filter by `type` field first
   - Score each entry: count how many distinct keywords matched, use `stars` as tiebreaker
   - Output top 30 candidates, each line: `id\tname\ttype\tcategory\tstars\tdescription\tdescription_zh` (TSV plain text)
5. **Semantic reranking**: From the 30 candidates, YOU (Claude) read all entries' name + description and judge their relevance to the user's ORIGINAL query intent. Pick the top 5 most semantically relevant candidates. Consider:
   - Direct functional match (tool does exactly what user asked)
   - Closely related tools (solves the same problem from a different angle)
   - Do NOT simply pick by stars or score — prioritize semantic fit
   - If none of the 30 are relevant, say so honestly
6. For the top 5 semantically selected candidates, fetch per-entry API for verification:
   - Prefer `https://.../api/v1/{type}/{id}.json`
   - If per-entry API fails, fall back to full index and filter by `id`
   - Extract `source`, `evaluation`, `health`, `install`, `source_url`, `tags` fields — only pull a small number of directly usable signals
7. **Candidate Verification Gate (mandatory)**
   - NEVER label results as "recommendations" based solely on search hits or stars
   - A result enters the "Top Candidates" section ONLY when it satisfies: **≥1 trust signal + ≥1 actionable signal**
   - Trust signal examples: official/well-known source, curated, notably higher quality/health signals
   - Actionable signal examples: `install.method` is defined, per-entry API provides usable install info
   - If the gate is not met, label results as "matches" or "worth checking" — never as "verified recommendation" or overpromise
8. Format results as "Top Candidates + Other Matches" two-tier output (not a flat single table)
   - For broad-intent queries, top candidates should focus on one primary direction; avoid mixing too many adjacent categories on the first screen

## Output Structure

Output the following structure in the user's conversation language. The labels below are structural identifiers — translate them naturally.

```
Section: "Search Results: {query}"

Line: "Search terms: original={original} | compressed={compressed} | alternative={alternative or none}"

Section: "Top Candidates"
  (Only show gate-verified results. If none pass the gate, show: "No high-confidence candidates yet")
  Per item:
    - Name (Type / Category)
    - Why worth checking: relevance to user's query
    - Basis: brief understandable basis from source/quality/install feasibility
    - Next step: `/everything-ai-coding-install <name>`

Section: "Other Matches" (table)
  Columns: # | Name | Type | Category | Stars | Install Method | Description
  (Use description_zh for Chinese users, description for others)
```

9. Footer prompt:
   - If top candidates exist: suggest installing or refining search
   - If no high-confidence candidates: suggest refining keywords or trying a specific candidate directly
