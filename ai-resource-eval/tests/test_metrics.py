"""Tests for ai_resource_eval.metrics — rubrics, prompt builder, and output parsing."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from ai_resource_eval.api.metric import BaseMetric
from ai_resource_eval.api.types import MetricResult
from ai_resource_eval.metrics.coding_relevance import CodingRelevance
from ai_resource_eval.metrics.doc_completeness import DocCompleteness
from ai_resource_eval.metrics.desc_accuracy import DescAccuracy
from ai_resource_eval.metrics.writing_quality import WritingQuality
from ai_resource_eval.metrics.specificity import Specificity
from ai_resource_eval.metrics.install_clarity import InstallClarity
from ai_resource_eval.metrics.prompt_builder import (
    LLMEvalResponse,
    build_output_schema,
    build_system_prompt,
    metric_registry,
)


# ===================================================================
# Metric class inventory — parametrised over all six dimensions
# ===================================================================

ALL_METRIC_CLASSES: list[tuple[type[BaseMetric], str]] = [
    (CodingRelevance, "coding_relevance"),
    (DocCompleteness, "doc_completeness"),
    (DescAccuracy, "desc_accuracy"),
    (WritingQuality, "writing_quality"),
    (Specificity, "specificity"),
    (InstallClarity, "install_clarity"),
]


@pytest.fixture(params=ALL_METRIC_CLASSES, ids=[n for _, n in ALL_METRIC_CLASSES])
def metric_pair(request):
    """Yield (metric_instance, expected_name) for each dimension."""
    cls, expected_name = request.param
    return cls(), expected_name


# ===================================================================
# 7.1-7.6  Individual metric properties
# ===================================================================


class TestMetricProperties:
    """Each metric must have a valid name, require content, and produce a non-empty rubric."""

    def test_name_matches(self, metric_pair):
        metric, expected_name = metric_pair
        assert metric.name == expected_name

    def test_requires_content_is_true(self, metric_pair):
        metric, _ = metric_pair
        assert metric.requires_content is True

    def test_rubric_is_non_empty_string(self, metric_pair):
        metric, _ = metric_pair
        rubric = metric.build_rubric()
        assert isinstance(rubric, str)
        assert len(rubric) > 0

    def test_rubric_contains_score_anchors(self, metric_pair):
        """Rubric must describe all five score levels."""
        metric, _ = metric_pair
        rubric = metric.build_rubric()
        for level in ("1", "2", "3", "4", "5"):
            assert f"**{level}" in rubric, f"Missing anchor for score {level}"

    def test_rubric_mentions_output_fields(self, metric_pair):
        """Rubric must remind the LLM about the required output fields."""
        metric, _ = metric_pair
        rubric = metric.build_rubric()
        for field in ("score", "evidence", "missing", "suggestion"):
            assert field in rubric, f"Rubric does not mention '{field}'"

    def test_default_weight_is_one(self, metric_pair):
        metric, _ = metric_pair
        assert metric.weight == 1.0

    def test_custom_weight(self):
        metric = CodingRelevance(weight=0.3)
        assert metric.weight == pytest.approx(0.3)

    def test_negative_weight_raises(self):
        with pytest.raises(ValueError, match="non-negative"):
            CodingRelevance(weight=-0.1)

    def test_inherits_base_metric(self, metric_pair):
        metric, _ = metric_pair
        assert isinstance(metric, BaseMetric)


# ===================================================================
# 7.7  Prompt builder
# ===================================================================


class TestBuildSystemPrompt:
    """Tests for build_system_prompt()."""

    def test_contains_all_rubrics(self):
        metrics = [cls() for cls, _ in ALL_METRIC_CLASSES]
        prompt = build_system_prompt(metrics)
        for _, name in ALL_METRIC_CLASSES:
            assert name in prompt, f"Prompt missing rubric for '{name}'"

    def test_contains_preamble(self):
        metrics = [CodingRelevance()]
        prompt = build_system_prompt(metrics)
        assert "expert evaluator" in prompt
        assert "JSON" in prompt

    def test_empty_metrics_returns_preamble_only(self):
        prompt = build_system_prompt([])
        assert "expert evaluator" in prompt
        # No dimension-specific content
        for _, name in ALL_METRIC_CLASSES:
            assert name not in prompt

    def test_prompt_is_string(self):
        metrics = [CodingRelevance(), DocCompleteness()]
        prompt = build_system_prompt(metrics)
        assert isinstance(prompt, str)
        assert len(prompt) > 100

    def test_enrichment_false_no_enrichment_section(self):
        metrics = [CodingRelevance()]
        prompt = build_system_prompt(metrics, enrichment=False)
        assert "Enrichment Fields" not in prompt

    def test_enrichment_true_has_enrichment_section(self):
        metrics = [CodingRelevance()]
        prompt = build_system_prompt(metrics, enrichment=True)
        assert "Enrichment Fields" in prompt
        assert "summary" in prompt
        assert "summary_zh" in prompt
        assert "tags" in prompt
        assert "tech_stack" in prompt
        assert "search_terms" in prompt
        assert "highlights" in prompt

    def test_enrichment_default_false(self):
        """Default enrichment=False for backward compatibility."""
        metrics = [CodingRelevance()]
        prompt = build_system_prompt(metrics)
        assert "Enrichment Fields" not in prompt


class TestBuildOutputSchema:
    """Tests for build_output_schema()."""

    def test_schema_has_metrics_key(self):
        schema = build_output_schema(["coding_relevance"])
        assert "metrics" in schema["properties"]

    def test_schema_requires_all_dimensions(self):
        names = [name for _, name in ALL_METRIC_CLASSES]
        schema = build_output_schema(names)
        required = schema["properties"]["metrics"]["required"]
        assert set(required) == set(names)

    def test_schema_is_json_serialisable(self):
        names = [name for _, name in ALL_METRIC_CLASSES]
        schema = build_output_schema(names)
        # Must not raise
        json_str = json.dumps(schema)
        assert isinstance(json_str, str)

    def test_schema_references_metric_result(self):
        schema = build_output_schema(["coding_relevance"])
        props = schema["properties"]["metrics"]["properties"]
        assert "$ref" in props["coding_relevance"]
        assert "MetricResult" in props["coding_relevance"]["$ref"]

    def test_schema_no_enrichment_by_default(self):
        schema = build_output_schema(["coding_relevance"])
        assert "enrichment" not in schema["properties"]
        assert "enrichment" not in schema["required"]

    def test_schema_with_enrichment(self):
        schema = build_output_schema(["coding_relevance"], enrichment=True)
        assert "enrichment" in schema["properties"]
        assert "enrichment" in schema["required"]
        assert "EnrichmentData" in schema["$defs"]

    def test_schema_with_enrichment_is_json_serialisable(self):
        schema = build_output_schema(["coding_relevance"], enrichment=True)
        json_str = json.dumps(schema)
        assert isinstance(json_str, str)


# ===================================================================
# 7.7  Metric registry
# ===================================================================


class TestMetricRegistry:
    """Tests for the default metric_registry."""

    def test_registry_has_six_metrics(self):
        assert len(metric_registry) == 6

    def test_all_names_registered(self):
        for _, name in ALL_METRIC_CLASSES:
            assert name in metric_registry

    def test_get_returns_correct_type(self):
        metric = metric_registry.get("coding_relevance")
        assert isinstance(metric, CodingRelevance)


# ===================================================================
# 7.8  Mock LLM response parsing
# ===================================================================


class TestLLMEvalResponse:
    """Validate that mock LLM JSON output parses correctly via Pydantic."""

    @pytest.fixture
    def mock_response_data(self) -> dict:
        """A well-formed mock LLM response covering all six dimensions."""
        dimensions = [name for _, name in ALL_METRIC_CLASSES]
        metrics = {}
        for i, dim in enumerate(dimensions, start=1):
            metrics[dim] = {
                "score": min(i, 5),
                "evidence": [f"Found {dim}-related content in README"],
                "missing": [f"Could add more {dim} detail"],
                "suggestion": f"Improve {dim} by adding examples.",
            }
        return {"metrics": metrics}

    def test_parse_valid_response(self, mock_response_data):
        resp = LLMEvalResponse.model_validate(mock_response_data)
        assert len(resp.metrics) == 6
        for _, name in ALL_METRIC_CLASSES:
            assert name in resp.metrics
            result = resp.metrics[name]
            assert isinstance(result, MetricResult)
            assert 1 <= result.score <= 5

    def test_score_clamped_to_range(self):
        """MetricResult clamps score to [1, 5]."""
        data = {
            "metrics": {
                "coding_relevance": {
                    "score": 10,
                    "evidence": [],
                    "missing": [],
                    "suggestion": "",
                },
            },
        }
        resp = LLMEvalResponse.model_validate(data)
        assert resp.metrics["coding_relevance"].score == 5

    def test_score_below_one_clamped(self):
        data = {
            "metrics": {
                "coding_relevance": {
                    "score": 0,
                    "evidence": [],
                    "missing": [],
                    "suggestion": "",
                },
            },
        }
        resp = LLMEvalResponse.model_validate(data)
        assert resp.metrics["coding_relevance"].score == 1

    def test_missing_score_raises(self):
        data = {
            "metrics": {
                "coding_relevance": {
                    "evidence": ["some text"],
                    "missing": [],
                    "suggestion": "",
                },
            },
        }
        with pytest.raises(ValidationError):
            LLMEvalResponse.model_validate(data)

    def test_empty_metrics_allowed(self):
        """An empty metrics dict is structurally valid (no dimensions evaluated)."""
        data = {"metrics": {}}
        resp = LLMEvalResponse.model_validate(data)
        assert resp.metrics == {}

    def test_missing_metrics_key_raises(self):
        with pytest.raises(ValidationError):
            LLMEvalResponse.model_validate({})

    def test_extra_fields_in_metric_result_ignored(self):
        """MetricResult should tolerate extra fields from LLM output."""
        data = {
            "metrics": {
                "coding_relevance": {
                    "score": 4,
                    "evidence": ["good coverage"],
                    "missing": [],
                    "suggestion": "Add more examples",
                    "confidence": 0.95,  # extra field
                },
            },
        }
        # Should not raise — Pydantic defaults to ignoring extra fields
        resp = LLMEvalResponse.model_validate(data)
        assert resp.metrics["coding_relevance"].score == 4

    def test_round_trip_json_serialisation(self, mock_response_data):
        """Validate → serialise → deserialise → validate round trip."""
        resp = LLMEvalResponse.model_validate(mock_response_data)
        json_str = resp.model_dump_json()
        resp2 = LLMEvalResponse.model_validate_json(json_str)
        assert resp == resp2

    def test_enrichment_none_by_default(self, mock_response_data):
        resp = LLMEvalResponse.model_validate(mock_response_data)
        assert resp.enrichment is None

    def test_enrichment_parsed(self, mock_response_data):
        mock_response_data["enrichment"] = {
            "summary": "A great tool",
            "summary_zh": "很棒的工具",
            "tags": ["tool"],
            "tech_stack": ["python"],
            "search_terms": ["tool", "工具"],
            "highlights": ["功能强大"],
        }
        resp = LLMEvalResponse.model_validate(mock_response_data)
        assert resp.enrichment is not None
        assert resp.enrichment.summary == "A great tool"
        assert resp.enrichment.tags == ["tool"]
