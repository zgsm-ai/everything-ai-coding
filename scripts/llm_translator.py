#!/usr/bin/env python3
"""LLM batch translator for entries missing description_zh.

Reuses LLM_BASE_URL / LLM_API_KEY / LLM_MODEL environment variables.
Cache stored at catalog/.llm_translate_cache.json.
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
CACHE_PATH = os.path.join(CATALOG_DIR, ".llm_translate_cache.json")
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
    """Build the LLM prompt for translation."""
    items = []
    for e in entries:
        name = e.get("name", "")[:100]
        desc = e.get("description", "")[:300]
        items.append(f"- id: {e['id']}\n  name: {name}\n  description: {desc}")

    return f"""Translate each description to concise Chinese (one sentence, max 50 chars).

ENTRIES:
{chr(10).join(items)}

Respond ONLY with a JSON object mapping entry id to Chinese description.
Example: {{"entry-id": "简洁的中文描述"}}"""


def _call_llm_batch(entries: list[dict]) -> dict[str, str]:
    """Call LLM API with a batch. Returns {id: description_zh} or {}."""
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
            {"role": "system", "content": "You translate software tool descriptions to concise Chinese. Respond only with valid JSON."},
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
            logger.warning(f"LLM translator API error (attempt {attempt+1}): {e}")
            if attempt < 2:
                time.sleep(2 ** attempt)
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.warning(f"LLM translator response parse error: {e}")
            return {}

    return {}


def llm_translate_entries(entries: list[dict]) -> dict[str, str]:
    """Translate entries missing description_zh using LLM.

    Args:
        entries: List of index entries.

    Returns:
        Dict mapping entry id to Chinese description.
    """
    base_url = os.environ.get("LLM_BASE_URL", "")
    api_key = os.environ.get("LLM_API_KEY", "")
    if not base_url or not api_key:
        logger.info("LLM credentials not set, skipping translation")
        return {}

    # Filter to entries needing translation
    needs_translate = [e for e in entries if not e.get("description_zh")]
    if not needs_translate:
        return {}

    # Check cache
    cache = _load_cache()
    result = {}
    uncached = []

    for e in needs_translate:
        eid = e["id"]
        if eid in cache and _is_cache_valid(cache[eid]):
            result[eid] = cache[eid]["description_zh"]
        else:
            uncached.append(e)

    if not uncached:
        return result

    # Batch LLM calls
    batches = [uncached[i:i+BATCH_SIZE] for i in range(0, len(uncached), BATCH_SIZE)]
    now_iso = datetime.now().isoformat()

    for i, batch in enumerate(batches):
        logger.info(f"Translating batch {i+1}/{len(batches)} ({len(batch)} entries)")
        raw = _call_llm_batch(batch)
        for e in batch:
            eid = e["id"]
            if eid in raw and isinstance(raw[eid], str):
                zh = raw[eid].strip()
                if zh:
                    result[eid] = zh
                    cache[eid] = {"description_zh": zh, "cached_at": now_iso}

        _save_cache(cache)
        time.sleep(1)  # Rate limit courtesy

    logger.info(f"LLM translator: {len(batches)} API calls, {len(result)} entries translated")
    return result
