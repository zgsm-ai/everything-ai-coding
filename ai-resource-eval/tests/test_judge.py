"""Tests for ai_resource_eval.api.judge — JudgeProvider Protocol & JudgeResult."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest
from pydantic import BaseModel, Field

from ai_resource_eval.api.judge import JudgeProvider, JudgeResult
from ai_resource_eval.judges.base import BaseJudge
from ai_resource_eval.judges.openai_compat import OpenAICompatJudge
from ai_resource_eval.judges.deepseek import DeepSeekJudge, judge_registry


# ===================================================================
# JudgeResult
# ===================================================================


class TestJudgeResult:
    """Tests for JudgeResult dataclass."""

    def _make_result(self, **overrides: Any) -> JudgeResult:
        defaults: dict[str, Any] = dict(
            content='{"score": 4}',
            structured={"score": 4},
            cost_usd=0.002,
            prompt_tokens=100,
            completion_tokens=50,
            latency_ms=320,
            model_id="deepseek-chat",
        )
        defaults.update(overrides)
        return JudgeResult(**defaults)

    def test_all_fields(self):
        r = self._make_result()
        assert r.content == '{"score": 4}'
        assert r.structured == {"score": 4}
        assert r.cost_usd == 0.002
        assert r.prompt_tokens == 100
        assert r.completion_tokens == 50
        assert r.latency_ms == 320
        assert r.model_id == "deepseek-chat"

    def test_structured_none(self):
        """structured can be None when JSON parsing fails."""
        r = self._make_result(structured=None)
        assert r.structured is None

    def test_total_tokens(self):
        """total_tokens should return prompt_tokens + completion_tokens."""
        r = self._make_result(prompt_tokens=200, completion_tokens=80)
        assert r.total_tokens == 280

    def test_frozen(self):
        """JudgeResult should be immutable (frozen dataclass)."""
        r = self._make_result()
        with pytest.raises(FrozenInstanceError):
            r.content = "changed"  # type: ignore[misc]

    def test_structured_default_none(self):
        """structured defaults to None when not provided."""
        r = JudgeResult(
            content="raw text",
            cost_usd=0.0,
            prompt_tokens=10,
            completion_tokens=5,
            latency_ms=100,
            model_id="test-model",
        )
        assert r.structured is None


# ===================================================================
# JudgeProvider Protocol
# ===================================================================


class _FakeJudge:
    """Minimal implementation satisfying the JudgeProvider Protocol."""

    def judge(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any] | None = None,
        pydantic_model: type | None = None,
    ) -> JudgeResult:
        return JudgeResult(
            content="fake",
            structured=None,
            cost_usd=0.0,
            prompt_tokens=0,
            completion_tokens=0,
            latency_ms=0,
            model_id="fake-model",
        )


class TestJudgeProviderProtocol:
    """Tests for JudgeProvider Protocol structural subtyping."""

    def test_satisfies_protocol(self):
        """A class with the correct signature should satisfy JudgeProvider."""
        judge: JudgeProvider = _FakeJudge()
        result = judge.judge("system", "user")
        assert isinstance(result, JudgeResult)

    def test_satisfies_protocol_with_schema(self):
        judge: JudgeProvider = _FakeJudge()
        result = judge.judge("system", "user", schema={"type": "object"})
        assert isinstance(result, JudgeResult)

    def test_runtime_checkable(self):
        """JudgeProvider should be runtime-checkable via isinstance."""
        assert isinstance(_FakeJudge(), JudgeProvider)

    def test_non_conforming_rejected(self):
        """An object without the judge method should not satisfy the Protocol."""

        class _NotAJudge:
            pass

        assert not isinstance(_NotAJudge(), JudgeProvider)


# ===================================================================
# BaseJudge — JSON extraction & retry logic
# ===================================================================


def _make_openai_response(
    content: str,
    prompt_tokens: int = 100,
    completion_tokens: int = 50,
) -> dict[str, Any]:
    """Build a minimal OpenAI-compatible chat completion response dict."""
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


def _make_mock_response(
    response_body: dict[str, Any], status_code: int = 200
) -> MagicMock:
    """Create a single mock httpx.Response with the given body and status."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = status_code
    mock_response.json.return_value = response_body
    mock_response.raise_for_status = MagicMock()
    return mock_response


def _mock_httpx_post(response_body: dict[str, Any], status_code: int = 200):
    """Return a mock that replaces ``httpx.post`` with a canned response."""
    return MagicMock(return_value=_make_mock_response(response_body, status_code))


