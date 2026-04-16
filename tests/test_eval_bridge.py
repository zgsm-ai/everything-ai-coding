"""Tests for eval_bridge — harness ↔ catalog integration."""
import json
import os
import sys
import tempfile
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))


def _make_entries():
    """Minimal catalog entries for testing."""
    return [
        {
            "id": "test-mcp-1",
            "name": "Test MCP Server",
            "type": "mcp",
            "description": "A test MCP server",
            "source_url": "https://github.com/owner/test-mcp",
            "stars": 100,
            "source": "awesome-mcp-servers",
        },
        {
            "id": "test-skill-1",
            "name": "Test Skill",
            "type": "skill",
            "description": "A test skill",
            "source_url": "https://github.com/owner/test-skill",
            "stars": 50,
            "source": "anthropics-skills",
        },
    ]


_SAMPLE_ENRICHMENT = {
    "summary": "A tool for database access via MCP",
    "summary_zh": "通过 MCP 访问数据库的工具",
    "tags": ["mcp-server", "database", "python"],
    "tech_stack": ["python", "fastapi"],
    "search_terms": ["database", "数据库", "MCP server"],
    "highlights": ["支持 15+ 数据库类型", "Docker 一键部署"],
}


def _make_eval_result(entry_id, scores=None, enrichment=None):
    """Create a mock EvalResult-like dict."""
    default_scores = {
        "coding_relevance": 4,
        "doc_completeness": 3,
        "desc_accuracy": 4,
        "writing_quality": 3,
        "specificity": 4,
        "install_clarity": 3,
    }
    s = scores or default_scores
    result = {
        "entry_id": entry_id,
        "metrics": {k: {"score": v, "evidence": [], "missing": [], "suggestion": ""} for k, v in s.items()},
        "health": {"freshness": 80.0, "popularity": 50.0, "source_trust": 70.0},
        "llm_score": 72.0,
        "final_score": 75.0,
        "decision": "accept",
        "star_weight": 1.0,
        "content_hash": "abc123",
        "rubric_version": "1.deadbeef",
        "model_id": "deepseek-chat",
        "evaluated_at": "2026-04-16T00:00:00Z",
    }
    if enrichment is not None:
        result["enrichment"] = enrichment
    return result


class TestMapResultToEntry:
    """Test that eval results map correctly onto catalog entries."""

    def test_scores_are_flattened(self):
        from eval_bridge import map_result_to_entry

        entry = _make_entries()[0]
        result = _make_eval_result("test-mcp-1")
        map_result_to_entry(entry, result)

        ev = entry["evaluation"]
        assert ev["coding_relevance"] == 4
        assert ev["doc_completeness"] == 3
        assert ev["final_score"] == 75.0
        assert ev["decision"] == "accept"
        assert ev["model_id"] == "deepseek-chat"
        assert ev["rubric_version"] == "1.deadbeef"
        # evidence should NOT be in the flattened evaluation
        assert "evidence" not in ev
        assert "missing" not in ev

    def test_health_mapped(self):
        from eval_bridge import map_result_to_entry

        entry = _make_entries()[0]
        result = _make_eval_result("test-mcp-1")
        map_result_to_entry(entry, result)

        assert entry["health"]["signals"]["freshness"] == 80.0
        assert entry["health"]["signals"]["popularity"] == 50.0
        assert "score" in entry["health"]
        assert "freshness_label" in entry["health"]

    def test_top_level_promotion(self):
        from eval_bridge import map_result_to_entry

        entry = _make_entries()[0]
        result = _make_eval_result("test-mcp-1")
        map_result_to_entry(entry, result)

        assert entry["final_score"] == 75.0
        assert entry["decision"] == "accept"

    def test_no_result_preserves_entry(self):
        from eval_bridge import map_result_to_entry

        entry = _make_entries()[0]
        entry["evaluation"] = {"coding_relevance": 2, "final_score": 30, "decision": "review"}
        original_eval = dict(entry["evaluation"])
        map_result_to_entry(entry, None)

        # Entry unchanged when result is None (harness skipped it)
        assert entry["evaluation"] == original_eval


