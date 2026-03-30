#!/usr/bin/env python3

from __future__ import annotations
from typing import Any


def _normalize_tags(tags: list[str] | None) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for tag in tags or []:
        normalized = str(tag).strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def ensure_evaluation(entry: dict[str, Any]) -> None:
    evaluation = dict(entry.get("evaluation") or {})

    coding_relevance = entry.get("coding_relevance")
    content_quality = entry.get("quality_score")
    if coding_relevance is not None:
        evaluation.setdefault("coding_relevance", coding_relevance)
    if content_quality is not None:
        evaluation.setdefault("content_quality", content_quality)

    if (
        evaluation.get("coding_relevance") is not None
        and evaluation.get("content_quality") is not None
    ):
        final_score = int(
            (evaluation["coding_relevance"] + evaluation["content_quality"]) / 10 * 100
        )
        evaluation.setdefault("specificity", evaluation["content_quality"])
        evaluation.setdefault("source_trust", 3)
        evaluation.setdefault("confidence", 3)
        evaluation.setdefault("final_score", final_score)
        evaluation.setdefault("decision", "accept")
        evaluation.setdefault("reason", "Derived from current enrichment signals")

    entry["evaluation"] = evaluation


def apply_enrichment(
    entry: dict[str, Any],
    *,
    category: str | None = None,
    tags: list[str] | None = None,
    description_zh: str | None = None,
    coding_relevance: int | None = None,
    content_quality: int | None = None,
    reason: str | None = None,
) -> None:
    if category:
        entry["category"] = category
    if tags is not None:
        entry["tags"] = _normalize_tags(tags)
    if description_zh:
        entry["description_zh"] = description_zh
    if coding_relevance is not None:
        entry["coding_relevance"] = coding_relevance
    if content_quality is not None:
        entry["quality_score"] = content_quality

    ensure_evaluation(entry)
    if reason:
        entry["evaluation"]["reason"] = reason