class TestBaseJudgeJsonExtraction:
    """Tests for BaseJudge._try_parse and its helper methods."""

    def _make_concrete_judge(self) -> OpenAICompatJudge:
        return OpenAICompatJudge(
            base_url="https://example.com",
            api_key="test-key",
            model="test-model",
        )

    def test_direct_json(self):
        judge = self._make_concrete_judge()
        result = judge._try_parse('{"score": 5, "reason": "good"}', None)
        assert result == {"score": 5, "reason": "good"}

    def test_fenced_json_block(self):
        judge = self._make_concrete_judge()
        text = 'Here is my evaluation:\n```json\n{"score": 3}\n```\nDone.'
        result = judge._try_parse(text, None)
        assert result == {"score": 3}

    def test_fenced_block_no_lang(self):
        judge = self._make_concrete_judge()
        text = 'Result:\n```\n{"score": 4}\n```'
        result = judge._try_parse(text, None)
        assert result == {"score": 4}

    def test_bare_json_in_prose(self):
        judge = self._make_concrete_judge()
        text = 'I think the answer is {"score": 2, "reason": "poor"} and that is it.'
        result = judge._try_parse(text, None)
        assert result == {"score": 2, "reason": "poor"}

    def test_nested_braces(self):
        judge = self._make_concrete_judge()
        text = 'prefix {"a": {"b": 1}} suffix'
        result = judge._try_parse(text, None)
        assert result == {"a": {"b": 1}}

    def test_no_json_returns_none(self):
        judge = self._make_concrete_judge()
        result = judge._try_parse("no json here at all", None)
        assert result is None

    def test_schema_validation_pass(self):
        judge = self._make_concrete_judge()
        schema = {
            "type": "object",
            "properties": {"score": {"type": "integer"}},
            "required": ["score"],
        }
        result = judge._try_parse('{"score": 5}', schema)
        assert result == {"score": 5}

    def test_schema_validation_fail_missing_field(self):
        judge = self._make_concrete_judge()
        schema = {
            "type": "object",
            "properties": {"score": {"type": "integer"}},
            "required": ["score"],
        }
        # Missing required field "score"
        result = judge._try_parse('{"other": 1}', schema)
        assert result is None

    # -- Nested required validation (P1 fix) --

    def test_nested_required_pass(self):
        """Schema with nested required keys — all present."""
        judge = self._make_concrete_judge()
        schema = {
            "type": "object",
            "required": ["metrics"],
            "properties": {
                "metrics": {
                    "type": "object",
                    "required": ["dim_a", "dim_b"],
                    "properties": {
                        "dim_a": {"type": "object"},
                        "dim_b": {"type": "object"},
                    },
                },
            },
        }
        data = json.dumps({"metrics": {"dim_a": {"score": 5}, "dim_b": {"score": 3}}})
        result = judge._try_parse(data, schema)
        assert result is not None
        assert "dim_a" in result["metrics"]
        assert "dim_b" in result["metrics"]

    def test_nested_required_empty_metrics_rejected(self):
        """An empty metrics dict should be rejected when dimensions are required."""
        judge = self._make_concrete_judge()
        schema = {
            "type": "object",
            "required": ["metrics"],
            "properties": {
                "metrics": {
                    "type": "object",
                    "required": ["dim_a", "dim_b"],
                    "properties": {
                        "dim_a": {"type": "object"},
                        "dim_b": {"type": "object"},
                    },
                },
            },
        }
        result = judge._try_parse('{"metrics": {}}', schema)
        assert result is None

    def test_nested_required_partial_metrics_rejected(self):
        """Partial metrics (missing some required dimensions) should be rejected."""
        judge = self._make_concrete_judge()
        schema = {
            "type": "object",
            "required": ["metrics"],
            "properties": {
                "metrics": {
                    "type": "object",
                    "required": ["dim_a", "dim_b"],
                    "properties": {
                        "dim_a": {"type": "object"},
                        "dim_b": {"type": "object"},
                    },
                },
            },
        }
        result = judge._try_parse('{"metrics": {"dim_a": {"score": 5}}}', schema)
        assert result is None

    def test_nested_required_non_dict_metrics_rejected(self):
        """metrics value that is not a dict should be rejected."""
        judge = self._make_concrete_judge()
        schema = {
            "type": "object",
            "required": ["metrics"],
            "properties": {
                "metrics": {
                    "type": "object",
                    "required": ["dim_a"],
                    "properties": {
                        "dim_a": {"type": "object"},
                    },
                },
            },
        }
        result = judge._try_parse('{"metrics": "oops"}', schema)
        assert result is None

    def test_nested_required_no_nested_schema_still_passes(self):
        """Schema without nested required — existing behaviour unchanged."""
        judge = self._make_concrete_judge()
        schema = {
            "type": "object",
            "required": ["metrics"],
            "properties": {
                "metrics": {"type": "object"},
            },
        }
        result = judge._try_parse('{"metrics": {}}', schema)
        assert result == {"metrics": {}}

    def test_schema_no_required_accepts_anything(self):
        """Schema with no required list at any level accepts any dict."""
        judge = self._make_concrete_judge()
        schema = {
            "type": "object",
            "properties": {"foo": {"type": "string"}},
        }
        result = judge._try_parse('{"bar": 1}', schema)
        assert result == {"bar": 1}

    # -- $ref resolution tests (P1 fix) --

    def _ref_schema(self) -> dict:
        """Build a schema using $ref/$defs like build_output_schema()."""
        return {
            "type": "object",
            "required": ["metrics"],
            "properties": {
                "metrics": {
                    "type": "object",
                    "required": ["dim_a", "dim_b"],
                    "properties": {
                        "dim_a": {"$ref": "#/$defs/MetricResult"},
                        "dim_b": {"$ref": "#/$defs/MetricResult"},
                    },
                    "additionalProperties": False,
                },
            },
            "$defs": {
                "MetricResult": {
                    "type": "object",
                    "required": ["score"],
                    "properties": {
                        "score": {"type": "integer"},
                        "evidence": {"type": "array"},
                        "missing": {"type": "array"},
                        "suggestion": {"type": "string"},
                    },
                },
            },
        }

    def test_ref_schema_valid_data_passes(self):
        """$ref schema — all required fields present should pass."""
        judge = self._make_concrete_judge()
        data = json.dumps({
            "metrics": {
                "dim_a": {"score": 5, "evidence": ["good"]},
                "dim_b": {"score": 3, "suggestion": "improve"},
            }
        })
        result = judge._try_parse(data, self._ref_schema())
        assert result is not None
        assert result["metrics"]["dim_a"]["score"] == 5

    def test_ref_schema_empty_metric_rejected(self):
        """$ref schema — empty metric dict missing required 'score' must be rejected."""
        judge = self._make_concrete_judge()
        data = json.dumps({
            "metrics": {
                "dim_a": {},
                "dim_b": {"score": 3},
            }
        })
        result = judge._try_parse(data, self._ref_schema())
        assert result is None

    def test_ref_schema_missing_score_rejected(self):
        """$ref schema — metric with evidence but no score must be rejected."""
        judge = self._make_concrete_judge()
        data = json.dumps({
            "metrics": {
                "dim_a": {"evidence": ["has evidence"], "suggestion": "tip"},
                "dim_b": {"score": 4},
            }
        })
        result = judge._try_parse(data, self._ref_schema())
        assert result is None

    def test_ref_schema_missing_dimension_rejected(self):
        """$ref schema — missing required dimension should be rejected."""
        judge = self._make_concrete_judge()
        data = json.dumps({
            "metrics": {
                "dim_a": {"score": 5},
                # dim_b is missing entirely
            }
        })
        result = judge._try_parse(data, self._ref_schema())
        assert result is None

    def test_ref_schema_non_dict_metric_rejected(self):
        """$ref schema — non-dict metric value should be rejected."""
        judge = self._make_concrete_judge()
        data = json.dumps({
            "metrics": {
                "dim_a": "not a dict",
                "dim_b": {"score": 3},
            }
        })
        result = judge._try_parse(data, self._ref_schema())
        assert result is None

    def test_ref_unresolvable_ref_treated_as_opaque(self):
        """Unresolvable $ref is treated as opaque (no required check)."""
        judge = self._make_concrete_judge()
        schema = {
            "type": "object",
            "required": ["x"],
            "properties": {
                "x": {"$ref": "#/$defs/Missing"},
            },
            "$defs": {},
        }
        data = json.dumps({"x": {}})
        result = judge._try_parse(data, schema)
        # Missing ref cannot be resolved — falls through without
        # nested validation, so top-level required passes
        assert result is not None


