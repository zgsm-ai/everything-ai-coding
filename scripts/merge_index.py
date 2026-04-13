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
        normalize_source_url,
        get_repo_meta,
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
        normalize_source_url,
        get_repo_meta,
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


def overlay_curated_fields(entries: list) -> list:
    """Merge supplementary fields from curated.json files into deduped entries.

    For each entry in the deduped list, if a matching curated entry exists
    (matched by id, with fallback to normalized source_url):
      - tech_stack: union of curated + existing (curated values first, deduplicated)
      - tags: append curated tags (deduplicated)
      - Non-supplementary fields (name, description, stars, source_url, install,
        evaluation) are NOT overwritten.

    Curated entries with no match are appended as new entries.

    This function is idempotent: calling it multiple times produces the same result.
    """
    # Build lookup maps over the deduped entries
    id_to_entry: dict[str, Any] = {}
    url_to_entry: dict[str, Any] = {}
    for entry in entries:
        eid = entry.get("id", "")
        if eid:
            id_to_entry[eid] = entry
        surl = entry.get("source_url", "")
        if surl:
            url_to_entry[normalize_source_url(surl)] = entry

    appended: list = []

    for resource_type in TYPES:
        curated_path = os.path.join(CATALOG_DIR, resource_type, "curated.json")
        curated_entries = load_index(curated_path)
        for curated in curated_entries:
            cid = curated.get("id", "")
            curl = curated.get("source_url", "")
            norm_curl = normalize_source_url(curl) if curl else ""

            # Find match: id first, then normalized source_url
            target = None
            if cid and cid in id_to_entry:
                target = id_to_entry[cid]
            elif norm_curl and norm_curl in url_to_entry:
                target = url_to_entry[norm_curl]

            if target is None:
                # No match — append as new entry, track to prevent
                # duplicates from subsequent curated entries in the loop
                appended.append(curated)
                if cid:
                    id_to_entry[cid] = curated
                if norm_curl:
                    url_to_entry[norm_curl] = curated
                continue

            # Merge tech_stack: curated first, then existing, deduplicated
            curated_ts = curated.get("tech_stack") or []
            existing_ts = target.get("tech_stack") or []
            merged_ts_seen: set = set()
            merged_ts: list = []
            for item in curated_ts + existing_ts:
                if item not in merged_ts_seen:
                    merged_ts_seen.add(item)
                    merged_ts.append(item)
            target["tech_stack"] = merged_ts

            # Merge tags: append curated tags (deduplicated)
            curated_tags = curated.get("tags") or []
            existing_tags = target.get("tags") or []
            existing_tags_set = set(existing_tags)
            for tag in curated_tags:
                if tag not in existing_tags_set:
                    existing_tags.append(tag)
                    existing_tags_set.add(tag)
            target["tags"] = existing_tags

    return entries + appended


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

    # Overlay supplementary fields (tech_stack, tags) from curated.json files
    deduped = overlay_curated_fields(deduped)

    # --- Backfill pushed_at from GitHub API for entries missing it ---
    missing_pushed_at = [e for e in deduped if not e.get("pushed_at") and e.get("source_url", "").startswith("https://github.com/")]
    if missing_pushed_at:
        logger.info(f"Backfilling pushed_at for {len(missing_pushed_at)} entries via GitHub API")
        filled = 0
        for entry in missing_pushed_at:
            meta = get_repo_meta(entry["source_url"])
            if meta and meta.get("pushed_at"):
                entry["pushed_at"] = meta["pushed_at"]
                filled += 1
        logger.info(f"Backfilled pushed_at for {filled}/{len(missing_pushed_at)} entries")

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

    # Promote scoring fields to top level for easy consumption by search/browse/recommend
    for entry in deduped:
        ev = entry.get("evaluation") or {}
        entry["final_score"] = ev.get("final_score", 0)
        entry["decision"] = ev.get("decision", "review")

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

    # Sort by final_score descending, then health.score, then stars (nulls last)
    deduped.sort(
        key=lambda x: (
            x.get("final_score", 0),
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
        "final_score", "decision",
    )
    search_entries = []
    for entry in deduped:
        se = {k: entry.get(k) for k in SEARCH_INDEX_FIELDS}
        install_obj = entry.get("install")
        se["install_method"] = install_obj.get("method") if isinstance(install_obj, dict) else None
        # Build search_text: merged field for semantic keyword matching
        parts = [
            entry.get("name", ""),
            entry.get("description", ""),
            entry.get("description_zh", ""),
            " ".join(entry.get("tags") or []),
            " ".join(entry.get("tech_stack") or []),
            " ".join(entry.get("search_terms") or []),
        ]
        se["search_text"] = " ".join(p for p in parts if p)
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
