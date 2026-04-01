#!/usr/bin/env python3
"""Health scorer: compute composite health score from multiple signals."""

import math
from datetime import datetime, timezone
from typing import Any


def compute_health(
    entry: dict[str, Any], *, now: datetime | None = None
) -> dict[str, Any]:
    """Compute health score and signals for a catalog entry.

    Returns dict with:
    - score: 0-100 integer
    - signals: {popularity, freshness, quality, installability}
    - freshness_label: "active" | "stale" | "abandoned"
    - last_commit: ISO timestamp or null
    """
    popularity = _compute_popularity(entry.get("stars"))
    freshness_result = _compute_freshness(entry.get("pushed_at"), now=now)
    quality = _compute_quality(entry)
    installability = _compute_installability(entry.get("install", {}))

    # Weighted linear formula
    score = (
        0.30 * popularity
        + 0.25 * freshness_result["score"]
        + 0.25 * quality
        + 0.20 * installability
    )

    return {
        "score": int(round(score)),
        "signals": {
            "popularity": popularity,
            "freshness": freshness_result["score"],
            "quality": quality,
            "installability": installability,
        },
        "freshness_label": freshness_result["label"],
        "last_commit": entry.get("pushed_at"),
    }


def _compute_popularity(stars: int | None) -> int:
    """Normalize stars to 0-100 scale using log10."""
    if stars is None or stars <= 0:
        return 0
    score = math.log10(max(stars, 1)) / math.log10(100000) * 100
    return min(100, int(round(score)))


def _compute_freshness(
    pushed_at: str | None, *, now: datetime | None = None
) -> dict[str, Any]:
    """Compute freshness score and label from pushed_at timestamp.

    Spec:
    - Active (≤90d): score=100
    - Stale (90d-365d): linear decay from 100 → 30
    - Abandoned (>365d): linear decay from 30 → 0 (capped at 0 for >3 years)
    - Null pushed_at: score=0, label="abandoned"
    """
    if not pushed_at:
        return {"score": 0, "label": "abandoned"}

    try:
        last_push = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
        if now is None:
            reference_now = datetime.now(timezone.utc)
        elif now.tzinfo is None:
            reference_now = now.replace(tzinfo=timezone.utc)
        else:
            reference_now = now.astimezone(timezone.utc)
        days_ago = max((reference_now - last_push).days, 0)

        if days_ago <= 90:
            return {"score": 100, "label": "active"}
        elif days_ago <= 365:
            # Linear decay: 100 at 90d → 30 at 365d
            score = 100 - (days_ago - 90) * (100 - 30) / (365 - 90)
            return {"score": int(round(score)), "label": "stale"}
        else:
            # Linear decay: 30 at 365d → 0 at 3 years (1095d), capped at 0
            score = max(0, 30 - (days_ago - 365) * 30 / (1095 - 365))
            return {"score": int(round(score)), "label": "abandoned"}
    except (ValueError, AttributeError):
        return {"score": 0, "label": "abandoned"}


def _compute_quality(entry: dict[str, Any]) -> int:
    """Compute quality score from evaluation.final_score or heuristics.

    Priority:
    1. evaluation.final_score (set by scoring_governor Layer 3)
    2. LLM scores: (coding_relevance + quality_score) / 10 * 100
    3. MCP/skill heuristic from install completeness + description
    4. Rule/prompt without evaluation → 0
    """
    evaluation = entry.get("evaluation") or {}

    # Prefer final_score from Layer 3 governance
    final_score = evaluation.get("final_score")
    if final_score is not None:
        return int(final_score)
    coding_rel = entry.get("coding_relevance")
    quality_score = entry.get("quality_score")
    if coding_rel is None:
        coding_rel = evaluation.get("coding_relevance")
    if quality_score is None:
        quality_score = evaluation.get("content_quality")

    if coding_rel is not None and quality_score is not None:
        return int((coding_rel + quality_score) / 10 * 100)

    # Rules and prompts without LLM evaluation → 0
    entry_type = str(entry.get("type", "")).strip().lower()
    if entry_type.endswith("s"):
        entry_type = entry_type[:-1]
    if entry_type in ("rule", "prompt"):
        return 0
    if entry_type not in ("mcp", "skill"):
        return 0

    # MCP/skill heuristic: install completeness (0-50) + description quality (0-50)
    score = 0

    install = entry.get("install", {})
    method = install.get("method")
    if method == "mcp_config":
        score += 50
    elif method == "mcp_config_template":
        score += 40
    elif method == "git_clone":
        score += 30
    elif method == "download_file":
        score += 20

    desc = (entry.get("description") or "").strip()
    if len(desc) >= 100:
        score += 50
    elif len(desc) >= 50:
        score += 25
    elif len(desc) >= 20:
        score += 10

    return min(100, score)


def _compute_installability(install: dict[str, Any]) -> int:
    """Map install method to 0-100 score."""
    if not install or "method" not in install:
        return 0

    method_value = install.get("method")
    method = str(method_value) if method_value is not None else ""
    mapping = {
        "mcp_config": 100,
        "mcp_config_template": 80,
        "git_clone": 60,
        "download_file": 40,
        "manual": 20,
    }
    return mapping.get(method, 0)
