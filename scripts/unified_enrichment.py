#!/usr/bin/env python3
"""Unified enrichment - Layer 2 signal population."""

from __future__ import annotations
import re
from typing import Any
from datetime import datetime


SOURCE_TRUST_MAP = {
    "anthropics-skills": 5,
    "curated": 5,
    "awesome-mcp-servers": 4,
    "awesome-mcp-zh": 4,
    "awesome-cursorrules": 4,
    "prompts-chat": 4,
    "antigravity-skills": 3,
    "ai-agent-skills": 3,
    "openclaw-skills": 3,
    "rules-2.1-optimized": 3,
    "wonderful-prompts": 3,
    "github-search": 3,
    "mcp.so": 2,
}

DEFAULT_SOURCE_TRUST = 2


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


def compute_confidence(entry: dict[str, Any], has_llm: bool) -> int:
    """Compute confidence score (1-5) based on signal richness."""
    # Base: 3 if LLM evaluated, 1 if heuristic only
    base = 3 if has_llm else 1

    bonus = 0
    stars = entry.get("stars") or 0
    if stars > 100:
        bonus += 1
    elif stars > 10:
        bonus += 0  # no bonus for moderate stars

    # Recent activity bonus
    pushed_at = entry.get("pushed_at") or ""
    if pushed_at:
        try:
            pushed = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
            days_ago = (datetime.now(pushed.tzinfo) - pushed).days
            if days_ago <= 90:
                bonus += 1
        except (ValueError, TypeError):
            pass

    penalty = 0
    desc = entry.get("description") or ""
    if len(desc) < 20:
        penalty += 1

    confidence = base + bonus - penalty
    return max(1, min(5, confidence))


def generate_heuristic_reason(entry: dict[str, Any]) -> str:
    """Generate reason from deterministic signals (3-level fallback)."""
    parts = []

    # Install method
    install = entry.get("install") or {}
    method = install.get("method")
    if method == "mcp_config":
        parts.append("Easy install via MCP config")
    elif method:
        parts.append(f"Install via {method}")

    # Stars
    stars = entry.get("stars") or 0
    if stars > 0:
        parts.append(f"{stars} stars")

    # Freshness
    pushed_at = entry.get("pushed_at") or ""
    if pushed_at:
        try:
            pushed = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
            days_ago = (datetime.now(pushed.tzinfo) - pushed).days
            if days_ago <= 30:
                parts.append("recently updated")
            elif days_ago <= 180:
                parts.append("updated within 6 months")
        except (ValueError, TypeError):
            pass

    if parts:
        return "; ".join(parts)

    # Fallback to source
    source = entry.get("source") or "unknown"
    return f"Accepted from {source} source"


def _heuristic_specificity(entry: dict[str, Any]) -> int:
    """Deterministic specificity (1-5) from metadata when LLM is unavailable."""
    score = 3  # base: assume moderately specific
    desc = entry.get("description") or ""
    name = entry.get("name") or ""

    # Vague indicators
    vague_words = {"general", "various", "multiple", "many", "all", "any"}
    if any(w in desc.lower() or w in name.lower() for w in vague_words):
        score -= 1

    # Specific indicators (mentions concrete tech/protocols)
    specific_words = {"api", "protocol", "format", "standard", "spec"}
    if any(w in desc.lower() for w in specific_words):
        score += 1

    return max(1, min(5, score))


def _heuristic_coding_relevance(entry: dict[str, Any]) -> int:
    """Deterministic coding_relevance (1-5) from metadata when LLM is unavailable.

    Caps:
    - Non-dev tools (Slack/Discord/email etc.) → max 2
    - Dev keyword bonus → max 4 (score 5 requires "operates on code itself",
      which heuristic cannot verify)
    """
    score = 2  # base: assume minimally relevant
    desc = (entry.get("description") or "").lower()
    name = (entry.get("name") or "").lower()
    tags = entry.get("tags") or []
    tag_str = " ".join(tags).lower()
    combined = f"{desc} {name} {tag_str}"

    # Non-dev tool keywords → primary audience is not developers, cap at 2
    # Use word boundary matching to avoid false positives on substrings
    # (e.g., "note" inside "notebook", "chat" inside "chatops")
    non_dev_keywords = {"slack", "discord", "email", "calendar",
                        "social", "marketing", "seo"}
    if any(re.search(rf"\b{kw}\b", combined) for kw in non_dev_keywords):
        return min(2, score)

    coding_keywords = {"api", "sdk", "cli", "server", "client", "database", "git",
                       "code", "debug", "test", "lint", "build", "deploy", "docker"}
    matches = sum(1 for kw in coding_keywords if kw in desc or kw in tag_str)
    if matches >= 3:
        score += 2
    elif matches >= 1:
        score += 1

    stars = entry.get("stars") or 0
    if stars > 100:
        score += 1

    # Cap at 4: score 5 requires evidence of operating on code itself,
    # which heuristic cannot verify
    return min(4, score)


