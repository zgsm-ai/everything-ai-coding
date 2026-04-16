"""Tests for ai_resource_eval.api.types Pydantic models."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_resource_eval.api.types import (
    ContentSource,
    Decision,
    EnrichmentData,
    EvalItem,
    EvalResult,
    HealthSignals,
    HeuristicSignalWeight,
    MetricResult,
    MetricWeight,
    StarRoutingConfig,
    TaskConfig,
    ThresholdsConfig,
)

FIXTURES = Path(__file__).parent / "fixtures"


# ===================================================================
# EvalItem
# ===================================================================


class TestEvalItem:
    """Tests for EvalItem catalog entry model."""

    def test_minimal(self):
        item = EvalItem(id="test-id", name="test/name")
        assert item.id == "test-id"
        assert item.name == "test/name"
        assert item.stars is None
        assert item.tags == []

    def test_full_fields(self):
        item = EvalItem(
            id="abc",
            name="org/repo",
            type="mcp",
            description="A cool tool",
            source_url="https://github.com/org/repo",
            stars=1234,
            pushed_at="2026-03-30T17:17:56Z",
            category="ai-ml",
            tags=["tag1", "tag2"],
            tech_stack=["python"],
            install={"method": "manual"},
            source="awesome-mcp-zh",
            last_synced="2026-04-13",
            added_at="2026-03-30",
        )
        assert item.type == "mcp"
        assert item.stars == 1234
        assert len(item.tags) == 2

    def test_extra_fields_allowed(self):
        """EvalItem should accept unknown fields from the catalog."""
        item = EvalItem(
            id="x",
            name="x/y",
            some_future_field="hello",
            another_field=42,
        )
        assert item.id == "x"
        # Extra fields accessible via model_extra
        assert item.model_extra["some_future_field"] == "hello"

    def test_from_catalog_fixture(self):
        """EvalItem should parse real catalog entries without errors."""
        with open(FIXTURES / "catalog_sample.json") as f:
            catalog = json.load(f)
        assert len(catalog) > 0
        for raw in catalog:
            item = EvalItem(**raw)
            assert item.id
            assert item.name

    def test_pushed_at_datetime(self):
        item = EvalItem(
            id="t",
            name="t/t",
            pushed_at=datetime(2026, 3, 30, tzinfo=timezone.utc),
        )
        assert isinstance(item.pushed_at, datetime)

    def test_pushed_at_string(self):
        item = EvalItem(id="t", name="t/t", pushed_at="2026-03-30T17:17:56Z")
        # Should accept string as-is (Union[datetime, str, None])
        assert item.pushed_at is not None


# ===================================================================
# MetricResult
# ===================================================================


class TestMetricResult:
    """Tests for MetricResult self-explaining metric output."""

    def test_basic(self):
        r = MetricResult(
            score=4,
            evidence=["Has install section"],
            missing=["No API reference"],
            suggestion="Add API docs",
        )
        assert r.score == 4
        assert len(r.evidence) == 1
        assert len(r.missing) == 1
        assert r.suggestion == "Add API docs"

    def test_score_clamp_low(self):
        """Scores below 1 should be clamped to 1."""
        r = MetricResult(score=0)
        assert r.score == 1

    def test_score_clamp_negative(self):
        r = MetricResult(score=-5)
        assert r.score == 1

    def test_score_clamp_high(self):
        """Scores above 5 should be clamped to 5."""
        r = MetricResult(score=10)
        assert r.score == 5

    def test_score_boundaries(self):
        """Boundary values 1 and 5 should be accepted as-is."""
        assert MetricResult(score=1).score == 1
        assert MetricResult(score=5).score == 5

    def test_score_in_range(self):
        for v in (1, 2, 3, 4, 5):
            assert MetricResult(score=v).score == v

    def test_defaults(self):
        r = MetricResult(score=3)
        assert r.evidence == []
        assert r.missing == []
        assert r.suggestion == ""


# ===================================================================
# HealthSignals
# ===================================================================


class TestHealthSignals:
    """Tests for HealthSignals model."""

    def test_defaults(self):
        h = HealthSignals()
        assert h.freshness == 0.0
        assert h.popularity == 0.0
        assert h.source_trust == 0.0

    def test_valid_range(self):
        h = HealthSignals(freshness=100, popularity=50, source_trust=0)
        assert h.freshness == 100
        assert h.popularity == 50

    def test_out_of_range(self):
        with pytest.raises(ValidationError):
            HealthSignals(freshness=101)
        with pytest.raises(ValidationError):
            HealthSignals(popularity=-1)


# ===================================================================
# EnrichmentData
# ===================================================================


class TestEnrichmentData:
    """Tests for EnrichmentData enrichment output model."""

    def test_all_fields(self):
        e = EnrichmentData(
            summary="A tool for database access",
            summary_zh="数据库访问工具",
            tags=["mcp-server", "database"],
            tech_stack=["python", "fastapi"],
            search_terms=["database", "数据库"],
            highlights=["支持 15+ 数据库类型", "Docker 一键部署"],
        )
        assert e.summary == "A tool for database access"
        assert e.summary_zh == "数据库访问工具"
        assert len(e.tags) == 2
        assert len(e.highlights) == 2

    def test_defaults(self):
        e = EnrichmentData()
        assert e.summary == ""
        assert e.summary_zh == ""
        assert e.tags == []
        assert e.tech_stack == []
        assert e.search_terms == []
        assert e.highlights == []

    def test_partial_fields(self):
        e = EnrichmentData(summary="test", tags=["a"])
        assert e.summary == "test"
        assert e.tags == ["a"]
        assert e.tech_stack == []

    def test_serialization_roundtrip(self):
        e = EnrichmentData(
            summary="test",
            summary_zh="测试",
            tags=["a", "b"],
            tech_stack=["python"],
            search_terms=["test", "测试"],
            highlights=["亮点一"],
        )
        data = e.model_dump()
        e2 = EnrichmentData.model_validate(data)
        assert e == e2


# ===================================================================
# EvalResult
# ===================================================================


class TestEvalResult:
    """Tests for EvalResult complete evaluation output."""

    def _make_result(self, **overrides) -> EvalResult:
        defaults = dict(
            entry_id="test-id",
            metrics={
                "coding_relevance": MetricResult(score=4, evidence=["relevant"]),
            },
            final_score=72.0,
            decision=Decision.accept,
        )
        defaults.update(overrides)
        return EvalResult(**defaults)

    def test_basic(self):
        r = self._make_result()
        assert r.entry_id == "test-id"
        assert r.final_score == 72.0
        assert r.decision == Decision.accept
        assert r.star_weight == 1.0

    def test_final_score_range(self):
        with pytest.raises(ValidationError):
            self._make_result(final_score=-1)
        with pytest.raises(ValidationError):
            self._make_result(final_score=101)

    def test_star_weight_valid(self):
        r = self._make_result(star_weight=0.0)
        assert r.star_weight == 0.0
        r = self._make_result(star_weight=1.0)
        assert r.star_weight == 1.0

    def test_star_weight_invalid(self):
        with pytest.raises(ValidationError, match="star_weight must be 0.0 or 1.0"):
            self._make_result(star_weight=0.5)

    def test_decision_enum(self):
        for d in Decision:
            r = self._make_result(decision=d)
            assert r.decision == d

    def test_decision_from_string(self):
        r = self._make_result(decision="review")
        assert r.decision == Decision.review

    def test_content_hash_optional(self):
        r = self._make_result()
        assert r.content_hash is None

    def test_content_hash_set(self):
        h = "a" * 64
        r = self._make_result(content_hash=h)
        assert r.content_hash == h

    def test_multiple_metrics(self):
        metrics = {
            "coding_relevance": MetricResult(score=5),
            "doc_completeness": MetricResult(score=3),
            "install_clarity": MetricResult(score=2),
        }
        r = self._make_result(metrics=metrics)
        assert len(r.metrics) == 3
        assert r.metrics["doc_completeness"].score == 3

    def test_enrichment_none_by_default(self):
        r = self._make_result()
        assert r.enrichment is None

    def test_enrichment_present(self):
        enrichment = EnrichmentData(
            summary="test",
            summary_zh="测试",
            tags=["a"],
        )
        r = self._make_result(enrichment=enrichment)
        assert r.enrichment is not None
        assert r.enrichment.summary == "test"

    def test_enrichment_none_explicit(self):
        r = self._make_result(enrichment=None)
        assert r.enrichment is None

    def test_backward_compat_no_enrichment_key(self):
        """Old cached results without enrichment key should deserialize fine."""
        data = {
            "entry_id": "test",
            "metrics": {},
            "final_score": 50.0,
            "decision": "review",
        }
        r = EvalResult.model_validate(data)
        assert r.enrichment is None


# ===================================================================
# TaskConfig
# ===================================================================


def _valid_metrics() -> list[dict]:
    return [
        {"metric": "coding_relevance", "weight": 0.25},
        {"metric": "doc_completeness", "weight": 0.20},
        {"metric": "desc_accuracy", "weight": 0.15},
        {"metric": "writing_quality", "weight": 0.15},
        {"metric": "specificity", "weight": 0.15},
        {"metric": "install_clarity", "weight": 0.10},
    ]


def _valid_signals() -> list[dict]:
    return [
        {"signal": "freshness", "weight": 0.30},
        {"signal": "popularity", "weight": 0.30},
        {"signal": "source_trust", "weight": 0.40},
    ]


class TestTaskConfig:
    """Tests for TaskConfig YAML task configuration model."""

    def test_full_config(self):
        cfg = TaskConfig(
            task="skill",
            content_source="readme",
            content_paths=["SKILL.md", "README.md"],
            content_fallback="description",
            metrics=_valid_metrics(),
            heuristic_signals=_valid_signals(),
            star_routing=StarRoutingConfig(
                zero_weight_sources=["antigravity-skills", "davila7/*"],
                monorepo_threshold=5,
            ),
            thresholds=ThresholdsConfig(accept=65, review=40),
            rubric_major_version=1,
        )
        assert cfg.task == "skill"
        assert cfg.content_source == ContentSource.readme
        assert len(cfg.metrics) == 6
        assert len(cfg.heuristic_signals) == 3
        assert cfg.thresholds.accept == 65
        assert cfg.thresholds.review == 40
        assert cfg.rubric_major_version == 1

    def test_metric_weights_must_sum_to_one(self):
        bad_metrics = [
            {"metric": "coding_relevance", "weight": 0.50},
            {"metric": "doc_completeness", "weight": 0.20},
        ]
        with pytest.raises(ValidationError, match="Metric weights must sum to 1.0"):
            TaskConfig(task="test", metrics=bad_metrics)

    def test_metric_weights_tolerance(self):
        """Weights summing to 1.0 within ±0.001 tolerance should be accepted."""
        # These sum to 1.0005 which is within tolerance
        metrics = [
            {"metric": "a", "weight": 0.3334},
            {"metric": "b", "weight": 0.3333},
            {"metric": "c", "weight": 0.3338},
        ]
        cfg = TaskConfig(task="test", metrics=metrics)
        assert len(cfg.metrics) == 3

    def test_metric_weights_outside_tolerance(self):
        """Weights off by more than 0.001 should fail."""
        metrics = [
            {"metric": "a", "weight": 0.33},
            {"metric": "b", "weight": 0.33},
            {"metric": "c", "weight": 0.33},
        ]
        with pytest.raises(ValidationError, match="Metric weights must sum to 1.0"):
            TaskConfig(task="test", metrics=metrics)

    def test_signal_weights_must_sum_to_one(self):
        bad_signals = [
            {"signal": "freshness", "weight": 0.50},
            {"signal": "popularity", "weight": 0.20},
        ]
        with pytest.raises(
            ValidationError, match="Heuristic signal weights must sum to 1.0"
        ):
            TaskConfig(
                task="test",
                metrics=_valid_metrics(),
                heuristic_signals=bad_signals,
            )

    def test_no_signals_is_valid(self):
        """A task config with no heuristic signals should be valid."""
        cfg = TaskConfig(task="test", metrics=_valid_metrics())
        assert cfg.heuristic_signals == []

    def test_defaults(self):
        cfg = TaskConfig(task="test", metrics=_valid_metrics())
        assert cfg.content_source == ContentSource.readme
        assert cfg.content_paths == ["README.md"]
        assert cfg.content_fallback == "description"
        assert cfg.thresholds.accept == 65
        assert cfg.thresholds.review == 40
        assert cfg.rubric_major_version == 1

    def test_thresholds_accept_above_review(self):
        with pytest.raises(ValidationError, match="accept threshold.*must be greater"):
            ThresholdsConfig(accept=40, review=65)

    def test_thresholds_equal_invalid(self):
        with pytest.raises(ValidationError, match="accept threshold.*must be greater"):
            ThresholdsConfig(accept=50, review=50)

    def test_star_routing_defaults(self):
        sr = StarRoutingConfig()
        assert sr.zero_weight_sources == []
        assert sr.monorepo_threshold == 5

    def test_metric_weight_zero_invalid(self):
        """Individual metric weight must be > 0."""
        with pytest.raises(ValidationError):
            MetricWeight(metric="test", weight=0.0)

    def test_metric_weight_over_one_invalid(self):
        """Individual metric weight must be <= 1."""
        with pytest.raises(ValidationError):
            MetricWeight(metric="test", weight=1.5)

    def test_enrichment_default_true(self):
        cfg = TaskConfig(task="test", metrics=_valid_metrics())
        assert cfg.enrichment is True

    def test_enrichment_explicit_false(self):
        cfg = TaskConfig(task="test", metrics=_valid_metrics(), enrichment=False)
        assert cfg.enrichment is False
