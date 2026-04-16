#!/usr/bin/env python3
"""Enrichment orchestrator - unified enrichment via eval harness.

All enrichment (tags, tech_stack, summary, search_terms, highlights)
and quality evaluation are produced in a single LLM call per entry
via the ai-resource-eval harness.
"""

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def enrich_entries(entries: list[dict[str, Any]]) -> None:
    """
    Orchestrate enrichment via eval harness (idempotent).
    Modifies entries in-place.
    """
    total_entries = len(entries)
    logger.info(f"Enrichment pipeline starting for {total_entries} entries")

    # Run eval harness (evaluation + enrichment in a single LLM call)
    incremental = os.environ.get("EVAL_INCREMENTAL", "true").lower() == "true"
    try:
        from eval_bridge import eval_and_map
        logger.info("Running eval harness (incremental=%s)...", incremental)
        eval_and_map(
            entries,
            cache_dir=str(Path(__file__).resolve().parent.parent / ".eval_cache"),
            incremental=incremental,
        )
    except ImportError:
        logger.warning("eval_bridge not available, skipping evaluation + enrichment")

    logger.info(f"Enrichment pipeline complete for {total_entries} entries")