def _heuristic_content_quality(entry: dict[str, Any]) -> int:
    """Deterministic content_quality (1-5) from metadata when LLM is unavailable."""
    score = 2  # base
    desc = entry.get("description") or ""
    if len(desc) >= 80:
        score += 1
    elif len(desc) < 20:
        score -= 1

    stars = entry.get("stars") or 0
    if stars > 500:
        score += 2
    elif stars > 50:
        score += 1

    return max(1, min(5, score))


def populate_signals(entry: dict[str, Any]) -> None:
    """
    Populate Layer 2 evaluation signals on entry.
    Does NOT compute final_score or decision (that's Layer 3).
    """
    evaluation = dict(entry.get("evaluation") or {})
    llm_eval = entry.get("_llm_eval") or {}
    prior_eval = entry.get("_prior_evaluation") or {}

    # LLM-sourced signals (prefer _llm_eval, then existing evaluation, then prior, then top-level)
    coding_relevance = (
        llm_eval.get("coding_relevance")
        or evaluation.get("coding_relevance")
        or prior_eval.get("coding_relevance")
        or entry.get("coding_relevance")
    )
    content_quality = (
        llm_eval.get("content_quality")
        or evaluation.get("content_quality")
        or prior_eval.get("content_quality")
        or entry.get("quality_score")
    )

    # Track whether we're using prior scores or backfilling heuristically
    used_prior = False
    if coding_relevance is not None:
        evaluation["coding_relevance"] = int(coding_relevance)
        if not llm_eval and prior_eval.get("coding_relevance") == coding_relevance:
            used_prior = True
    else:
        evaluation["coding_relevance"] = _heuristic_coding_relevance(entry)

    if content_quality is not None:
        evaluation["content_quality"] = int(content_quality)
        if not llm_eval and prior_eval.get("content_quality") == content_quality:
            used_prior = True
    else:
        evaluation["content_quality"] = _heuristic_content_quality(entry)

    # Specificity (only for MCP/Skill)
    entry_type = entry.get("type")
    if entry_type in ("mcp", "skill"):
        specificity = (
            llm_eval.get("specificity")
            or evaluation.get("specificity")
            or prior_eval.get("specificity")
        )
        if specificity is not None:
            evaluation["specificity"] = int(specificity)
            if not llm_eval and prior_eval.get("specificity") == specificity:
                used_prior = True
        else:
            evaluation["specificity"] = _heuristic_specificity(entry)

    # Source trust (deterministic mapping)
    source = entry.get("source") or ""
    evaluation["source_trust"] = SOURCE_TRUST_MAP.get(source, DEFAULT_SOURCE_TRUST)

    # Metadata - use prior evaluation if we're reusing its scores, otherwise fresh/heuristic
    if used_prior and prior_eval:
        evaluation["evaluated_at"] = prior_eval.get("evaluated_at", datetime.now().isoformat())
        evaluation["evaluator"] = prior_eval.get("evaluator", "heuristic")
        evaluation["confidence"] = prior_eval.get("confidence", compute_confidence(entry, True))
        if not evaluation.get("reason"):
            evaluation["reason"] = prior_eval.get("reason", generate_heuristic_reason(entry))
    else:
        # Fresh LLM eval or heuristic backfill
        has_llm = bool(llm_eval.get("evaluator"))
        evaluation["confidence"] = compute_confidence(entry, has_llm)

        llm_reasoning = llm_eval.get("reasoning") or ""
        if llm_reasoning:
            evaluation["reason"] = llm_reasoning
        elif not evaluation.get("reason"):
            evaluation["reason"] = generate_heuristic_reason(entry)

        evaluation["evaluated_at"] = (
            llm_eval.get("evaluated_at") or datetime.now().isoformat()
        )
        evaluation["evaluator"] = llm_eval.get("evaluator") or "heuristic"

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
    """Apply enrichment fields to entry (backward-compatible helper)."""
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

    populate_signals(entry)
    if reason:
        entry["evaluation"]["reason"] = reason
