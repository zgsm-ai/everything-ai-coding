"""JudgeProvider Protocol and JudgeResult — LLM provider abstraction.

Defines the interface that all LLM judge backends must satisfy.  Concrete
implementations (e.g. DeepSeek, OpenAI-compatible) only need to implement the
:class:`JudgeProvider` Protocol and register themselves.

Pattern borrowed from OpenAI Evals' ``CompletionFn``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel


@dataclass(frozen=True)
class JudgeResult:
    """Immutable result returned by a :class:`JudgeProvider` call.

    Attributes:
        content: Raw LLM response text.
        structured: Parsed JSON result, or ``None`` if parsing failed.
        cost_usd: Estimated cost of the API call in USD.
        prompt_tokens: Number of tokens in the prompt.
        completion_tokens: Number of tokens in the completion.
        latency_ms: Wall-clock duration of the API call in milliseconds.
        model_id: Identifier of the model that produced the response.
    """

    content: str
    cost_usd: float
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    model_id: str
    structured: dict[str, Any] | None = field(default=None)

    @property
    def total_tokens(self) -> int:
        """Total token count (prompt + completion)."""
        return self.prompt_tokens + self.completion_tokens


@runtime_checkable
class JudgeProvider(Protocol):
    """Protocol that all LLM judge backends must satisfy.

    Implementations receive system and user prompts plus an optional JSON
    Schema and return a :class:`JudgeResult`.  The ``schema`` parameter
    enables structured-output modes on providers that support it.
    """

    def judge(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any] | None = None,
        pydantic_model: type[BaseModel] | None = None,
    ) -> JudgeResult:
        """Evaluate content using the LLM and return a structured result.

        Args:
            system_prompt: System-level instructions (rubric, persona, etc.).
            user_prompt: The content to evaluate (typically README text).
            schema: Optional JSON Schema to request structured output from
                the provider.
            pydantic_model: Optional Pydantic model class used to validate
                the parsed JSON.  When provided, the parsed data is validated
                via ``pydantic_model.model_validate(data)`` which catches
                type errors, missing fields, and constraint violations that
                the basic schema key-check would miss.

        Returns:
            A :class:`JudgeResult` with the raw response, parsed output,
            cost, token counts, and latency.
        """
        ...  # pragma: no cover