class TestOpenAICompatJudgeNormalResponse:
    """Test OpenAICompatJudge with mocked httpx — normal JSON response."""

    def _make_judge(self) -> OpenAICompatJudge:
        return OpenAICompatJudge(
            base_url="https://api.example.com",
            api_key="sk-test",
            model="gpt-test",
            cost_per_1k_prompt=0.01,
            cost_per_1k_completion=0.03,
        )

    @patch("ai_resource_eval.judges.openai_compat.httpx.post")
    def test_normal_json_response(self, mock_post: MagicMock):
        """LLM returns valid JSON directly — should parse and return structured."""
        body = _make_openai_response(
            content='{"score": 4, "reason": "well documented"}',
            prompt_tokens=200,
            completion_tokens=80,
        )
        mock_post.return_value = _make_mock_response(body)

        judge = self._make_judge()
        result = judge.judge("system", "user")

        assert result.structured == {"score": 4, "reason": "well documented"}
        assert result.prompt_tokens == 200
        assert result.completion_tokens == 80
        assert result.total_tokens == 280
        assert result.model_id == "gpt-test"
        # Cost: 200/1000 * 0.01 + 80/1000 * 0.03 = 0.002 + 0.0024 = 0.0044
        assert abs(result.cost_usd - 0.0044) < 1e-9

    @patch("ai_resource_eval.judges.openai_compat.httpx.post")
    def test_freetext_fallback(self, mock_post: MagicMock):
        """LLM returns prose with embedded JSON — should extract and parse."""
        content = (
            "Here is my evaluation:\n"
            "```json\n"
            '{"score": 3, "reason": "needs examples"}\n'
            "```\n"
            "Hope that helps!"
        )
        body = _make_openai_response(content=content)
        mock_post.return_value = _make_mock_response(body)

        judge = self._make_judge()
        result = judge.judge("system", "user")

        assert result.structured == {"score": 3, "reason": "needs examples"}
        # Only one call — no retries needed
        assert mock_post.call_count == 1

    @patch("ai_resource_eval.judges.openai_compat.httpx.post")
    def test_request_includes_schema_response_format(self, mock_post: MagicMock):
        """When schema is provided, request should include response_format."""
        body = _make_openai_response(content='{"score": 5}')
        mock_post.return_value = _make_mock_response(body)

        judge = self._make_judge()
        schema = {"type": "object", "properties": {"score": {"type": "integer"}}}
        judge.judge("system", "user", schema=schema)

        # Verify the POST payload includes response_format
        call_kwargs = mock_post.call_args
        sent_payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert "response_format" in sent_payload
        assert sent_payload["response_format"]["type"] == "json_schema"


