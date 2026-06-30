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


def _make_eval_result(entry_id, scores=None, enrichment=None, mcp_installability=None):
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
    if mcp_installability is not None:
        result["mcp_installability"] = mcp_installability
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


class TestMcpInstallabilityMapping:
    """Test MCP installability fields mapping from EvalResult to catalog entry."""

    def test_mcp_installability_fields_mapped_for_mcp(self):
        from eval_bridge import map_result_to_entry

        entry = _make_entries()[0]
        installability = {
            "mcp_schema_valid": True,
            "mcp_install_state": "needs_config",
            "mcp_validation_tags": ["readme_config_found", "placeholder_path"],
            "mcp_installability_reason": "README 配置包含本地路径占位。",
        }
        result = _make_eval_result(
            "test-mcp-1", mcp_installability=installability
        )

        map_result_to_entry(entry, result)

        assert entry["mcp_schema_valid"] is True
        assert entry["mcp_install_state"] == "needs_config"
        assert entry["mcp_validation_tags"] == [
            "readme_config_found",
            "placeholder_path",
        ]
        assert entry["mcp_installability_reason"] == "README 配置包含本地路径占位。"

    def test_mcp_installability_not_mapped_for_non_mcp(self):
        from eval_bridge import map_result_to_entry

        entry = _make_entries()[1]
        installability = {
            "mcp_schema_valid": True,
            "mcp_install_state": "ready",
            "mcp_validation_tags": ["catalog_config_ready"],
            "mcp_installability_reason": "配置可直接运行。",
        }
        result = _make_eval_result(
            "test-skill-1", mcp_installability=installability
        )

        map_result_to_entry(entry, result)

        assert "mcp_schema_valid" not in entry
        assert "mcp_install_state" not in entry
        assert "mcp_validation_tags" not in entry
        assert "mcp_installability_reason" not in entry

    def test_missing_mcp_installability_sets_unknown_fallback(self):
        from eval_bridge import map_result_to_entry

        entry = _make_entries()[0]
        entry["mcp_install_state"] = "manual"
        result = _make_eval_result("test-mcp-1")

        map_result_to_entry(entry, result)

        assert entry["mcp_schema_valid"] is False
        assert entry["mcp_install_state"] == "unknown"
        assert entry["mcp_validation_tags"] == ["insufficient_evidence"]
        assert entry["mcp_installability_reason"] == "本轮评估未返回有效的 MCP 可用性判断。"


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


class TestInstallPopularitySignal:
    """install_popularity 信号采集（默认权重 0，仅观测）"""

    def test_install_popularity_mapped_into_signals(self):
        """harness 输出包含 install_popularity 时应写入 health.signals"""
        from eval_bridge import map_result_to_entry

        entry = _make_entries()[1]  # skill entry
        result = _make_eval_result("test-skill-1")
        # 模拟 harness 已计算的 install_popularity
        result["health"] = {
            "freshness": 80.0,
            "popularity": 50.0,
            "source_trust": 70.0,
            "install_popularity": 80.0,  # 对应 install_count ≈ 10000
        }
        map_result_to_entry(entry, result)

        signals = entry["health"]["signals"]
        assert signals["install_popularity"] == 80
        # health.score 仅由前 3 个信号聚合，不被 install_popularity 影响
        assert entry["health"]["score"] == round((80 + 50 + 70) / 3)

    def test_install_popularity_absent_defaults_to_zero(self):
        """harness 输出未包含 install_popularity 时回填 0，保持向后兼容"""
        from eval_bridge import map_result_to_entry

        entry = _make_entries()[0]
        result = _make_eval_result("test-mcp-1")
        # 旧版 result 不含 install_popularity 字段
        result["health"] = {
            "freshness": 80.0,
            "popularity": 50.0,
            "source_trust": 70.0,
        }
        map_result_to_entry(entry, result)

        signals = entry["health"]["signals"]
        assert signals["install_popularity"] == 0


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