class TestEnrichmentMapping:
    """Test enrichment fields mapping from EvalResult to catalog entry."""

    def test_enrichment_fields_mapped(self):
        from eval_bridge import map_result_to_entry

        entry = _make_entries()[0]
        result = _make_eval_result("test-mcp-1", enrichment=dict(_SAMPLE_ENRICHMENT))
        map_result_to_entry(entry, result)

        assert entry["tags"] == ["mcp-server", "database", "python"]
        assert entry["tech_stack"] == ["python", "fastapi"]
        assert entry["description_zh"] == "通过 MCP 访问数据库的工具"
        assert entry["search_terms"] == ["database", "数据库", "MCP server"]
        assert entry["highlights"] == ["支持 15+ 数据库类型", "Docker 一键部署"]
        assert entry["description"] == "A tool for database access via MCP"

    def test_summary_overwrites_description_and_preserves_original(self):
        from eval_bridge import map_result_to_entry

        entry = _make_entries()[0]
        original_desc = entry["description"]
        result = _make_eval_result("test-mcp-1", enrichment=dict(_SAMPLE_ENRICHMENT))
        map_result_to_entry(entry, result)

        assert entry["description"] == "A tool for database access via MCP"
        assert entry["description_original"] == original_desc

    def test_no_enrichment_preserves_fields(self):
        from eval_bridge import map_result_to_entry

        entry = _make_entries()[0]
        entry["tags"] = ["existing-tag"]
        entry["tech_stack"] = ["go"]
        result = _make_eval_result("test-mcp-1")  # no enrichment
        map_result_to_entry(entry, result)

        assert entry["tags"] == ["existing-tag"]
        assert entry["tech_stack"] == ["go"]

    def test_partial_enrichment(self):
        from eval_bridge import map_result_to_entry

        entry = _make_entries()[0]
        partial = {"summary": "test", "tags": ["a"]}
        result = _make_eval_result("test-mcp-1", enrichment=partial)
        map_result_to_entry(entry, result)

        assert entry["description"] == "test"
        assert entry["tags"] == ["a"]
        # Fields not in enrichment should not be created
        assert "highlights" not in entry

    def test_empty_enrichment_lists_not_mapped(self):
        from eval_bridge import map_result_to_entry

        entry = _make_entries()[0]
        entry["tags"] = ["keep-me"]
        empty_enrichment = {"tags": [], "tech_stack": [], "summary": ""}
        result = _make_eval_result("test-mcp-1", enrichment=empty_enrichment)
        map_result_to_entry(entry, result)

        # Empty lists/strings should not overwrite existing values
        assert entry["tags"] == ["keep-me"]


class TestHealthFormatConversion:
    """Test health signal conversion to README-compatible format."""

    def test_health_format_with_pushed_at(self):
        from eval_bridge import map_result_to_entry

        entry = _make_entries()[0]
        entry["pushed_at"] = "2026-04-05T00:00:00Z"
        result = _make_eval_result("test-mcp-1")
        # health: freshness=80, popularity=50, source_trust=70
        map_result_to_entry(entry, result)

        h = entry["health"]
        assert h["score"] == 67  # round((80+50+70)/3)
        assert h["freshness_label"] == "active"  # 80 > 70
        assert h["last_commit"] == "2026-04-05T00:00:00Z"
        assert h["signals"]["freshness"] == 80.0
        assert h["signals"]["popularity"] == 50.0
        assert h["signals"]["source_trust"] == 70.0

    def test_health_format_without_pushed_at(self):
        from eval_bridge import map_result_to_entry

        entry = _make_entries()[0]
        # No pushed_at
        result = _make_eval_result("test-mcp-1")
        map_result_to_entry(entry, result)

        h = entry["health"]
        assert h["last_commit"] is None

    def test_freshness_label_active(self):
        from eval_bridge import map_result_to_entry

        entry = _make_entries()[0]
        result = _make_eval_result("test-mcp-1")
        result["health"] = {"freshness": 75.0, "popularity": 50.0, "source_trust": 60.0}
        map_result_to_entry(entry, result)
        assert entry["health"]["freshness_label"] == "active"

    def test_freshness_label_stale(self):
        from eval_bridge import map_result_to_entry

        entry = _make_entries()[0]
        result = _make_eval_result("test-mcp-1")
        result["health"] = {"freshness": 50.0, "popularity": 50.0, "source_trust": 60.0}
        map_result_to_entry(entry, result)
        assert entry["health"]["freshness_label"] == "stale"

    def test_freshness_label_abandoned(self):
        from eval_bridge import map_result_to_entry

        entry = _make_entries()[0]
        result = _make_eval_result("test-mcp-1")
        result["health"] = {"freshness": 20.0, "popularity": 10.0, "source_trust": 40.0}
        map_result_to_entry(entry, result)
        assert entry["health"]["freshness_label"] == "abandoned"

    def test_freshness_label_boundary_70(self):
        from eval_bridge import map_result_to_entry

        entry = _make_entries()[0]
        result = _make_eval_result("test-mcp-1")
        result["health"] = {"freshness": 70.0, "popularity": 50.0, "source_trust": 60.0}
        map_result_to_entry(entry, result)
        # 70 is NOT > 70, so it should be "stale"
        assert entry["health"]["freshness_label"] == "stale"

    def test_freshness_label_boundary_30(self):
        from eval_bridge import map_result_to_entry

        entry = _make_entries()[0]
        result = _make_eval_result("test-mcp-1")
        result["health"] = {"freshness": 30.0, "popularity": 50.0, "source_trust": 60.0}
        map_result_to_entry(entry, result)
        # 30 is NOT > 30, so it should be "abandoned"
        assert entry["health"]["freshness_label"] == "abandoned"


class TestResolveTaskName:
    """Test task name resolution for built-in configs."""

    def test_known_types(self):
        from eval_bridge import resolve_task_name

        assert resolve_task_name("mcp") == "mcp_server"
        assert resolve_task_name("skill") == "skill"
        assert resolve_task_name("rule") == "rule"
        assert resolve_task_name("prompt") == "prompt"

    def test_unknown_type_falls_back_to_skill(self):
        from eval_bridge import resolve_task_name

        assert resolve_task_name("unknown_type") == "skill"

    def test_builtin_configs_loadable(self):
        from ai_resource_eval.tasks.loader import load_task_config
        from eval_bridge import resolve_task_name

        for t in ("mcp", "skill", "rule", "prompt"):
            config = load_task_config(resolve_task_name(t))
            assert config is not None