class TestResponseFormatFallback:
    """Test that _call_llm retries without response_format on 400."""

    def _make_judge(self) -> OpenAICompatJudge:
        return OpenAICompatJudge(
            base_url="https://api.example.com",
            api_key="sk-test",
            model="vllm-model",
        )

    @patch("ai_resource_eval.judges.openai_compat.httpx.post")
    def test_400_with_schema_retries_without_response_format(
        self, mock_post: MagicMock
    ):
        """When response_format causes a 400, retry without it and succeed."""
        # First call: 400 (backend rejects response_format)
        resp_400 = MagicMock(spec=httpx.Response)
        resp_400.status_code = 400

        # Second call: 200 with valid JSON in freetext
        good_body = _make_openai_response(
            content='{"score": 4, "reason": "solid readme"}'
        )
        resp_200 = MagicMock(spec=httpx.Response)
        resp_200.status_code = 200
        resp_200.json.return_value = good_body
        resp_200.raise_for_status = MagicMock()

        mock_post.side_effect = [resp_400, resp_200]

        judge = self._make_judge()
        schema = {"type": "object", "properties": {"score": {"type": "integer"}}}
        result = judge.judge("system", "user", schema=schema)

        assert result.structured == {"score": 4, "reason": "solid readme"}
        assert mock_post.call_count == 2

        # Verify first call included response_format
        first_payload = mock_post.call_args_list[0].kwargs.get("json") or mock_post.call_args_list[0][1].get("json")
        # The payload was mutated (pop), so check the second call lacks it
        second_payload = mock_post.call_args_list[1].kwargs.get("json") or mock_post.call_args_list[1][1].get("json")
        assert "response_format" not in second_payload

    @patch("ai_resource_eval.judges.openai_compat.httpx.post")
    def test_400_without_schema_still_raises(self, mock_post: MagicMock):
        """A 400 when no schema was provided should still raise HTTPStatusError."""
        resp_400 = MagicMock(spec=httpx.Response)
        resp_400.status_code = 400
        resp_400.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Bad Request", request=MagicMock(), response=resp_400
        )

        mock_post.return_value = resp_400

        judge = self._make_judge()
        with pytest.raises(httpx.HTTPStatusError):
            judge.judge("system", "user")  # no schema

    @patch("ai_resource_eval.judges.base.time.sleep")
    @patch("ai_resource_eval.judges.openai_compat.httpx.post")
    def test_non_400_error_with_schema_retries_then_raises(
        self, mock_post: MagicMock, mock_sleep: MagicMock
    ):
        """A 500 error should be retried as a transient failure, then raise."""
        resp_500 = MagicMock(spec=httpx.Response)
        resp_500.status_code = 500
        resp_500.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error", request=MagicMock(), response=resp_500
        )

        mock_post.return_value = resp_500

        judge = self._make_judge()
        schema = {"type": "object", "properties": {"score": {"type": "integer"}}}
        with pytest.raises(httpx.HTTPStatusError):
            judge.judge("system", "user", schema=schema)

        # 500 is transient — retried max_retries (3) times
        assert mock_post.call_count == 3


