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
        logger,
    )
    from .enrichment_orchestrator import enrich_entries
    from .scoring_governor import apply_governance
    from .catalog_lifecycle import (
        overlay_added_at,
        build_incremental_recrawl_candidates,
        backfill_missing_added_at,
    )
except ImportError:
    from utils import (
        load_index,
        save_index,
        deduplicate,
        categorize,
        extract_tags,
        logger,
    )
    from enrichment_orchestrator import enrich_entries
    from scoring_governor import apply_governance
    from catalog_lifecycle import (
        overlay_added_at,
        build_incremental_recrawl_candidates,
        backfill_missing_added_at,
    )

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
    pre_dedup_counts = {}
    for entry in all_entries:
        t = entry.get("type", "unknown")
        pre_dedup_counts[t] = pre_dedup_counts.get(t, 0) + 1

    deduped = deduplicate(all_entries)

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

    # Fix invalid categories
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

    # --- Overlay prior evaluation from existing output ---
    # Per-type source indexes don't carry evaluation data. Store the full
    # prior evaluation under _prior_evaluation so populate_signals() can
    # use it as a fallback when cache/LLM are unavailable, preventing
    # unchanged entries from losing their scores. Only overlay timestamps
    # into evaluation{} to avoid blocking enrich_quality() re-evaluation.
    existing_output = load_index(os.path.join(CATALOG_DIR, "index.json"))
    _TIMESTAMP_KEYS = ("evaluated_at", "evaluator")
    _SCORE_KEYS = ("coding_relevance", "content_quality", "specificity")
    existing_eval_map = {}
    for entry in existing_output:
        eid = entry.get("id")
        ev = entry.get("evaluation")
        if eid and ev and (ev.get("evaluated_at") or any(ev.get(k) for k in _SCORE_KEYS)):
            existing_eval_map[eid] = ev
    for entry in deduped:
        eid = entry.get("id")
        if eid and eid in existing_eval_map and not entry.get("evaluation"):
            prior_ev = existing_eval_map[eid]
            entry["_prior_evaluation"] = dict(prior_ev)
            entry["evaluation"] = {k: prior_ev[k] for k in _TIMESTAMP_KEYS if k in prior_ev}

    # --- Layer 2: Enrichment (tags, translation, LLM evaluation, signals) ---
    enrich_entries(deduped)
    logger.info(f"Enrichment complete for {len(deduped)} entries")

    # --- Layer 3: Scoring & Governance (final_score, decision, health, reject filter) ---
    deduped = apply_governance(deduped)
    logger.info(f"Governance complete: {len(deduped)} entries after filtering")

    # --- Lifecycle ---
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

    # Generate lightweight search index (subset of fields for search/browse/recommend)
    SEARCH_INDEX_FIELDS = (
        "id", "name", "type", "category", "tags", "tech_stack",
        "stars", "description", "description_zh", "source_url",
    )
    search_entries = []
    for entry in deduped:
        se = {k: entry.get(k) for k in SEARCH_INDEX_FIELDS}
        install_obj = entry.get("install")
        se["install_method"] = install_obj.get("method") if isinstance(install_obj, dict) else None
        search_entries.append(se)

    search_index_path = os.path.join(CATALOG_DIR, "search-index.json")
    with open(search_index_path, "w", encoding="utf-8") as f:
        json.dump(search_entries, f, ensure_ascii=False, separators=(",", ":"))

    full_size = os.path.getsize(output_path)
    search_size = os.path.getsize(search_index_path)
    ratio = search_size / full_size * 100 if full_size else 0
    logger.info(
        f"Search index: {len(search_entries)} entries, "
        f"{search_size / 1024:.0f} KB ({ratio:.1f}% of full index)"
    )

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
