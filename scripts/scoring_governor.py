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
    """Apply governance: verify eval fields, fallback-score unevaluated entries, filter rejects."""
    dry_run = os.environ.get("EVAL_DRY_RUN", "true").lower() not in ("false", "0", "no")

    for entry in entries:
        ev = entry.get("evaluation", {})

        # If harness already scored this entry, just verify fields
        if ev.get("model_id") and ev.get("final_score") is not None:
            entry["final_score"] = ev["final_score"]
            entry["decision"] = ev.get("decision", "review")
            continue

        # Fallback: entry wasn't evaluated by harness — use old logic
        score = compute_final_score(entry)
        ev["final_score"] = score
        decision = judge_decision(entry)
        ev["decision"] = decision
        entry["evaluation"] = ev
        entry["final_score"] = score
        entry["decision"] = decision

        # Compute health via old scorer for fallback entries
        try:
            entry["health"] = compute_health(entry)
        except Exception:
            pass

    # Filter rejects
    result = []
    reject_count = 0
    for entry in entries:
        decision = entry.get("decision", "review")
        if decision == "reject" and not dry_run:
            reject_count += 1
            logger.info("REJECT (filtered): %s — score=%s", entry.get("id"), entry.get("final_score"))
        else:
            if decision == "reject":
                logger.info("REJECT (dry-run, kept): %s — score=%s", entry.get("id"), entry.get("final_score"))
            result.append(entry)

    logger.info("Governance: %d entries → %d kept, %d rejected", len(entries), len(result), reject_count)
    return result


def _normalize_type(t: str) -> str:
    """Normalize type string (strip trailing 's', lowercase)."""
    t = str(t).strip().lower()
    if t.endswith("s"):
        t = t[:-1]
    return t