class TestRetryLogic:
    """Test that BaseJudge retries on parse failure."""

    @patch("ai_resource_eval.judges.base.time.sleep")
    @patch("ai_resource_eval.judges.openai_compat.httpx.post")
    def test_retries_on_unparseable_then_succeeds(
        self, mock_post: MagicMock, mock_sleep: MagicMock
    ):
        """First call returns garbage, second returns valid JSON."""
        bad_body = _make_openai_response(content="This is not JSON at all")
        good_body = _make_openai_response(content='{"score": 4}')

        resp_bad = _make_mock_response(bad_body)
        resp_good = _make_mock_response(good_body)

        mock_post.side_effect = [resp_bad, resp_good]

        judge = OpenAICompatJudge(
            base_url="https://api.example.com",
            api_key="sk-test",
            model="test",
        )
        result = judge.judge("system", "user")

        assert result.structured == {"score": 4}
        assert mock_post.call_count == 2
        # Should have slept once (backoff between attempt 0 and 1)
        assert mock_sleep.call_count == 1

    @patch("ai_resource_eval.judges.base.time.sleep")
    @patch("ai_resource_eval.judges.openai_compat.httpx.post")
    def test_all_retries_exhausted(
        self, mock_post: MagicMock, mock_sleep: MagicMock
    ):
        """All 3 attempts return unparseable text — structured should be None."""
        bad_body = _make_openai_response(content="no json anywhere")

        mock_post.return_value = _make_mock_response(bad_body)

        judge = OpenAICompatJudge(
            base_url="https://api.example.com",
            api_key="sk-test",
            model="test",
        )
        result = judge.judge("system", "user")

        assert result.structured is None
        assert result.content == "no json anywhere"
        assert mock_post.call_count == 3
        # Sleeps between attempt 0->1 and 1->2 (not after last)
        assert mock_sleep.call_count == 2

    @patch("ai_resource_eval.judges.base.time.sleep")
    @patch("ai_resource_eval.judges.openai_compat.httpx.post")
    def test_exponential_backoff_times(
        self, mock_post: MagicMock, mock_sleep: MagicMock
    ):
        """Verify back-off durations: 1s, 2s."""
        bad_body = _make_openai_response(content="garbage")
        mock_post.return_value = _make_mock_response(bad_body)

        judge = OpenAICompatJudge(
            base_url="https://api.example.com",
            api_key="sk-test",
            model="test",
        )
        judge.judge("system", "user")

        sleep_args = [call.args[0] for call in mock_sleep.call_args_list]
        assert sleep_args == [1.0, 2.0]  # base * 2^0, base * 2^1


class TestTokenCostComputation:
    """Test cost computation in OpenAICompatJudge."""

    def test_zero_cost_rates(self):
        judge = OpenAICompatJudge(
            base_url="https://example.com",
            api_key="key",
            model="m",
            cost_per_1k_prompt=0.0,
            cost_per_1k_completion=0.0,
        )
        assert judge._compute_cost(1000, 1000) == 0.0

    def test_cost_calculation(self):
        judge = OpenAICompatJudge(
            base_url="https://example.com",
            api_key="key",
            model="m",
            cost_per_1k_prompt=0.01,
            cost_per_1k_completion=0.03,
        )
        # 500 prompt tokens + 200 completion tokens
        # = 0.5 * 0.01 + 0.2 * 0.03 = 0.005 + 0.006 = 0.011
        cost = judge._compute_cost(500, 200)
        assert abs(cost - 0.011) < 1e-9

    def test_model_id(self):
        judge = OpenAICompatJudge(
            base_url="https://example.com",
            api_key="key",
            model="my-model-v2",
        )
        assert judge._model_id() == "my-model-v2"


class TestDeepSeekJudge:
    """Test DeepSeekJudge configuration and registry."""

    def test_default_base_url(self):
        judge = DeepSeekJudge(api_key="sk-test")
        assert judge.base_url == "https://api.deepseek.com"

    def test_default_model(self):
        judge = DeepSeekJudge(api_key="sk-test")
        assert judge.model == "deepseek-chat"

    def test_cost_rates_set(self):
        judge = DeepSeekJudge(api_key="sk-test")
        assert judge.cost_per_1k_prompt > 0
        assert judge.cost_per_1k_completion > 0

    def test_registered_in_registry(self):
        assert "deepseek" in judge_registry

    def test_registry_returns_class(self):
        cls = judge_registry.get("deepseek")
        assert cls is DeepSeekJudge

    def test_satisfies_judge_provider(self):
        judge = DeepSeekJudge(api_key="sk-test")
        assert isinstance(judge, JudgeProvider)

    @patch("ai_resource_eval.judges.openai_compat.httpx.post")
    def test_deepseek_posts_to_correct_url(self, mock_post: MagicMock):
        body = _make_openai_response(content='{"score": 5}')
        mock_post.return_value = _make_mock_response(body)

        judge = DeepSeekJudge(api_key="sk-deep")
        judge.judge("system", "user")

        call_args = mock_post.call_args
        url = call_args.args[0] if call_args.args else call_args.kwargs.get("url")
        assert url == "https://api.deepseek.com/v1/chat/completions"


# ===================================================================
# Pydantic model validation (P1 fix: enforce field types)
# ===================================================================


class _SimpleMetricResult(BaseModel):
    """Minimal stand-in for MetricResult used in tests."""

    score: int = Field(..., ge=1, le=5)
    evidence: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    suggestion: str = Field(default="")