class TestBlendDerivedHealth:
    """effective_score / content_quality / excluded_signals / manifest axis are
    derived in map_result_to_entry from the blend identity
    ``final = α·llm + (1-α)·health`` (α=0.85), so downstream consumers display a
    self-consistent breakdown instead of re-porting the scoring engine."""

    @staticmethod
    def _result(**over):
        r = {
            "metrics": {
                "coding_relevance": {"score": 4}, "doc_completeness": {"score": 4},
                "desc_accuracy": {"score": 5}, "writing_quality": {"score": 4},
                "specificity": {"score": 4}, "install_clarity": {"score": 4},
            },
            "health": {"freshness": 100.0, "popularity": 100.0, "source_trust": 40.0},
            "llm_score": 83.0,
            "final_score": 80.407,  # 0.85*83 + 0.15*65.71
            "decision": "accept", "star_weight": 0.0,
            "model_id": "m", "rubric_version": "v", "evaluated_at": "t",
        }
        r.update(over)
        return r

    def test_skill_star_noise(self):
        from eval_bridge import map_result_to_entry

        entry = {"id": "azure", "type": "skill", "pushed_at": "2026-05-09T00:00:00Z"}
        map_result_to_entry(entry, self._result())
        assert entry["evaluation"]["content_quality"] == 83
        assert entry["health"]["effective_score"] == 66  # round((80.407-70.55)/0.15)
        assert entry["health"]["excluded_signals"] == ["popularity"]
        assert entry["health"]["score"] == 80  # simple-mean radar unchanged
        assert "manifest_completeness" not in entry["health"]["signals"]

    def test_plugin_manifest_axis(self):
        from eval_bridge import map_result_to_entry

        entry = {"id": "sp", "type": "plugin", "pushed_at": "2026-06-09T00:00:00Z"}
        result = self._result(
            metrics={
                "coding_relevance": {"score": 5}, "doc_completeness": {"score": 4},
                "desc_accuracy": {"score": 5}, "writing_quality": {"score": 5},
                "specificity": {"score": 5},
            },
            health={"freshness": 100.0, "popularity": 100.0, "source_trust": 100.0,
                    "manifest_completeness": 70.0},
            llm_score=94.0, final_score=94.45, star_weight=1.0,
        )
        map_result_to_entry(entry, result)
        assert entry["evaluation"]["content_quality"] == 94
        assert entry["health"]["effective_score"] == 97  # (94.45-79.9)/0.15
        assert entry["health"]["excluded_signals"] == []
        assert entry["health"]["signals"]["manifest_completeness"] == 70

    def test_missing_pushed_at_excludes_freshness(self):
        from eval_bridge import map_result_to_entry

        entry = {"id": "x", "type": "skill", "pushed_at": None}
        map_result_to_entry(entry, self._result(star_weight=1.0))
        assert entry["health"]["excluded_signals"] == ["freshness"]

    def test_health_only_has_no_content_quality(self):
        from eval_bridge import map_result_to_entry

        entry = {"id": "ho", "type": "plugin", "pushed_at": "2026-06-09T00:00:00Z"}
        map_result_to_entry(entry, {
            "metrics": {}, "llm_score": None, "final_score": 100.0,
            "health": {"freshness": 100.0, "popularity": 100.0,
                       "source_trust": 100.0, "manifest_completeness": 100.0},
        })
        assert "content_quality" not in entry["evaluation"]
        assert entry["health"]["effective_score"] == 100  # final == health


class TestParseExtraHeaders:
    """LLM_EXTRA_HEADERS → header dict (gateway x-apikey injection)."""

    def test_unset_returns_empty(self):
        from eval_bridge import _parse_extra_headers

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LLM_EXTRA_HEADERS", None)
            assert _parse_extra_headers() == {}

    def test_valid_json_object(self):
        from eval_bridge import _parse_extra_headers

        with patch.dict(os.environ, {"LLM_EXTRA_HEADERS": '{"x-apikey": "secret"}'}):
            assert _parse_extra_headers() == {"x-apikey": "secret"}

    def test_malformed_json_degrades_to_empty(self):
        from eval_bridge import _parse_extra_headers

        with patch.dict(os.environ, {"LLM_EXTRA_HEADERS": "not json"}):
            assert _parse_extra_headers() == {}

    def test_non_object_json_degrades_to_empty(self):
        from eval_bridge import _parse_extra_headers

        with patch.dict(os.environ, {"LLM_EXTRA_HEADERS": '["a", "b"]'}):
            assert _parse_extra_headers() == {}


class TestBuildJudge:
    """_build_judge routing + extra_headers threading."""

    def test_custom_gateway_with_deepseek_model_uses_openai_compat(self):
        """A ``deepseek-*`` model behind a custom gateway must route to the
        generic OpenAI-compat judge (so base_url + x-apikey are honoured),
        not the hardcoded api.deepseek.com DeepSeekJudge."""
        from eval_bridge import _build_judge

        with patch.dict(os.environ, {
            "LLM_API_KEY": "sk-test",
            "LLM_BASE_URL": "https://gateway.example.com/newapi/v1",
            "LLM_MODEL": "deepseek-v4-flash",
            "LLM_EXTRA_HEADERS": '{"x-apikey": "gw-secret"}',
        }):
            judge = _build_judge()

        assert type(judge).__name__ == "OpenAICompatJudge"
        assert judge.base_url == "https://gateway.example.com/newapi/v1"
        assert judge.model == "deepseek-v4-flash"
        assert judge.extra_headers == {"x-apikey": "gw-secret"}

    def test_official_deepseek_host_uses_deepseek_judge(self):
        from eval_bridge import _build_judge

        with patch.dict(os.environ, {
            "LLM_API_KEY": "sk-test",
            "LLM_BASE_URL": "https://api.deepseek.com",
            "LLM_MODEL": "deepseek-chat",
        }):
            os.environ.pop("LLM_EXTRA_HEADERS", None)
            judge = _build_judge()

        assert type(judge).__name__ == "DeepSeekJudge"

    def test_no_api_key_returns_none(self):
        from eval_bridge import _build_judge

        with patch.dict(os.environ, {}, clear=True):
            assert _build_judge() is None
