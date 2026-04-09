#!/usr/bin/env python3
"""LLM batch search term enricher for catalog entries.

Generates user-perspective search terms (search_terms) for each entry,
enabling semantic recall in the search pipeline. Follows the same
batch + cache pattern as llm_tagger.py and llm_techstack_tagger.py.

Cache stored at catalog/.llm_search_cache.json.
"""

import os
import json
import time
import logging
from datetime import datetime, timedelta
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

logger = logging.getLogger(__name__)

CATALOG_DIR = os.path.join(os.path.dirname(__file__), "..", "catalog")
CACHE_PATH = os.path.join(CATALOG_DIR, ".llm_search_cache.json")
CACHE_EXPIRY_DAYS = 30
BATCH_SIZE = 40


def _load_cache() -> dict:
    if not os.path.exists(CACHE_PATH):
        return {}
    try:
        with open(CACHE_PATH, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def _save_cache(cache: dict):
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def _is_cache_valid(entry: dict) -> bool:
    cached_at = entry.get("cached_at", "")
    if not cached_at:
        return False
    try:
        dt = datetime.fromisoformat(cached_at)
        return datetime.now() - dt < timedelta(days=CACHE_EXPIRY_DAYS)
    except ValueError:
        return False


def _build_prompt(entries: list[dict]) -> str:
    """Build the LLM prompt for search term generation."""
    items = []
    for e in entries:
        name = e.get("name", "")[:100]
        desc = e.get("description", "")[:300]
        tags = ", ".join((e.get("tags") or [])[:8])
        entry_type = e.get("type", "")
        items.append(
            f"- id: {e['id']}\n  type: {entry_type}\n  name: {name}\n"
            f"  description: {desc}\n  tags: {tags}"
        )

    return f"""For each coding resource entry below, generate search terms that a developer would use to FIND this tool. Think from the USER's perspective, not the author's.

Include these types of terms (5-8 phrases per entry, mix of English and Chinese):
- Problem descriptions the user might type: "manage database migrations", "自动化部署"
- Use case phrases: "code review before PR", "生成 API 文档"
- Abbreviations and alternative names: "k8s" for kubernetes, "TS" for typescript
- Related concepts the author didn't mention but users associate with this tool
- Chinese equivalents of key English terms and vice versa

Do NOT include:
- The tool's own name (already searchable)
- Generic terms like "tool", "server", "plugin" alone
- Tags that are already present in the entry

ENTRIES:
{chr(10).join(items)}

Respond ONLY with a JSON object mapping entry id to an array of search term strings.
Example: {{"entry-id": ["database migration", "数据库迁移", "schema management", "DB schema versioning", "migrate tables"]}}"""


def _call_llm_batch(entries: list[dict]) -> dict[str, list[str]]:
    """Call LLM API with a batch. Returns {id: [search_terms]} or {}."""
    base_url = os.environ.get("LLM_BASE_URL", "")
    api_key = os.environ.get("LLM_API_KEY", "")
    model = os.environ.get("LLM_MODEL", "deepseek-chat")

    if not base_url or not api_key:
        return {}

    prompt = _build_prompt(entries)
    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a search term generator for coding resources. "
                    "Generate terms that developers would type when searching "
                    "for these tools. Respond only with valid JSON."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 8192,
    }

    data = json.dumps(payload).encode()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    req = Request(url, data=data, headers=headers, method="POST")

    for attempt in range(3):
        try:
            with urlopen(req, timeout=300) as resp:
                result = json.loads(resp.read().decode())
                content = result["choices"][0]["message"]["content"].strip()
                if content.startswith("```"):
                    content = content.split("\n", 1)[1].rsplit("```", 1)[0]
                return json.loads(content)
        except (HTTPError, URLError, TimeoutError) as e:
            logger.warning(f"LLM search enricher API error (attempt {attempt+1}): {e}")
            if attempt < 2:
                time.sleep(2 ** attempt)
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.warning(f"LLM search enricher response parse error: {e}")
            return {}

    return {}


def _postprocess_terms(terms: list) -> list[str]:
    """Strip, dedup while preserving order.

    Unlike llm_tagger's _postprocess_tags() which lowercases all tags,
    search terms preserve original casing for display (e.g. "CI/CD", "k8s").
    Deduplication is case-insensitive to avoid near-duplicates.
    """
    seen = set()
    result = []
    for t in terms:
        if not isinstance(t, str):
            continue
        t = t.strip()
        t_lower = t.lower()
        if t and t_lower not in seen:
            seen.add(t_lower)
            result.append(t)
    return result[:10]  # Cap at 10 to limit search_text bloat


def enrich_search_terms(entries: list[dict]) -> dict[str, list[str]]:
    """Generate search terms for all entries using LLM.

    Args:
        entries: List of index entries.

    Returns:
        Dict mapping entry id to list of search term phrases.
    """
    base_url = os.environ.get("LLM_BASE_URL", "")
    api_key = os.environ.get("LLM_API_KEY", "")
    if not base_url or not api_key:
        logger.info("LLM credentials not set, skipping search term enrichment")
        return {}

    # Check cache
    cache = _load_cache()
    result = {}
    uncached = []

    for e in entries:
        eid = e["id"]
        if eid in cache and _is_cache_valid(cache[eid]):
            result[eid] = cache[eid]["terms"]
        else:
            uncached.append(e)

    if not uncached:
        logger.info(f"Search enricher: all {len(result)} entries cached")
        return result

    # Batch LLM calls
    batches = [uncached[i:i+BATCH_SIZE] for i in range(0, len(uncached), BATCH_SIZE)]
    now_iso = datetime.now().isoformat()

    for batch_idx, batch in enumerate(batches):
        raw = _call_llm_batch(batch)
        if not raw:
            logger.warning(f"Search enricher: batch {batch_idx+1}/{len(batches)} failed, skipping")
            continue
        for e in batch:
            eid = e["id"]
            if eid in raw and isinstance(raw[eid], list):
                terms = _postprocess_terms(raw[eid])
                result[eid] = terms
                cache[eid] = {"terms": terms, "cached_at": now_iso}

        _save_cache(cache)

    cached_count = len(entries) - len(uncached)
    new_count = len(result) - cached_count
    logger.info(
        f"Search enricher: {len(batches)} API calls, "
        f"{cached_count} cached, {new_count} new from LLM"
    )
    return result