class _SimpleEvalResponse(BaseModel):
    """Minimal stand-in for LLMEvalResponse used in tests."""

    metrics: dict[str, _SimpleMetricResult]


class TestPydanticModelValidation:
    """Tests that pydantic_model validation catches type/shape errors."""

    def _make_judge(self) -> OpenAICompatJudge:
        return OpenAICompatJudge(
            base_url="https://example.com",
            api_key="test-key",
            model="test-model",
        )

    # -- _try_parse level tests --

    def test_valid_data_passes_pydantic(self):
        judge = self._make_judge()
        data = json.dumps({
            "metrics": {
                "dim_a": {"score": 4, "evidence": ["good"], "missing": [], "suggestion": "ok"},
            }
        })
        result = judge._try_parse(data, None, pydantic_model=_SimpleEvalResponse)
        assert result is not None
        assert result["metrics"]["dim_a"]["score"] == 4

    def test_wrong_score_type_rejected(self):
        """score: 'oops' (string instead of int) should be rejected."""
        judge = self._make_judge()
        data = json.dumps({
            "metrics": {
                "dim_a": {"score": "oops", "evidence": [], "missing": [], "suggestion": ""},
            }
        })
        result = judge._try_parse(data, None, pydantic_model=_SimpleEvalResponse)
        assert result is None

    def test_evidence_not_a_list_rejected(self):
        """evidence: 'not-a-list' should be rejected."""
        judge = self._make_judge()
        data = json.dumps({
            "metrics": {
                "dim_a": {"score": 3, "evidence": "not-a-list", "missing": [], "suggestion": ""},
            }
        })
        result = judge._try_parse(data, None, pydantic_model=_SimpleEvalResponse)
        assert result is None

    def test_missing_not_a_list_rejected(self):
        """missing: 42 should be rejected."""
        judge = self._make_judge()
        data = json.dumps({
            "metrics": {
                "dim_a": {"score": 3, "evidence": [], "missing": 42, "suggestion": ""},
            }
        })
        result = judge._try_parse(data, None, pydantic_model=_SimpleEvalResponse)
        assert result is None

    def test_score_out_of_range_rejected(self):
        """score: 0 should be rejected (ge=1 constraint)."""
        judge = self._make_judge()
        data = json.dumps({
            "metrics": {
                "dim_a": {"score": 0, "evidence": [], "missing": [], "suggestion": ""},
            }
        })
        result = judge._try_parse(data, None, pydantic_model=_SimpleEvalResponse)
        assert result is None

    def test_missing_required_field_rejected(self):
        """Missing 'score' field should be rejected."""
        judge = self._make_judge()
        data = json.dumps({
            "metrics": {
                "dim_a": {"evidence": ["ok"], "missing": [], "suggestion": ""},
            }
        })
        result = judge._try_parse(data, None, pydantic_model=_SimpleEvalResponse)
        assert result is None

    def test_metrics_not_a_dict_rejected(self):
        """metrics: 'oops' should be rejected."""
        judge = self._make_judge()
        data = json.dumps({"metrics": "oops"})
        result = judge._try_parse(data, None, pydantic_model=_SimpleEvalResponse)
        assert result is None

    def test_pydantic_model_takes_precedence_over_schema(self):
        """When both pydantic_model and schema are provided, pydantic_model wins."""
        judge = self._make_judge()
        # The schema would pass (only checks required keys),
        # but pydantic_model should reject the wrong type.
        schema = {
            "type": "object",
            "required": ["metrics"],
            "properties": {"metrics": {"type": "object"}},
        }
        data = json.dumps({
            "metrics": {
                "dim_a": {"score": "oops"},
            }
        })
        result = judge._try_parse(data, schema, pydantic_model=_SimpleEvalResponse)
        assert result is None

    def test_no_pydantic_model_falls_back_to_schema(self):
        """Without pydantic_model, the old schema key-check still works."""
        judge = self._make_judge()
        schema = {
            "type": "object",
            "required": ["score"],
            "properties": {"score": {"type": "integer"}},
        }
        # score is a string — schema key check does NOT catch this (it only
        # checks presence), so this should still pass with schema alone.
        data = json.dumps({"score": "oops"})
        result = judge._try_parse(data, schema, pydantic_model=None)
        assert result is not None  # schema fallback only checks key presence

    # -- Full judge() integration tests --

    @patch("ai_resource_eval.judges.base.time.sleep")
    @patch("ai_resource_eval.judges.openai_compat.httpx.post")
    def test_judge_retries_on_pydantic_failure(
        self, mock_post: MagicMock, mock_sleep: MagicMock
    ):
        """judge() retries when pydantic_model rejects the response."""
        bad_body = _make_openai_response(
            content=json.dumps({"metrics": {"dim_a": {"score": "oops"}}})
        )
        good_body = _make_openai_response(
            content=json.dumps({
                "metrics": {"dim_a": {"score": 4, "evidence": [], "missing": [], "suggestion": ""}}
            })
        )

        mock_post.side_effect = [
            _make_mock_response(bad_body),
            _make_mock_response(good_body),
        ]

        judge = self._make_judge()
        result = judge.judge(
            "system", "user", pydantic_model=_SimpleEvalResponse
        )

        assert result.structured is not None
        assert result.structured["metrics"]["dim_a"]["score"] == 4
        assert mock_post.call_count == 2
        assert mock_sleep.call_count == 1

    @patch("ai_resource_eval.judges.base.time.sleep")
    @patch("ai_resource_eval.judges.openai_compat.httpx.post")
    def test_judge_exhausts_retries_with_bad_types(
        self, mock_post: MagicMock, mock_sleep: MagicMock
    ):
        """All retries exhausted with wrong types — structured should be None."""
        bad_body = _make_openai_response(
            content=json.dumps({"metrics": {"dim_a": {"score": "always-wrong"}}})
        )
        mock_post.return_value = _make_mock_response(bad_body)

        judge = self._make_judge()
        result = judge.judge(
            "system", "user", pydantic_model=_SimpleEvalResponse
        )

        assert result.structured is None
        assert mock_post.call_count == 3


