#!/usr/bin/env python3
"""Enrichment orchestrator - unified Layer 2 enrichment entry point."""

import sys
import os
from typing import Any

sys.path.insert(0, os.path.dirname(__file__))
try:
    from .llm_tagger import llm_tag_entries
    from .llm_translator import llm_translate_entries
    from .llm_evaluator import enrich_quality
    from .unified_enrichment import populate_signals
except ImportError:
    from llm_tagger import llm_tag_entries
    from llm_translator import llm_translate_entries
    from llm_evaluator import enrich_quality
    from unified_enrichment import populate_signals


def enrich_entries(entries: list[dict[str, Any]]) -> None:
    """
    Orchestrate all Layer 2 enrichment steps (idempotent).
    Modifies entries in-place.
    """
    # Step 1: Tag enrichment (only for entries with <2 tags)
    all_existing_tags = []
    for entry in entries:
        all_existing_tags.extend(entry.get("tags") or [])

    tag_results = llm_tag_entries(entries, existing_tag_freq=all_existing_tags)
    if tag_results:
        for entry in entries:
            eid = entry["id"]
            if eid in tag_results and len(entry.get("tags") or []) < 2:
                # Merge existing tags with LLM tags
                existing = set(entry.get("tags") or [])
                new_tags = [t for t in tag_results[eid] if t not in existing]
                entry["tags"] = (entry.get("tags") or []) + new_tags

    # Step 2: Translation enrichment (only for entries missing description_zh)
    translate_results = llm_translate_entries(entries)
    if translate_results:
        for entry in entries:
            eid = entry["id"]
            if eid in translate_results and not entry.get("description_zh"):
                entry["description_zh"] = translate_results[eid]

    # Step 3: Quality evaluation (only for entries without evaluation)
    eval_results = enrich_quality(entries)
    if eval_results:
        for entry in entries:
            eid = entry["id"]
            if eid in eval_results:
                # Store LLM results temporarily for populate_signals
                entry["_llm_eval"] = eval_results[eid]

    # Step 4: Populate signals (fills evaluation sub-object)
    for entry in entries:
        populate_signals(entry)
        entry.pop("_llm_eval", None)  # Clean up temp field
        entry.pop("_prior_evaluation", None)  # Clean up fallback field
