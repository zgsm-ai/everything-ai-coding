#!/usr/bin/env python3
"""LLM batch tagger for entries with insufficient tags.

Sends entries with <2 tags to an LLM in batches, returns suggested tags.
Reuses LLM_BASE_URL / LLM_API_KEY / LLM_MODEL environment variables.
Cache stored at catalog/.llm_tag_cache.json (separate from llm_evaluator cache).
"""

import os
import json
import time
import logging
from collections import Counter
from datetime import datetime, timedelta
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

logger = logging.getLogger(__name__)

CATALOG_DIR = os.path.join(os.path.dirname(__file__), "..", "catalog")
CACHE_PATH = os.path.join(CATALOG_DIR, ".llm_tag_cache.json")
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


def _build_prompt(entries: list[dict], reference_vocab: list[str]) -> str:
    """Build the LLM prompt for tag suggestion."""
    items = []
    for e in entries:
        name = e.get("name", "")[:100]
        desc = e.get("description", "")[:300]
        url = e.get("source_url", "")[:200]
        items.append(f"- id: {e['id']}\n  name: {name}\n  description: {desc}\n  url: {url}")

    vocab_str = ", ".join(reference_vocab[:40]) if reference_vocab else "(none yet)"

    return f"""For each entry below, suggest 3-5 relevant tags.

FORMAT RULES:
- Output kebab-case lowercase tags (e.g. nextjs, react-native, postgres)
- Do NOT use dots, spaces, or uppercase (not Next.js, React Native, PostgreSQL)
- Prefer tags from the reference vocabulary when applicable

REFERENCE VOCABULARY (high-frequency existing tags):
{vocab_str}

ENTRIES:
{chr(10).join(items)}

Respond ONLY with a JSON object mapping entry id to tag array.
Example: {{"entry-id": ["python", "cli", "mcp-server"]}}"""


def _call_llm_batch(entries: list[dict], reference_vocab: list[str]) -> dict[str, list[str]]:
    """Call LLM API with a batch. Returns {id: [tags]} or {}."""
    base_url = os.environ.get("LLM_BASE_URL", "")
    api_key = os.environ.get("LLM_API_KEY", "")
    model = os.environ.get("LLM_MODEL", "deepseek-chat")

    if not base_url or not api_key:
        return {}

    prompt = _build_prompt(entries, reference_vocab)
    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a coding resource tagger. Respond only with valid JSON."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
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
            logger.warning(f"LLM tagger API error (attempt {attempt+1}): {e}")
            if attempt < 2:
                time.sleep(2 ** attempt)
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.warning(f"LLM tagger response parse error: {e}")
            return {}

    return {}


def _postprocess_tags(tags: list) -> list[str]:
    """Lowercase, strip, dedup while preserving order."""
    seen = set()
    result = []
    for t in tags:
        if not isinstance(t, str):
            continue
        t = t.lower().strip()
        if t and t not in seen:
            seen.add(t)
            result.append(t)
    return result


def _compute_reference_vocab(existing_tag_freq: list[str] | None) -> list[str]:
    """Get top 40 most common tags from existing frequency list."""
    if not existing_tag_freq:
        return []
    counter = Counter(existing_tag_freq)
    return [tag for tag, _ in counter.most_common(40)]


def llm_tag_entries(entries: list[dict],
                    existing_tag_freq: list[str] | None = None) -> dict[str, list[str]]:
    """Tag entries with insufficient tags (<2) using LLM.

    Args:
        entries: List of index entries.
        existing_tag_freq: Flat list of all existing tags (for frequency counting).

    Returns:
        Dict mapping entry id to list of suggested tags (lowercased, deduped).
    """
    base_url = os.environ.get("LLM_BASE_URL", "")
    api_key = os.environ.get("LLM_API_KEY", "")
    if not base_url or not api_key:
        logger.info("LLM credentials not set, skipping tag enrichment")
        return {}

    # Filter to entries needing tags
    needs_tags = [e for e in entries if len(e.get("tags") or []) < 2]
    if not needs_tags:
        return {}

    # Check cache
    cache = _load_cache()
    result = {}
    uncached = []

    for e in needs_tags:
        eid = e["id"]
        if eid in cache and _is_cache_valid(cache[eid]):
            result[eid] = cache[eid]["tags"]
        else:
            uncached.append(e)

    if not uncached:
        return result

    # Build reference vocabulary
    reference_vocab = _compute_reference_vocab(existing_tag_freq)

    # Batch LLM calls
    batches = [uncached[i:i+BATCH_SIZE] for i in range(0, len(uncached), BATCH_SIZE)]
    now_iso = datetime.now().isoformat()

    for batch in batches:
        raw = _call_llm_batch(batch, reference_vocab)
        for e in batch:
            eid = e["id"]
            if eid in raw and isinstance(raw[eid], list):
                tags = _postprocess_tags(raw[eid])
                result[eid] = tags
                cache[eid] = {"tags": tags, "cached_at": now_iso}

        _save_cache(cache)

    logger.info(f"LLM tagger: {len(batches)} API calls, {len(result)} entries tagged")
    return result
