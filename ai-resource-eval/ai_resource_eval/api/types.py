"""Pydantic models for ai-resource-eval evaluation pipeline."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Decision(str, Enum):
    """Evaluation decision outcome."""

    accept = "accept"
    review = "review"
    reject = "reject"


class ContentSource(str, Enum):
    """Primary content source strategy."""

    readme = "readme"
    description = "description"


# ---------------------------------------------------------------------------
# EvalItem — catalog entry input
# ---------------------------------------------------------------------------


class EvalItem(BaseModel):
    """A single catalog entry to be evaluated.

    Flexible schema: only ``id`` and ``name`` are required.  All other fields
    are optional so the model can ingest catalog entries that may have varying
    shapes.
    """

    id: str
    name: str
    type: str | None = None
    description: str | None = None
    source_url: str | None = None
    stars: int | None = None
    pushed_at: datetime | str | None = None
    category: str | None = None
    tags: list[str] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)
    install: dict[str, Any] | None = None
    source: str | None = None
    last_synced: str | None = None
    added_at: str | None = None
    description_zh: str | None = None
    search_terms: list[str] = Field(default_factory=list)

    # Existing evaluation / health data (from upstream catalog) — ignored by
    # this harness but accepted so we can round-trip catalog JSON.
    evaluation: dict[str, Any] | None = None
    health: dict[str, Any] | None = None
    final_score: float | None = None
    decision: str | None = None

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# MetricResult — single dimension output
# ---------------------------------------------------------------------------


class MetricResult(BaseModel):
    """Self-explaining result for a single evaluation dimension.

    ``score`` is clamped to the [1, 5] range.
    """

    score: int = Field(..., description="Integer score 1-5")
    evidence: list[str] = Field(
        default_factory=list,
        description="Evidence strings found in the README supporting the score",
    )
    missing: list[str] = Field(
        default_factory=list,
        description="Content absent from the README that would improve the score",
    )
    suggestion: str = Field(
        default="",
        description="Actionable suggestion for how to score higher",
    )

    @field_validator("score")
    @classmethod
    def clamp_score(cls, v: int) -> int:
        """Clamp score to [1, 5] range."""
        if v < 1:
            return 1
        if v > 5:
            return 5
        return v


# ---------------------------------------------------------------------------
# EvalResult — complete evaluation output
# ---------------------------------------------------------------------------


class HealthSignals(BaseModel):
    """Heuristic health signals (computed locally, not by LLM)."""

    freshness: float = Field(0.0, ge=0, le=100)
    popularity: float = Field(0.0, ge=0, le=100)
    source_trust: float = Field(0.0, ge=0, le=100)


class EnrichmentData(BaseModel):
    """Enrichment fields produced alongside evaluation metrics in a single LLM call."""

    summary: str = Field("", description="Concise English summary (≤150 chars)")
    summary_zh: str = Field("", description="Concise Chinese summary (≤100 chars)")
    tags: list[str] = Field(default_factory=list, description="3-5 lowercase kebab-case tags")
    tech_stack: list[str] = Field(default_factory=list, description="Languages/frameworks/tools")
    search_terms: list[str] = Field(default_factory=list, description="3-5 bilingual search terms")
    highlights: list[str] = Field(default_factory=list, description="2-3 Chinese feature highlights (≤60 chars each)")

    @field_validator("summary")
    @classmethod
    def truncate_summary(cls, v: str) -> str:
        return v[:150] if len(v) > 150 else v

    @field_validator("summary_zh")
    @classmethod
    def truncate_summary_zh(cls, v: str) -> str:
        return v[:100] if len(v) > 100 else v

    @field_validator("highlights")
    @classmethod
    def truncate_highlights(cls, v: list[str]) -> list[str]:
        return [h[:60] for h in v[:3]]

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, v: list[str]) -> list[str]:
        return [t.lower().strip() for t in v[:5]]


class EvalResult(BaseModel):
    """Complete evaluation result for one catalog entry."""

    entry_id: str
    metrics: dict[str, MetricResult] = Field(
        default_factory=dict,
        description="Keyed by dimension name (e.g. 'coding_relevance')",
    )
    enrichment: EnrichmentData | None = Field(
        None,
        description="Enrichment fields from single LLM call (optional)",
    )
    health: HealthSignals = Field(default_factory=HealthSignals)
    llm_score: float | None = Field(
        None,
        ge=0,
        le=100,
        description="LLM-only weighted score before health blending (0-100)",
    )
    final_score: float = Field(
        ...,
        ge=0,
        le=100,
        description="Blended score (LLM × α + health × (1-α)), 0-100",
    )
    decision: Decision
    star_weight: float = Field(
        1.0,
        description="0.0 if star noise detected, else 1.0",
    )
    content_hash: str | None = Field(
        None,
        description="SHA-256 of the content used for evaluation",
    )
    rubric_version: str | None = Field(
        None,
        description='Format: "{major}.{sha8}"',
    )
    model_id: str | None = None
    evaluated_at: datetime | None = None

    @field_validator("star_weight")
    @classmethod
    def validate_star_weight(cls, v: float) -> float:
        """star_weight must be 0.0 or 1.0."""
        if v not in (0.0, 1.0):
            raise ValueError("star_weight must be 0.0 or 1.0")
        return v


# ---------------------------------------------------------------------------
# TaskConfig — YAML task configuration
# ---------------------------------------------------------------------------


class MetricWeight(BaseModel):
    """A single metric with its weight in the task configuration."""

    metric: str
    weight: float = Field(..., gt=0, le=1)


class HeuristicSignalWeight(BaseModel):
    """A single heuristic signal with its weight."""

    signal: str
    weight: float = Field(..., gt=0, le=1)


class StarRoutingConfig(BaseModel):
    """Star noise routing configuration."""

    zero_weight_sources: list[str] = Field(default_factory=list)
    monorepo_threshold: int = Field(5, ge=1)


class ThresholdsConfig(BaseModel):
    """Decision thresholds for accept/review/reject."""

    accept: float = Field(65, ge=0, le=100)
    review: float = Field(40, ge=0, le=100)

    @model_validator(mode="after")
    def accept_above_review(self) -> ThresholdsConfig:
        if self.accept <= self.review:
            raise ValueError(
                f"accept threshold ({self.accept}) must be greater than "
                f"review threshold ({self.review})"
            )
        return self


class TaskConfig(BaseModel):
    """Parsed YAML task configuration.

    Validates that metric weights and heuristic signal weights each sum to 1.0
    (tolerance ±0.001).
    """

    task: str
    content_source: ContentSource = ContentSource.readme
    content_paths: list[str] = Field(default_factory=lambda: ["README.md"])
    content_fallback: str = "description"

    metrics: list[MetricWeight]
    heuristic_signals: list[HeuristicSignalWeight] = Field(default_factory=list)

    star_routing: StarRoutingConfig = Field(default_factory=StarRoutingConfig)
    thresholds: ThresholdsConfig = Field(default_factory=ThresholdsConfig)
    rubric_major_version: int = Field(1, ge=1)
    health_blend_alpha: float = Field(
        0.85,
        ge=0,
        le=1,
        description="Blend ratio: final = α × llm_score + (1-α) × health_score",
    )
    enrichment: bool = Field(
        True,
        description="When true, LLM prompt includes enrichment section for tags/summary/etc.",
    )

    @model_validator(mode="after")
    def validate_weights(self) -> TaskConfig:
        """Ensure metric weights and heuristic signal weights each sum to 1.0."""
        metric_sum = sum(m.weight for m in self.metrics)
        if abs(metric_sum - 1.0) > 0.001:
            raise ValueError(
                f"Metric weights must sum to 1.0 (±0.001), got {metric_sum:.4f}"
            )

        if self.heuristic_signals:
            signal_sum = sum(s.weight for s in self.heuristic_signals)
            if abs(signal_sum - 1.0) > 0.001:
                raise ValueError(
                    f"Heuristic signal weights must sum to 1.0 (±0.001), got {signal_sum:.4f}"
                )

        return self
