"""Tests for task YAML configurations and the task config loader."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_resource_eval.api.types import TaskConfig
from ai_resource_eval.tasks.loader import (
    list_available_tasks,
    load_task_config,
    load_task_config_from_path,
)

# All known metric names from the metrics/ package.
VALID_METRIC_NAMES = {
    "coding_relevance",
    "doc_completeness",
    "desc_accuracy",
    "writing_quality",
    "specificity",
    "install_clarity",
}

# All known heuristic signal names.
VALID_SIGNAL_NAMES = {
    "freshness",
    "popularity",
    "source_trust",
}

# All 4 built-in task types.
ALL_TASK_NAMES = ["mcp_server", "skill", "rule", "prompt"]


# ===================================================================
# Schema validation for all 4 YAML files
# ===================================================================


class TestAllYamlFilesValid:
    """Each built-in YAML file must parse into a valid TaskConfig."""

    @pytest.mark.parametrize("task_name", ALL_TASK_NAMES)
    def test_yaml_loads_without_error(self, task_name: str):
        """YAML file parses and validates as TaskConfig."""
        cfg = load_task_config(task_name)
        assert isinstance(cfg, TaskConfig)
        assert cfg.task == task_name

    @pytest.mark.parametrize("task_name", ALL_TASK_NAMES)
    def test_content_source_is_readme(self, task_name: str):
        cfg = load_task_config(task_name)
        assert cfg.content_source.value == "readme"

    @pytest.mark.parametrize("task_name", ALL_TASK_NAMES)
    def test_content_fallback_is_description(self, task_name: str):
        cfg = load_task_config(task_name)
        assert cfg.content_fallback == "description"

    @pytest.mark.parametrize("task_name", ALL_TASK_NAMES)
    def test_rubric_major_version(self, task_name: str):
        cfg = load_task_config(task_name)
        assert cfg.rubric_major_version == 1


# ===================================================================
# Weights sum to 1.0
# ===================================================================


class TestWeightsSumToOne:
    """Metric weights and heuristic signal weights must each sum to 1.0."""

    @pytest.mark.parametrize("task_name", ALL_TASK_NAMES)
    def test_metric_weights_sum_to_one(self, task_name: str):
        cfg = load_task_config(task_name)
        total = sum(m.weight for m in cfg.metrics)
        assert abs(total - 1.0) < 0.001, (
            f"{task_name}: metric weights sum to {total:.4f}, expected 1.0"
        )

    @pytest.mark.parametrize("task_name", ALL_TASK_NAMES)
    def test_heuristic_signal_weights_sum_to_one(self, task_name: str):
        cfg = load_task_config(task_name)
        assert len(cfg.heuristic_signals) > 0
        total = sum(s.weight for s in cfg.heuristic_signals)
        assert abs(total - 1.0) < 0.001, (
            f"{task_name}: signal weights sum to {total:.4f}, expected 1.0"
        )


# ===================================================================
# Metric names are valid
# ===================================================================


class TestMetricNamesValid:
    """All metric names referenced in YAML must be known metric names."""

    @pytest.mark.parametrize("task_name", ALL_TASK_NAMES)
    def test_metric_names_are_valid(self, task_name: str):
        cfg = load_task_config(task_name)
        for mw in cfg.metrics:
            assert mw.metric in VALID_METRIC_NAMES, (
                f"{task_name}: unknown metric {mw.metric!r}"
            )

    @pytest.mark.parametrize("task_name", ALL_TASK_NAMES)
    def test_signal_names_are_valid(self, task_name: str):
        cfg = load_task_config(task_name)
        for sw in cfg.heuristic_signals:
            assert sw.signal in VALID_SIGNAL_NAMES, (
                f"{task_name}: unknown signal {sw.signal!r}"
            )

    @pytest.mark.parametrize("task_name", ALL_TASK_NAMES)
    def test_no_duplicate_metrics(self, task_name: str):
        cfg = load_task_config(task_name)
        names = [m.metric for m in cfg.metrics]
        assert len(names) == len(set(names)), (
            f"{task_name}: duplicate metric names found"
        )


# ===================================================================
# Type-specific metric sets
# ===================================================================


class TestTypeSpecificMetrics:
    """Verify each type has the expected set of metrics."""

    def test_mcp_server_has_all_6_metrics(self):
        cfg = load_task_config("mcp_server")
        metric_names = {m.metric for m in cfg.metrics}
        assert metric_names == VALID_METRIC_NAMES

    def test_skill_has_all_6_metrics(self):
        cfg = load_task_config("skill")
        metric_names = {m.metric for m in cfg.metrics}
        assert metric_names == VALID_METRIC_NAMES

    def test_rule_has_no_install_clarity(self):
        cfg = load_task_config("rule")
        metric_names = {m.metric for m in cfg.metrics}
        assert "install_clarity" not in metric_names
        assert metric_names == VALID_METRIC_NAMES - {"install_clarity"}

    def test_prompt_has_no_install_clarity_or_doc_completeness(self):
        cfg = load_task_config("prompt")
        metric_names = {m.metric for m in cfg.metrics}
        assert "install_clarity" not in metric_names
        assert "doc_completeness" not in metric_names
        assert metric_names == VALID_METRIC_NAMES - {
            "install_clarity",
            "doc_completeness",
        }


# ===================================================================
# Type-specific content_paths
# ===================================================================


class TestContentPaths:
    """Verify content_paths per type."""

    def test_mcp_server_content_paths(self):
        cfg = load_task_config("mcp_server")
        assert cfg.content_paths == ["README.md"]

    def test_skill_content_paths(self):
        cfg = load_task_config("skill")
        assert cfg.content_paths == ["SKILL.md", "README.md"]

    def test_rule_content_paths(self):
        cfg = load_task_config("rule")
        assert cfg.content_paths == ["README.md"]

    def test_prompt_content_paths(self):
        cfg = load_task_config("prompt")
        assert cfg.content_paths == ["README.md"]


# ===================================================================
# Star routing config is consistent
# ===================================================================


class TestStarRouting:
    """All 4 configs share the same star_routing."""

    @pytest.mark.parametrize("task_name", ALL_TASK_NAMES)
    def test_star_routing_has_zero_weight_sources(self, task_name: str):
        cfg = load_task_config(task_name)
        assert len(cfg.star_routing.zero_weight_sources) > 0

    @pytest.mark.parametrize("task_name", ALL_TASK_NAMES)
    def test_star_routing_monorepo_threshold(self, task_name: str):
        cfg = load_task_config(task_name)
        assert cfg.star_routing.monorepo_threshold == 5

    def test_all_configs_share_same_star_routing(self):
        configs = [load_task_config(name) for name in ALL_TASK_NAMES]
        sources_sets = [
            tuple(sorted(c.star_routing.zero_weight_sources)) for c in configs
        ]
        assert len(set(sources_sets)) == 1, "All configs should share the same zero_weight_sources"

    def test_all_configs_share_same_heuristic_signals(self):
        configs = [load_task_config(name) for name in ALL_TASK_NAMES]
        signal_tuples = [
            tuple((s.signal, s.weight) for s in c.heuristic_signals)
            for c in configs
        ]
        assert len(set(signal_tuples)) == 1, "All configs should share the same heuristic_signals"


# ===================================================================
# Thresholds
# ===================================================================


class TestThresholds:
    """All configs should have valid thresholds."""

    @pytest.mark.parametrize("task_name", ALL_TASK_NAMES)
    def test_accept_above_review(self, task_name: str):
        cfg = load_task_config(task_name)
        assert cfg.thresholds.accept > cfg.thresholds.review

    @pytest.mark.parametrize("task_name", ALL_TASK_NAMES)
    def test_default_thresholds(self, task_name: str):
        cfg = load_task_config(task_name)
        assert cfg.thresholds.accept == 65
        assert cfg.thresholds.review == 50


# ===================================================================
# Loader functions
# ===================================================================


class TestLoader:
    """Tests for the loader module functions."""

    def test_load_task_config_valid(self):
        cfg = load_task_config("skill")
        assert cfg.task == "skill"

    def test_load_task_config_not_found(self):
        with pytest.raises(FileNotFoundError, match="No task config found"):
            load_task_config("nonexistent_type")

    def test_load_task_config_from_path(self, tmp_path: Path):
        """Loading from an arbitrary path works."""
        yaml_content = (
            "task: custom\n"
            "metrics:\n"
            "  - metric: coding_relevance\n"
            "    weight: 0.50\n"
            "  - metric: doc_completeness\n"
            "    weight: 0.50\n"
        )
        p = tmp_path / "custom.yaml"
        p.write_text(yaml_content)
        cfg = load_task_config_from_path(p)
        assert cfg.task == "custom"
        assert len(cfg.metrics) == 2

    def test_load_task_config_from_path_not_found(self):
        with pytest.raises(FileNotFoundError, match="Task config file not found"):
            load_task_config_from_path("/nonexistent/path.yaml")

    def test_load_task_config_from_path_invalid_yaml(self, tmp_path: Path):
        """Non-mapping YAML should raise ValueError."""
        p = tmp_path / "bad.yaml"
        p.write_text("- just\n- a\n- list\n")
        with pytest.raises(ValueError, match="Expected a YAML mapping"):
            load_task_config_from_path(p)

    def test_load_task_config_from_path_validation_error(self, tmp_path: Path):
        """Invalid config should raise Pydantic ValidationError."""
        yaml_content = (
            "task: bad\n"
            "metrics:\n"
            "  - metric: a\n"
            "    weight: 0.30\n"
        )
        p = tmp_path / "bad.yaml"
        p.write_text(yaml_content)
        with pytest.raises(ValidationError, match="Metric weights must sum to 1.0"):
            load_task_config_from_path(p)

    def test_list_available_tasks(self):
        tasks = list_available_tasks()
        assert isinstance(tasks, list)
        for name in ALL_TASK_NAMES:
            assert name in tasks
        # Should be sorted
        assert tasks == sorted(tasks)
