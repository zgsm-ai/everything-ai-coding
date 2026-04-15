#!/usr/bin/env python3
"""Scoring governor - Layer 3: final_score calculation, decision, and reject filtering."""

import os
import logging
from typing import Any

try:
    from .health_scorer import compute_health
except ImportError:
    from health_scorer import compute_health

logger = logging.getLogger(__name__)

# Safe-by-default: dry-run unless explicitly disabled.
# CI sets EVAL_DRY_RUN via vars; local/manual runs stay non-destructive.
_raw = os.environ.get("EVAL_DRY_RUN", "true").lower()
EVAL_DRY_RUN = _raw not in ("false", "0", "no")

# Per-type signal weights for final_score (0-100)
TYPE_WEIGHTS = {
    "mcp": {
        "coding_relevance": 0.30,
        "content_quality": 0.25,
        "specificity": 0.20,
        "source_trust": 0.15,
        "confidence": 0.10,
    },
    "skill": {
        "coding_relevance": 0.30,
        "content_quality": 0.25,
        "specificity": 0.20,
        "source_trust": 0.15,
        "confidence": 0.10,
    },
    "rule": {
        "coding_relevance": 0.35,
        "content_quality": 0.35,
        "source_trust": 0.15,
        "confidence": 0.15,
    },
    "prompt": {
        "coding_relevance": 0.35,
        "content_quality": 0.35,
        "source_trust": 0.15,
        "confidence": 0.15,
    },
}

# Per-type decision thresholds (on final_score 0-100 scale)
TYPE_THRESHOLDS = {
    "mcp": {"accept": 50, "review": 35},
    "skill": {"accept": 50, "review": 35},
    "rule": {"accept": 40, "review": 25},
    "prompt": {"accept": 40, "review": 25},
}


def compute_final_score(entry: dict[str, Any]) -> int:
    """Compute final_score (0-100) from evaluation signals and type-specific weights."""
    evaluation = entry.get("evaluation") or {}
    entry_type = _normalize_type(entry.get("type", ""))
    weights = TYPE_WEIGHTS.get(entry_type, TYPE_WEIGHTS["mcp"])

    score = 0.0
    for signal, weight in weights.items():
        value = evaluation.get(signal)
        if value is not None:
            # Signals are 1-5, normalize to 0-100
            score += (int(value) / 5 * 100) * weight

    return max(0, min(100, int(round(score))))


def judge_decision(entry: dict[str, Any]) -> str:
    """Determine accept/review/reject based on final_score and type-specific thresholds."""
    evaluation = entry.get("evaluation") or {}
    final_score = evaluation.get("final_score", 0)
    cr = evaluation.get("coding_relevance", 3)

    # Hard rule: entries LLM deems unrelated to coding (cr≤1) never auto-accept.
    # Default cr=3 so entries without LLM evaluation skip this gate.
    if cr is not None and int(cr) <= 1:
        if final_score < 35:
            return "reject"
        return "review"

    entry_type = _normalize_type(entry.get("type", ""))
    thresholds = TYPE_THRESHOLDS.get(entry_type, TYPE_THRESHOLDS["mcp"])

    if final_score >= thresholds["accept"]:
        return "accept"
    elif final_score >= thresholds["review"]:
        return "review"
    return "reject"


def apply_governance(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Apply Layer 3 governance: compute final_score, decision, health, filter rejects.
    Returns filtered list (rejects removed unless dry-run).
    """
    reject_count = 0
    result = []

    for entry in entries:
        # Always compute and persist governance metadata (final_score,
        # decision, health) so the published catalog retains correct
        # sorting and signals regardless of mode.
        final_score = compute_final_score(entry)
        evaluation = entry.get("evaluation") or {}
        evaluation["final_score"] = final_score
        entry["evaluation"] = evaluation

        decision = judge_decision(entry)
        evaluation["decision"] = decision

    # Deep review: reclassify "review" entries by fetching actual content.
    # Runs after all entries have initial decisions, before reject filtering.
    # Lazy import to avoid circular dependency (deep_reviewer imports judge_decision).
    try:
        try:
            from .deep_reviewer import deep_review_entries
        except ImportError:
            from deep_reviewer import deep_review_entries
        deep_review_entries(entries)
    except ImportError:
        logger.debug("deep_reviewer module not available, skipping deep review")
    except Exception as e:
        logger.warning(f"Deep review failed, skipping: {e}")

    for entry in entries:
        evaluation = entry.get("evaluation") or {}
        decision = evaluation.get("decision", "reject")

        entry["health"] = compute_health(entry)

        if decision == "reject":
            reject_count += 1
            score = evaluation.get("final_score", 0)
            if EVAL_DRY_RUN:
                # Dry-run: log but keep the entry in the output.
                logger.debug(
                    f"[DRY-RUN] Would reject: {entry.get('id')} "
                    f"(score={score}, type={entry.get('type')})"
                )
                result.append(entry)
            else:
                logger.debug(
                    f"Rejected: {entry.get('id')} "
                    f"(score={score}, type={entry.get('type')})"
                )
        else:
            result.append(entry)

    if reject_count:
        mode = "[DRY-RUN] " if EVAL_DRY_RUN else ""
        logger.info(
            f"{mode}Governance: {reject_count}/{len(entries)} entries rejected, "
            f"{len(result)} entries kept"
        )
    else:
        logger.info(f"Governance: all {len(entries)} entries accepted")

    return result


def _normalize_type(t: str) -> str:
    """Normalize type string (strip trailing 's', lowercase)."""
    t = str(t).strip().lower()
    if t.endswith("s"):
        t = t[:-1]
    return t
