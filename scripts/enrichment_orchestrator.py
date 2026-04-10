#!/usr/bin/env python3
"""Enrichment orchestrator - unified Layer 2 enrichment entry point."""

import logging
import sys
import os
from typing import Any

sys.path.insert(0, os.path.dirname(__file__))
try:
    from .llm_tagger import llm_tag_entries
    from .llm_translator import llm_translate_entries, llm_translate_to_english
    from .llm_evaluator import enrich_quality
    from .unified_enrichment import populate_signals
    from .llm_techstack_tagger import tag_techstack
    from .llm_search_enricher import enrich_search_terms
except ImportError:
    from llm_tagger import llm_tag_entries
    from llm_translator import llm_translate_entries, llm_translate_to_english
    from llm_evaluator import enrich_quality
    from unified_enrichment import populate_signals
    from llm_techstack_tagger import tag_techstack
    from llm_search_enricher import enrich_search_terms

logger = logging.getLogger(__name__)


def enrich_entries(entries: list[dict[str, Any]]) -> None:
    """
    Orchestrate all Layer 2 enrichment steps (idempotent).
    Modifies entries in-place.
    """
    total_entries = len(entries)
    logger.info(f"Enrichment pipeline starting for {total_entries} entries")

    # Step 1: Tag enrichment (only for entries with <2 tags)
    all_existing_tags = []
    for entry in entries:
        all_existing_tags.extend(entry.get("tags") or [])

    tag_candidates = sum(1 for entry in entries if len(entry.get("tags") or []) < 2)
    logger.info(
        f"Enrichment step 1/5: tag enrichment starting for {tag_candidates} entries"
    )
    tag_results = llm_tag_entries(entries, existing_tag_freq=all_existing_tags)
    logger.info(
        f"Enrichment step 1/5 complete: {len(tag_results)} entries received tag suggestions"
    )
    if tag_results:
        for entry in entries:
            eid = entry["id"]
            if eid in tag_results and len(entry.get("tags") or []) < 2:
                # Merge existing tags with LLM tags
                existing = set(entry.get("tags") or [])
                new_tags = [t for t in tag_results[eid] if t not in existing]
                entry["tags"] = (entry.get("tags") or []) + new_tags

    # Step 1b: Tech stack tagging (only for entries missing tech_stack)
    techstack_candidates = [e for e in entries if not e.get("tech_stack")]
    logger.info(
        "Enrichment step 2/5: tech stack tagging starting "
        f"for {len(techstack_candidates)} entries"
    )
    techstack_results = tag_techstack(techstack_candidates)
    logger.info(
        "Enrichment step 2/5 complete: "
        f"{len(techstack_results)} entries received tech stack tags"
    )
    if techstack_results:
        for entry in entries:
            eid = entry["id"]
            if eid in techstack_results and not entry.get("tech_stack"):
                entry["tech_stack"] = techstack_results[eid]

    # Step 1.5: Ensure description is English (translate Chinese → English)
    en_candidates = sum(1 for entry in entries if entry.get("description"))
    logger.info(
        "Enrichment step 3/5: English normalization starting "
        f"for up to {en_candidates} entries"
    )
    en_results = llm_translate_to_english(entries)
    logger.info(
        "Enrichment step 3/5 complete: "
        f"{len(en_results)} entries normalized to English"
    )
    if en_results:
        for entry in entries:
            eid = entry["id"]
            if eid in en_results:
                if not entry.get("description_zh"):
                    entry["description_zh"] = entry.get("description", "")
                entry["description"] = en_results[eid]

    # Step 2: Translation enrichment (only for entries missing description_zh)
    translate_candidates = sum(1 for entry in entries if not entry.get("description_zh"))
    logger.info(
        "Enrichment step 4/5: Chinese translation starting "
        f"for {translate_candidates} entries"
    )
    translate_results = llm_translate_entries(entries)
    logger.info(
        "Enrichment step 4/5 complete: "
        f"{len(translate_results)} entries received Chinese descriptions"
    )
    if translate_results:
        for entry in entries:
            eid = entry["id"]
            if eid in translate_results and not entry.get("description_zh"):
                entry["description_zh"] = translate_results[eid]

    # Step 3: Quality evaluation (only for entries without evaluation)
    eval_candidates = sum(
        1 for entry in entries if not entry.get("evaluation", {}).get("coding_relevance")
    )
    logger.info(
        f"Enrichment step 5/5a: quality evaluation starting for {eval_candidates} entries"
    )
    eval_results = enrich_quality(entries)
    logger.info(
        f"Enrichment step 5/5a complete: {len(eval_results)} entries received evaluation data"
    )
    if eval_results:
        for entry in entries:
            eid = entry["id"]
            if eid in eval_results:
                # Store LLM results temporarily for populate_signals
                entry["_llm_eval"] = eval_results[eid]

    # Step 4: Populate signals (fills evaluation sub-object)
    logger.info(f"Enrichment step 5/5b: signal population starting for {total_entries} entries")
    for entry in entries:
        populate_signals(entry)
        entry.pop("_llm_eval", None)  # Clean up temp field
        entry.pop("_prior_evaluation", None)  # Clean up fallback field
    logger.info("Enrichment step 5/5b complete: signal population finished")

    # Step 5: Search term enrichment (generates search_terms for semantic recall)
    try:
        logger.info(
            f"Enrichment step 5/5c: search term enrichment starting for {total_entries} entries"
        )
        search_results = enrich_search_terms(entries)
        logger.info(
            "Enrichment step 5/5c complete: "
            f"{len(search_results)} entries returned search terms"
        )
        if search_results:
            for entry in entries:
                eid = entry["id"]
                if eid in search_results:
                    entry["search_terms"] = search_results[eid]
            # Ensure all entries have search_terms (empty array as default)
            for entry in entries:
                if "search_terms" not in entry:
                    entry["search_terms"] = []
    except Exception as e:
        logger.warning(f"Search term enrichment failed, skipping: {e}")
        for entry in entries:
            if "search_terms" not in entry:
                entry["search_terms"] = []

    logger.info(f"Enrichment pipeline complete for {total_entries} entries")