# ===================================================================
# P1 #1: Dual validation — pydantic_model + schema required keys
# ===================================================================


class TestDualPydanticAndSchemaValidation:
    """When both pydantic_model and schema are provided, both must pass."""

    def _make_judge(self) -> OpenAICompatJudge:
        return OpenAICompatJudge(
            base_url="https://example.com",
            api_key="test-key",
            model="test-model",
        )

    def _schema_requiring_two_dims(self) -> dict[str, Any]:
        """Schema that requires dim_a AND dim_b in metrics."""
        return {
            "type": "object",
            "required": ["metrics"],
            "properties": {
                "metrics": {
                    "type": "object",
                    "required": ["dim_a", "dim_b"],
                    "properties": {
                        "dim_a": {"type": "object"},
                        "dim_b": {"type": "object"},
                    },
                },
            },
        }

    def test_both_pass_returns_data(self):
        """Data valid for both pydantic_model and schema should pass."""
        judge = self._make_judge()
        schema = self._schema_requiring_two_dims()
        data = json.dumps({
            "metrics": {
                "dim_a": {"score": 4, "evidence": [], "missing": [], "suggestion": ""},
                "dim_b": {"score": 3, "evidence": [], "missing": [], "suggestion": ""},
            }
        })
        result = judge._try_parse(data, schema, pydantic_model=_SimpleEvalResponse)
        assert result is not None
        assert "dim_a" in result["metrics"]
        assert "dim_b" in result["metrics"]

    def test_pydantic_passes_even_with_missing_schema_dimension(self):
        """Pydantic accepts (dict[str, MetricResult] is flexible).  Schema
        required-key check is skipped when Pydantic passes — missing dimension
        detection is deferred to the runner layer (_parse_metrics)."""
        judge = self._make_judge()
        schema = self._schema_requiring_two_dims()
        # Only dim_a present — valid Pydantic-wise; dim_b check deferred
        data = json.dumps({
            "metrics": {
                "dim_a": {"score": 4, "evidence": [], "missing": [], "suggestion": ""},
            }
        })
        result = judge._try_parse(data, schema, pydantic_model=_SimpleEvalResponse)
        assert result is not None

    def test_pydantic_rejects_bad_type_even_with_schema(self):
        """Type error caught by pydantic_model — schema not even checked."""
        judge = self._make_judge()
        schema = self._schema_requiring_two_dims()
        data = json.dumps({
            "metrics": {
                "dim_a": {"score": "bad", "evidence": [], "missing": [], "suggestion": ""},
                "dim_b": {"score": 3, "evidence": [], "missing": [], "suggestion": ""},
            }
        })
        result = judge._try_parse(data, schema, pydantic_model=_SimpleEvalResponse)
        assert result is None

    def test_pydantic_only_without_schema_no_dimension_check(self):
        """Without schema, pydantic_model alone does not enforce required
        dimension names (dict[str, MetricResult] is flexible)."""
        judge = self._make_judge()
        data = json.dumps({
            "metrics": {
                "dim_a": {"score": 4, "evidence": [], "missing": [], "suggestion": ""},
            }
        })
        result = judge._try_parse(data, None, pydantic_model=_SimpleEvalResponse)
        assert result is not None  # pydantic alone doesn't know about dim_b


# ===================================================================
# P1 #2: Retry transient provider failures
# ===================================================================


