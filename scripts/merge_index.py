#!/usr/bin/env python3
"""Merge all type-specific indexes and curated files into catalog/index.json."""

import json
import os
import sys
from typing import Any
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
try:
    from .utils import (
        load_index,
        save_index,
        deduplicate,
        categorize,
        extract_tags,
        get_repo_languages,
        logger,
    )
    from .llm_tagger import llm_tag_entries
    from .llm_translator import llm_translate_entries
    from .health_scorer import compute_health
    from .catalog_lifecycle import (
        overlay_added_at,
        build_incremental_recrawl_candidates,
        backfill_missing_added_at,
    )
    from .unified_enrichment import ensure_evaluation
except ImportError:
    from utils import (
        load_index,
        save_index,
        deduplicate,
        categorize,
        extract_tags,
        get_repo_languages,
        logger,
    )
    from llm_tagger import llm_tag_entries
    from llm_translator import llm_translate_entries
    from health_scorer import compute_health
    from catalog_lifecycle import (
        overlay_added_at,
        build_incremental_recrawl_candidates,
        backfill_missing_added_at,
    )
    from unified_enrichment import ensure_evaluation

CATALOG_DIR = os.path.join(os.path.dirname(__file__), "..", "catalog")
TYPES = ["mcp", "skills", "rules", "prompts"]
TODAY = date.today().isoformat()


def _load_queue_state(queue_state_path: str) -> dict[str, Any]:
    try:
        with open(queue_state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, IOError):
        return {}


def merge():
    all_entries = []

    for resource_type in TYPES:
        type_dir = os.path.join(CATALOG_DIR, resource_type)

        # Load auto-synced index (includes Tier 1 + Tier 2 for skills)
        index_path = os.path.join(type_dir, "index.json")
        entries = load_index(index_path)
        logger.info(f"Loaded {len(entries)} entries from {resource_type}/index.json")
        all_entries.extend(entries)

        # Load curated entries (Tier 3 — lowest priority in dedup)
        curated_path = os.path.join(type_dir, "curated.json")
        curated = load_index(curated_path)
        if curated:
            logger.info(
                f"Loaded {len(curated)} entries from {resource_type}/curated.json"
            )
            all_entries.extend(curated)

    # Deduplicate by source_url + id (earlier entries take priority: Tier 1 > Tier 2 > Tier 3)
    # Count pre-dedup entries by type for integrity check
    pre_dedup_counts = {}
    for entry in all_entries:
        t = entry.get("type", "unknown")
        pre_dedup_counts[t] = pre_dedup_counts.get(t, 0) + 1

    deduped = deduplicate(all_entries)

    # Post-dedup integrity check: warn if any type lost >50%
    post_dedup_counts = {}
    for entry in deduped:
        t = entry.get("type", "unknown")
        post_dedup_counts[t] = post_dedup_counts.get(t, 0) + 1
    for t, pre in pre_dedup_counts.items():
        post = post_dedup_counts.get(t, 0)
        drop_pct = (1 - post / pre) * 100 if pre > 0 else 0
        if drop_pct > 50:
            logger.warning(
                f"Dedup integrity: type={t} dropped {drop_pct:.0f}% ({pre} → {post})"
            )
        else:
            logger.info(f"Dedup stats: type={t} {pre} → {post} (-{drop_pct:.0f}%)")

    # Fix invalid categories (e.g. "other" not in schema enum)
    VALID_CATEGORIES = {
        "frontend",
        "backend",
        "fullstack",
        "mobile",
        "devops",
        "database",
        "testing",
        "security",
        "ai-ml",
        "tooling",
        "documentation",
    }
    fixed_cats = 0
    for entry in deduped:
        if entry.get("category") not in VALID_CATEGORIES:
            tags = entry.get("tags") or []
            entry["category"] = categorize(
                entry.get("name", ""), entry.get("description", ""), tags
            )
            fixed_cats += 1
    if fixed_cats:
        logger.info(f"Fixed {fixed_cats} entries with invalid category")

    # --- Enrichment: LLM tags + Languages API tech_stack ---
    # Collect existing tag frequency for LLM reference vocabulary
    all_existing_tags = []
    for entry in deduped:
        all_existing_tags.extend(entry.get("tags") or [])

    # LLM tag enrichment for entries with <2 tags
    tag_results = llm_tag_entries(deduped, existing_tag_freq=all_existing_tags)
    if tag_results:
        enriched_tags = 0
        for entry in deduped:
            eid = entry["id"]
            if eid in tag_results and len(entry.get("tags") or []) < 2:
                entry["tags"] = tag_results[eid]
                enriched_tags += 1
        if enriched_tags:
            logger.info(f"LLM enriched tags for {enriched_tags} entries")

    # Languages API enrichment for entries with empty tech_stack
    enriched_ts = 0
    for entry in deduped:
        if not entry.get("tech_stack") and entry.get("source_url", ""):
            langs = get_repo_languages(entry["source_url"])
            if langs:
                entry["tech_stack"] = langs
                enriched_ts += 1
    if enriched_ts:
        logger.info(f"Languages API enriched tech_stack for {enriched_ts} entries")

    # LLM translation for entries missing description_zh
    translate_results = llm_translate_entries(deduped)
    if translate_results:
        enriched_zh = 0
        for entry in deduped:
            eid = entry["id"]
            if eid in translate_results and not entry.get("description_zh"):
                entry["description_zh"] = translate_results[eid]
                enriched_zh += 1
        if enriched_zh:
            logger.info(f"LLM enriched description_zh for {enriched_zh} entries")

    # Compute health scores
    for entry in deduped:
        ensure_evaluation(entry)
        entry["health"] = compute_health(entry)

    existing_output = load_index(os.path.join(CATALOG_DIR, "index.json"))
    existing_output = backfill_missing_added_at(existing_output, today=TODAY)
    prior_entries = deduped + existing_output
    deduped = overlay_added_at(deduped, prior_entries, today=TODAY)

    maintenance_dir = os.path.join(CATALOG_DIR, "maintenance")
    queue_path = os.path.join(maintenance_dir, "incremental_recrawl_candidates.json")
    queue_state_path = os.path.join(maintenance_dir, "incremental_recrawl_state.json")
    queue_state = _load_queue_state(queue_state_path)
    candidates, queue_state = build_incremental_recrawl_candidates(
        deduped,
        queue_state,
        now=datetime.combine(
            date.fromisoformat(TODAY), datetime.min.time(), tzinfo=timezone.utc
        ),
        threshold_days=365,
        cooldown_days=30,
        max_candidates=500,
    )
    save_index(candidates, queue_path)
    os.makedirs(os.path.dirname(queue_state_path), exist_ok=True)
    with open(queue_state_path, "w", encoding="utf-8") as f:
        json.dump(queue_state, f, indent=2, ensure_ascii=False)

    # Sort by health.score descending, ties broken by stars descending (nulls last)
    deduped.sort(
        key=lambda x: (
            x.get("health", {}).get("score", 0),
            x.get("stars") if x.get("stars") is not None else -1,
        ),
        reverse=True,
    )

    output_path = os.path.join(CATALOG_DIR, "index.json")
    save_index(deduped, output_path)

    # Print summary by type and category
    by_type = {}
    by_category = {}
    for entry in deduped:
        t = entry.get("type", "unknown")
        c = entry.get("category", "unknown")
        by_type[t] = by_type.get(t, 0) + 1
        by_category[c] = by_category.get(c, 0) + 1

    logger.info(f"\nTotal: {len(deduped)} entries")
    logger.info(f"By type: {by_type}")
    logger.info(f"By category: {by_category}")


if __name__ == "__main__":
    merge()
