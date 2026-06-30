"""OpenAICompatJudge — call any OpenAI-compatible API via httpx.

No dependency on the ``openai`` Python SDK; uses raw HTTP calls so we can
target DeepSeek, local vLLM, Together AI, etc.
"""

from __future__ import annotations

import time
from typing import Any, ClassVar

import httpx

from ai_resource_eval.judges.base import BaseJudge


class OpenAICompatJudge(BaseJudge):
    """Judge backend for any OpenAI-compatible chat-completions endpoint.

    Parameters
    ----------
    base_url:
        API base URL **without** trailing ``/v1``.  The judge will POST to
        ``{base_url}/v1/chat/completions``.
    api_key:
        Bearer token for the API.
    model:
        Model identifier to include in the request payload.
    cost_per_1k_prompt:
        USD cost per 1 000 prompt tokens (default 0).
    cost_per_1k_completion:
        USD cost per 1 000 completion tokens (default 0).
    timeout:
        HTTP timeout in seconds (default 120).

    Notes
    -----
    `_capability_cache`：进程级共享 ``(base_url, model) → bool`` 缓存，自动避免
    对已知不支持 ``response_format=json_schema`` 的 endpoint 重复发起会被 400
    拒绝的请求。OpenAI / Azure 等原生支持后端行为不变；DeepSeek 等不支持的
    后端首次撞 400 后写入缓存，后续调用直接走简化版。详见 CHANGELOG.md。
    """

    # Endpoint capability cache, keyed by ``(base_url, model)``.
    #
    # value 含义：``True`` 视作支持 ``response_format=json_schema`` 协议
    # （OpenAI 2024-08 Structured Outputs），``False`` 视作不支持。
    # ClassVar 让同一进程内所有 OpenAICompatJudge 实例共享一次探测结果，
    # CI 16 worker 并发时首次撞 400 后剩余 worker 立即受益。
    #
    # cache 默认值（未命中）：``True``（按原协议带 response_format 发起请求），
    # 这样 OpenAI / Azure 等原生支持 Structured Outputs 的后端完全不受影响。
    # 第一次撞 400 fallback 时写入 ``False``，后续同 (base_url, model) 调用
    # 直接发简化版（不带 response_format）。
    #
    # 进程退出即丢失（非持久化）；fallback 路径仍然保留作为冷启动兜底。
    _capability_cache: ClassVar[dict[tuple[str, str], bool]] = {}

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        cost_per_1k_prompt: float = 0.0,
        cost_per_1k_completion: float = 0.0,
        timeout: float = 120.0,
        temperature: float = 0.0,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.cost_per_1k_prompt = cost_per_1k_prompt
        self.cost_per_1k_completion = cost_per_1k_completion
        self.timeout = timeout
        self.temperature = temperature
        # Extra HTTP headers merged into every request. Needed for gateways
        # that require a non-standard auth header alongside ``Authorization``
        # (e.g. ``x-apikey`` on the sangfor newapi-sre gateway). Sourced from
        # the ``LLM_EXTRA_HEADERS`` env var (JSON object) by the judge factory.
        self.extra_headers = dict(extra_headers) if extra_headers else {}

    # ------------------------------------------------------------------
    # BaseJudge abstract implementations
    # ------------------------------------------------------------------

    def _model_id(self) -> str:
        return self.model

    def _compute_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        return (
            prompt_tokens / 1000.0 * self.cost_per_1k_prompt
            + completion_tokens / 1000.0 * self.cost_per_1k_completion
        )

    def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any] | None = None,
    ) -> tuple[str, int, int, int]:
        """POST to the OpenAI-compatible chat completions endpoint.

        Returns ``(raw_text, prompt_tokens, completion_tokens, latency_ms)``.
        """
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }

        # Request structured JSON output when a schema is provided AND the
        # endpoint hasn't been previously observed to reject `response_format`.
        # 见 design.md decision 1/2：cache key 为 (base_url, model)，
        # cache miss 时默认假设支持（True），让 OpenAI/Azure 等原生支持后端
        # 不受影响；首次 400 fallback 后写入 False，避免重复白发。
        cache_key = (self.base_url, self.model)
        supports_schema = self._capability_cache.get(cache_key, True)
        if schema is not None and supports_schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "judge_response",
                    "schema": schema,
                },
            }

        # Handle base_url that already includes /v1
        if self.base_url.rstrip("/").endswith("/v1"):
            url = f"{self.base_url.rstrip('/')}/chat/completions"
        else:
            url = f"{self.base_url}/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        # Merge caller-supplied headers last so a gateway-specific auth header
        # (e.g. ``x-apikey``) is always present. Callers may also override the
        # defaults above if they intentionally pass those keys.
        if self.extra_headers:
            headers.update(self.extra_headers)

        start = time.monotonic()
        response = httpx.post(
            url,
            json=payload,
            headers=headers,
            timeout=self.timeout,
        )
        latency_ms = int((time.monotonic() - start) * 1000)

        # If the backend rejects response_format with a 400, retry without it
        # so BaseJudge's freetext JSON-extraction fallback can handle the response.
        # 在 fallback 之前先把 (base_url, model) 标为不支持 json_schema —— 后续
        # 同一 endpoint 的调用会直接走简化版，不再重复白发原版被 400。保留
        # fallback 路径作为冷启动 / 缓存失效兜底（design decision 6）。
        if (
            response.status_code == 400
            and schema is not None
            and "response_format" in payload
        ):
            self._capability_cache[cache_key] = False
            payload.pop("response_format")
            start = time.monotonic()
            response = httpx.post(
                url,
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
            latency_ms = int((time.monotonic() - start) * 1000)

        response.raise_for_status()
        data = response.json()

        # Extract response text (some reasoning models may return null content)
        raw_text = data["choices"][0]["message"]["content"] or ""

        # Extract token usage
        usage = data.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)

        return raw_text, prompt_tokens, completion_tokens, latency_ms