class TestTransientRetry:
    """Test that BaseJudge retries on transient LLM errors."""

    def _make_judge(self) -> OpenAICompatJudge:
        return OpenAICompatJudge(
            base_url="https://api.example.com",
            api_key="sk-test",
            model="test",
        )

    @patch("ai_resource_eval.judges.base.time.sleep")
    @patch("ai_resource_eval.judges.openai_compat.httpx.post")
    def test_timeout_retried_then_succeeds(
        self, mock_post: MagicMock, mock_sleep: MagicMock
    ):
        """Timeout on first call, success on second — should return structured."""
        good_body = _make_openai_response(content='{"score": 5}')
        mock_post.side_effect = [
            httpx.TimeoutException("read timed out"),
            _make_mock_response(good_body),
        ]

        judge = self._make_judge()
        result = judge.judge("system", "user")

        assert result.structured == {"score": 5}
        assert mock_post.call_count == 2
        assert mock_sleep.call_count == 1

    @patch("ai_resource_eval.judges.base.time.sleep")
    @patch("ai_resource_eval.judges.openai_compat.httpx.post")
    def test_transport_error_retried_then_succeeds(
        self, mock_post: MagicMock, mock_sleep: MagicMock
    ):
        """Transport error on first call, success on second."""
        good_body = _make_openai_response(content='{"score": 3}')
        mock_post.side_effect = [
            httpx.ConnectError("connection reset"),
            _make_mock_response(good_body),
        ]

        judge = self._make_judge()
        result = judge.judge("system", "user")

        assert result.structured == {"score": 3}
        assert mock_post.call_count == 2

    @patch("ai_resource_eval.judges.base.time.sleep")
    @patch("ai_resource_eval.judges.openai_compat.httpx.post")
    def test_429_retried_then_succeeds(
        self, mock_post: MagicMock, mock_sleep: MagicMock
    ):
        """429 rate-limit on first call, success on second."""
        resp_429 = MagicMock(spec=httpx.Response)
        resp_429.status_code = 429
        resp_429.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Too Many Requests", request=MagicMock(), response=resp_429
        )

        good_body = _make_openai_response(content='{"score": 4}')

        mock_post.side_effect = [resp_429, _make_mock_response(good_body)]

        judge = self._make_judge()
        result = judge.judge("system", "user")

        assert result.structured == {"score": 4}
        assert mock_post.call_count == 2

    @patch("ai_resource_eval.judges.base.time.sleep")
    @patch("ai_resource_eval.judges.openai_compat.httpx.post")
    def test_5xx_retried_then_succeeds(
        self, mock_post: MagicMock, mock_sleep: MagicMock
    ):
        """502 on first call, success on second."""
        resp_502 = MagicMock(spec=httpx.Response)
        resp_502.status_code = 502
        resp_502.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Bad Gateway", request=MagicMock(), response=resp_502
        )

        good_body = _make_openai_response(content='{"score": 2}')

        mock_post.side_effect = [resp_502, _make_mock_response(good_body)]

        judge = self._make_judge()
        result = judge.judge("system", "user")

        assert result.structured == {"score": 2}
        assert mock_post.call_count == 2

    @patch("ai_resource_eval.judges.base.time.sleep")
    @patch("ai_resource_eval.judges.openai_compat.httpx.post")
    def test_all_transient_retries_exhausted_raises(
        self, mock_post: MagicMock, mock_sleep: MagicMock
    ):
        """All 3 attempts hit timeout — should raise the last exception."""
        mock_post.side_effect = httpx.TimeoutException("read timed out")

        judge = self._make_judge()
        with pytest.raises(httpx.TimeoutException):
            judge.judge("system", "user")

        assert mock_post.call_count == 3
        # Sleeps between attempts 0->1 and 1->2
        assert mock_sleep.call_count == 2

    @patch("ai_resource_eval.judges.base.time.sleep")
    @patch("ai_resource_eval.judges.openai_compat.httpx.post")
    def test_non_transient_4xx_not_retried(
        self, mock_post: MagicMock, mock_sleep: MagicMock
    ):
        """A 403 error should raise immediately, not retry."""
        resp_403 = MagicMock(spec=httpx.Response)
        resp_403.status_code = 403
        resp_403.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Forbidden", request=MagicMock(), response=resp_403
        )

        mock_post.return_value = resp_403

        judge = self._make_judge()
        with pytest.raises(httpx.HTTPStatusError):
            judge.judge("system", "user")

        # Not retried — only 1 call
        assert mock_post.call_count == 1
        assert mock_sleep.call_count == 0

    @patch("ai_resource_eval.judges.base.time.sleep")
    @patch("ai_resource_eval.judges.openai_compat.httpx.post")
    def test_transient_then_parse_failure_then_success(
        self, mock_post: MagicMock, mock_sleep: MagicMock
    ):
        """Timeout on first, unparseable on second, valid on third."""
        bad_body = _make_openai_response(content="not json")
        good_body = _make_openai_response(content='{"score": 5}')

        mock_post.side_effect = [
            httpx.TimeoutException("timed out"),
            _make_mock_response(bad_body),
            _make_mock_response(good_body),
        ]

        judge = self._make_judge()
        result = judge.judge("system", "user")

        assert result.structured == {"score": 5}
        assert mock_post.call_count == 3
