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

    Stage order (per spec security-risk-eval D5):
        1. quality eval + enrichment (existing — eval_and_map)
        2. security_scan (new — security_scan_and_map)
        3. scoring_governor / catalog_lifecycle (downstream — merge_index.py)

    Security stage failures are caught and logged here; they never propagate
    up so the rest of the pipeline (governor, lifecycle, sort, output) keeps
    running. ``SECURITY_SCAN_ENABLED=false`` skips the security stage entirely,
    leaving any pre-existing ``entry.security`` blocks untouched.
    """
    total_entries = len(entries)
    logger.info(f"Enrichment pipeline starting for {total_entries} entries")

    # Run eval harness (evaluation + enrichment in a single LLM call)
    incremental = os.environ.get("EVAL_INCREMENTAL", "true").lower() == "true"
    try:
        concurrency = int(os.environ.get("EVAL_CONCURRENCY", "4"))
    except ValueError:
        concurrency = 4
    cache_dir = str(Path(__file__).resolve().parent.parent / ".eval_cache")

    try:
        from eval_bridge import eval_and_map
        logger.info(
            "Running eval harness (incremental=%s, concurrency=%d)...",
            incremental,
            concurrency,
        )
        eval_and_map(
            entries,
            cache_dir=cache_dir,
            incremental=incremental,
            concurrency=concurrency,
        )
    except ImportError:
        logger.warning("eval_bridge not available, skipping evaluation + enrichment")

    # Security scan stage (independent LLM call per entry; failure-isolated)
    security_enabled = os.environ.get("SECURITY_SCAN_ENABLED", "true").lower() != "false"
    if security_enabled:
        try:
            from eval_bridge import security_scan_and_map
            logger.info(
                "Running security scan stage (incremental=%s, concurrency=%d)...",
                incremental,
                concurrency,
            )
            security_scan_and_map(
                entries,
                cache_dir=cache_dir,
                incremental=incremental,
                concurrency=concurrency,
            )
        except ImportError:
            logger.warning("security_scan_and_map not available; skipping security stage")
        except Exception as exc:  # noqa: BLE001 - never break the main pipeline
            logger.warning("Security scan stage raised but was suppressed: %s", exc)
    else:
        logger.info("SECURITY_SCAN_ENABLED=false; skipping security scan stage")

    # Resource authenticity stage (github-trending only; is_primary_skill judgment).
    # Mirrors the security stage: scoped, independent cache namespace, failure-safe.
    # ``AUTHENTICITY_SCAN_ENABLED=false`` skips it entirely.
    authenticity_enabled = (
        os.environ.get("AUTHENTICITY_SCAN_ENABLED", "true").lower() != "false"
    )
    if authenticity_enabled:
        try:
            from eval_bridge import authenticity_scan_and_map
            logger.info("Running resource authenticity stage (github-trending only)...")
            authenticity_scan_and_map(
                entries,
                cache_dir=cache_dir,
                incremental=incremental,
            )
        except ImportError:
            logger.warning(
                "authenticity_scan_and_map not available; skipping authenticity stage"
            )
        except Exception as exc:  # noqa: BLE001 - never break the main pipeline
            logger.warning("Resource authenticity stage raised but was suppressed: %s", exc)
    else:
        logger.info("AUTHENTICITY_SCAN_ENABLED=false; skipping resource authenticity stage")

    logger.info(f"Enrichment pipeline complete for {total_entries} entries")
