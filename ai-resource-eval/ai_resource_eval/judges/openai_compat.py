"""OpenAICompatJudge — call any OpenAI-compatible API via httpx.

No dependency on the ``openai`` Python SDK; uses raw HTTP calls so we can
target DeepSeek, local vLLM, Together AI, etc.
"""

from __future__ import annotations

import time
from typing import Any

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
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        cost_per_1k_prompt: float = 0.0,
        cost_per_1k_completion: float = 0.0,
        timeout: float = 120.0,
        temperature: float = 0.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.cost_per_1k_prompt = cost_per_1k_prompt
        self.cost_per_1k_completion = cost_per_1k_completion
        self.timeout = timeout
        self.temperature = temperature

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

        # Request structured JSON output when a schema is provided
        if schema is not None:
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
        if (
            response.status_code == 400
            and schema is not None
            and "response_format" in payload
        ):
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
