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


def _make_eval_result(entry_id, scores=None):
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
    return {
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

        assert entry["health"]["freshness"] == 80.0
        assert entry["health"]["popularity"] == 50.0

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


class TestResolveTaskConfig:
    """Test task config resolution from eval_config/ directory."""

    def test_known_types(self):
        from eval_bridge import resolve_task_config

        for t in ("mcp", "skill", "rule", "prompt"):
            path = resolve_task_config(t)
            assert path.endswith(".yaml")
            assert os.path.isfile(path), f"Config missing for type: {t}"

    def test_unknown_type_falls_back_to_skill(self):
        from eval_bridge import resolve_task_config

        path = resolve_task_config("unknown_type")
        assert "skill.yaml" in path
