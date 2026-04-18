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
- Command references (e.g. `/everything-ai-coding-install <id>`) stay as-is regardless of language.

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
   - If still failing, use local fallback path
4. Pre-filter with Python (cross-platform: use `$(command -v python3 || command -v python)`):
   - Load JSON file
   - If entries have a `search_text` field, match all keywords against `search_text` (case-insensitive)
   - Otherwise fall back to matching against `name`, `description`, `tags`, `tech_stack` separately (backward compatible)
   - If type filter specified, filter by `type` field first
   - Score each entry by the lexicographic descending key `(match_count, freshness_label != "abandoned", final_score, stars)` — `match_count` (number of distinct keywords matched) is the primary relevance signal; within equal relevance, non-abandoned entries outrank abandoned ones (sorting `True > False`); within the same relevance + freshness tier, `final_score` breaks ties ahead of `stars`. Treat missing `freshness_label` as not-abandoned and missing `final_score` as `0`. Do NOT drop abandoned entries here — the gate in step 7 handles them, and they may still surface in "Other Matches".
   - Keep `freshness_label` in the TSV so step 5 can apply the freshness preference and step 8 can render the stale warning: emit `id\ttype\tcategory\tstars\tfinal_score\tdecision\tfreshness_label\tdescription\tdescription_zh` (output top 30 candidates)
5. **Semantic reranking**: From the 30 candidates, YOU (Claude) read all entries' name + description and judge their relevance to the user's ORIGINAL query intent. Pick the top 5 most semantically relevant candidates. Consider:
   - Direct functional match (tool does exactly what user asked)
   - Closely related tools (solves the same problem from a different angle)
   - Do NOT simply pick by stars or score — prioritize semantic fit
   - **Freshness preference**: when two candidates are similarly relevant semantically, PREFER entries with `freshness_label != "abandoned"`. Abandoned entries can still appear in "Other Matches" but should NOT occupy verification slots unless no active/stale alternative matches the intent at all. If the shortlist genuinely has no active/stale matches, it is acceptable to verify abandoned candidates and note the staleness in the output.
   - If none of the 30 are relevant, say so honestly
6. For the top 5 semantically selected candidates, fetch per-entry API for verification:
   - Prefer `https://.../api/v1/{type}/{id}.json`
   - If per-entry API fails, fall back to full index and filter by `id`
   - Extract `source`, `evaluation`, `health`, `install`, `source_url`, `tags`, `highlights`, `weak_dims`, `freshness_label` fields — only pull a small number of directly usable signals
7. **Candidate Verification Gate (mandatory)**
   - NEVER label results as "recommendations" based solely on search hits or stars
   - A result enters the "Top Candidates" section ONLY when ALL of the following hold:
     1. `final_score >= 70`, AND
     2. `freshness_label != "abandoned"`, AND
     3. at least one tag / keyword / `search_text` hit.
   - Entries failing (1) or (2) are routed to "Other Matches" — they MUST NOT appear in "Top Candidates".
   - The numeric floor (≥70) decouples the gate from the rubric's `accept`/`review` symbol; a strong `review` entry (e.g. an official but thin-docs tool) can still reach Top Candidates on score alone. Treat missing `final_score` as `0` (i.e. not eligible).
   - If no candidate passes the gate, label results as "matches" or "worth checking" — never as "verified recommendation" or overpromise.
8. Format results as "Top Candidates + Other Matches" two-tier output (not a flat single table)
   - For broad-intent queries, top candidates should focus on one primary direction; avoid mixing too many adjacent categories on the first screen
   - **Rationale**: for each Top Candidate, derive the rationale from `highlights[0:2]` joined with `"; "`. If `highlights` is empty/missing, fall back to `description` (or `description_zh` in Chinese mode).
   - **Weak-dimension warnings**: when a Top Candidate has a non-empty `weak_dims` array, append one `⚠️` line per weak dimension. Each line describes WHERE the candidate scored low during LLM evaluation — it's a heads-up, not a deal-breaker. Do NOT leak the raw field name `weak_dims` or the rubric key (e.g. `install_clarity`) in output; use only the active-language label from the map below.

     ```
     coding_relevance → 编码相关度偏弱（与编码任务的直接关联较低） / coding relevance is weak (loosely tied to coding tasks)
     doc_completeness → 文档不完整（README 覆盖不全） / documentation is incomplete (README is sparse)
     desc_accuracy    → 描述与实际能力有出入 / description diverges from actual capability
     writing_quality  → 文档写作质量一般（表达不够清晰） / writing quality is weak (unclear phrasing)
     specificity      → 针对性不足（场景过于笼统） / specificity is low (scope too generic)
     install_clarity  → 安装/接入步骤不够清晰 / install steps are unclear
     ```

     Unknown-dimension fallback: if `weak_dims` contains a name not in the map (e.g. future rubric version), render the raw dimension name as the label — do not error or drop it.
   - **Stale freshness warning**: when a Top Candidate has `freshness_label == "stale"`, append a `⚠️` line — Chinese mode `⚠️ 半年未更新`, English mode `⚠️ half a year without update`. No warning when `freshness_label == "active"`; `"abandoned"` entries are already excluded by the gate.

## Output Structure

Output the following structure in the user's conversation language. The labels below are structural identifiers — translate them naturally.

```
Section: "Search Results: {query}"

Line: "Search terms: original={original} | compressed={compressed} | alternative={alternative or none}"

Section: "Top Candidates"
  (Only show gate-verified results. If none pass the gate, show: "No high-confidence candidates yet")
  Per item (use these exact labels — natural translations into the active language, NOT literal word-for-word):
    - ID (Type / Category)
    - English "Why it fits" / Chinese "推荐理由": relevance to user's query
    - English "Scoring basis" / Chinese "评分依据": brief understandable basis from source/quality/install feasibility
    - English "Install command" / Chinese "安装命令": `/everything-ai-coding-install <id>`

Section: "Other Matches" (table)
  Columns: # | ID | Type | Category | Stars | Install Method | Description
  (Use description_zh for Chinese users, description for others)
```

9. Footer prompt:
   - If top candidates exist: suggest installing or refining search
   - If no high-confidence candidates: suggest refining keywords or trying a specific candidate directly
