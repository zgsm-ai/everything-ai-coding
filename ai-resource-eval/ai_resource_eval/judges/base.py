"""BaseJudge — abstract base with retry logic and JSON extraction.

Provides the common ``judge()`` implementation that all concrete judge
backends inherit.  Subclasses only need to implement ``_call_llm``.
"""

from __future__ import annotations

import abc
import json
import logging
import re
import time
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from ai_resource_eval.api.judge import JudgeResult

logger = logging.getLogger(__name__)


class BaseJudge(abc.ABC):
    """Abstract base for LLM judge providers.

    Handles:
    - Structured JSON parsing (try ``json.loads`` first)
    - Fallback extraction of JSON from freetext (fenced blocks or bare ``{…}``)
    - Pydantic schema validation when a schema is supplied
    - Retry up to 3 total attempts with exponential back-off
    """

    max_retries: int = 3
    backoff_base: float = 1.0  # seconds; real wait = base * 2^attempt

    # ------------------------------------------------------------------
    # Abstract interface – subclasses must implement
    # ------------------------------------------------------------------

    @abc.abstractmethod
    def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any] | None = None,
    ) -> tuple[str, int, int, int]:
        """Call the LLM and return ``(raw_text, prompt_tokens, completion_tokens, latency_ms)``."""
        ...  # pragma: no cover

    @abc.abstractmethod
    def _compute_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Return estimated cost in USD for the given token counts."""
        ...  # pragma: no cover

    @abc.abstractmethod
    def _model_id(self) -> str:
        """Return the model identifier string."""
        ...  # pragma: no cover

    # ------------------------------------------------------------------
    # Public API (implements JudgeProvider.judge)
    # ------------------------------------------------------------------

    def judge(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any] | None = None,
        pydantic_model: type[BaseModel] | None = None,
    ) -> JudgeResult:
        """Evaluate content, retrying on parse failure up to *max_retries* times."""

        last_raw = ""
        last_prompt_tokens = 0
        last_completion_tokens = 0
        last_latency_ms = 0

        last_exception: Exception | None = None

        for attempt in range(self.max_retries):
            # On retries, drop response_format (schema) so models that
            # struggle with json_schema can fall back to freetext JSON.
            attempt_schema = schema if attempt == 0 else None

            # Wrap _call_llm to handle transient provider failures
            try:
                raw, prompt_tokens, completion_tokens, latency_ms = self._call_llm(
                    system_prompt, user_prompt, attempt_schema
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                logger.warning(
                    "Transient LLM error (attempt %d/%d): %s",
                    attempt + 1, self.max_retries, exc,
                )
                last_exception = exc
                if attempt < self.max_retries - 1:
                    time.sleep(self.backoff_base * (2**attempt))
                continue
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status == 429 or status >= 500:
                    logger.warning(
                        "Transient HTTP %d (attempt %d/%d): %s",
                        status, attempt + 1, self.max_retries, exc,
                    )
                    last_exception = exc
                    if attempt < self.max_retries - 1:
                        time.sleep(self.backoff_base * (2**attempt))
                    continue
                # Non-transient HTTP error (4xx other than 429) — re-raise
                raise

            last_exception = None
            last_raw = raw
            last_prompt_tokens = prompt_tokens
            last_completion_tokens = completion_tokens
            last_latency_ms = latency_ms

            parsed = self._try_parse(raw, attempt_schema, pydantic_model)
            if parsed is not None:
                return JudgeResult(
                    content=raw,
                    structured=parsed,
                    cost_usd=self._compute_cost(prompt_tokens, completion_tokens),
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    latency_ms=latency_ms,
                    model_id=self._model_id(),
                )

            # Back-off before retry (skip sleep on last attempt)
            if attempt < self.max_retries - 1:
                time.sleep(self.backoff_base * (2**attempt))

        # All retries exhausted
        if last_exception is not None:
            raise last_exception

        return JudgeResult(
            content=last_raw,
            structured=None,
            cost_usd=self._compute_cost(last_prompt_tokens, last_completion_tokens),
            prompt_tokens=last_prompt_tokens,
            completion_tokens=last_completion_tokens,
            latency_ms=last_latency_ms,
            model_id=self._model_id(),
        )

    # ------------------------------------------------------------------
    # JSON extraction helpers
    # ------------------------------------------------------------------

    def _try_parse(
        self,
        raw: str,
        schema: dict[str, Any] | None,
        pydantic_model: type[BaseModel] | None = None,
    ) -> dict[str, Any] | None:
        """Attempt to parse *raw* as JSON, with freetext fallback.

        1. Try ``json.loads(raw)`` directly.
        2. Try extracting a fenced ````` ```json … ``` ````` block.
        3. Try extracting the first top-level ``{ … }`` substring.
        4. If a *pydantic_model* is provided, validate via
           ``pydantic_model.model_validate(data)`` (catches type errors,
           missing fields, constraint violations).
        5. Otherwise, if a *schema* is provided, fall back to the basic
           required-key check.
        """
        if not raw:
            return None
        data = self._try_json_loads(raw)
        if data is None:
            data = self._extract_fenced_json(raw)
        if data is None:
            data = self._extract_bare_json(raw)
        if data is None:
            return None

        # Prefer Pydantic model validation when available.
        # Pydantic uses defaults for missing optional fields, so skip the
        # stricter schema required-key check when Pydantic passes.
        if pydantic_model is not None:
            data = self._validate_pydantic(data, pydantic_model)
            return data

        # Fall back to basic schema key-check
        if schema is not None:
            data = self._validate_schema(data, schema)

        return data

    @staticmethod
    def _try_json_loads(text: str) -> dict[str, Any] | None:
        try:
            result = json.loads(text)
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, TypeError):
            pass
        return None

    @staticmethod
    def _extract_fenced_json(text: str) -> dict[str, Any] | None:
        """Extract JSON from a ```json ... ``` fenced block."""
        pattern = r"```(?:json)?\s*\n?(.*?)\n?\s*```"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group(1))
                if isinstance(result, dict):
                    return result
            except (json.JSONDecodeError, TypeError):
                pass
        return None

    @staticmethod
    def _extract_bare_json(text: str) -> dict[str, Any] | None:
        """Extract the first balanced ``{ … }`` substring from *text*."""
        start = text.find("{")
        if start == -1:
            return None
        # Find the matching closing brace by tracking nesting
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        result = json.loads(text[start : i + 1])
                        if isinstance(result, dict):
                            return result
                    except (json.JSONDecodeError, TypeError):
                        pass
                    return None
        return None

    @staticmethod
    def _validate_pydantic(
        data: dict[str, Any], pydantic_model: type[BaseModel]
    ) -> dict[str, Any] | None:
        """Validate *data* by parsing it with a Pydantic model.

        Returns *data* if validation succeeds, or ``None`` if it fails.
        Using the actual Pydantic model catches type mismatches, missing
        required fields, and constraint violations that the basic
        required-key check cannot detect.
        """
        try:
            pydantic_model.model_validate(data)
            return data
        except (ValidationError, Exception):
            return None

    @staticmethod
    def _validate_schema(
        data: dict[str, Any], schema: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Validate *data* against a JSON Schema, checking nested required keys.

        Returns *data* if valid, or ``None`` if validation fails.

        We enforce *required* field presence at the top level **and**
        recursively for any nested object properties that declare their
        own ``required`` list.  Type checking beyond ``dict`` for nested
        objects is intentionally lenient — the caller can do deeper
        validation downstream.
        """
        try:
            if not BaseJudge._check_required_recursive(data, schema):
                return None
            return data
        except Exception:
            return None

    @staticmethod
    def _resolve_ref(
        prop_schema: dict[str, Any], root_schema: dict[str, Any]
    ) -> dict[str, Any]:
        """Resolve a ``$ref`` pointer against the root schema's ``$defs``.

        Only handles the ``#/$defs/<Name>`` form used by Pydantic.
        Returns the original *prop_schema* unchanged if there is no ``$ref``
        or the reference cannot be resolved.
        """
        ref = prop_schema.get("$ref")
        if ref is None:
            return prop_schema
        # Expected form: "#/$defs/SomeName"
        prefix = "#/$defs/"
        if not ref.startswith(prefix):
            return prop_schema
        def_name = ref[len(prefix):]
        defs = root_schema.get("$defs", {})
        return defs.get(def_name, prop_schema)

    @staticmethod
    def _check_required_recursive(
        data: dict[str, Any],
        schema: dict[str, Any],
        root_schema: dict[str, Any] | None = None,
    ) -> bool:
        """Return True if *data* satisfies the ``required`` constraints in *schema*.

        For each property that has its own ``required`` list and
        ``properties``, recurse into the corresponding value in *data*
        (which must itself be a ``dict``).

        ``$ref`` pointers (as produced by Pydantic's ``model_json_schema``)
        are resolved against the top-level ``$defs`` before inspection.
        """
        if root_schema is None:
            root_schema = schema

        required = schema.get("required", [])

        # Check that every required key is present at this level
        for key in required:
            if key not in data:
                return False

        # Recurse into nested object properties that define their own schema
        properties = schema.get("properties", {})
        for prop_name, prop_schema in properties.items():
            resolved = BaseJudge._resolve_ref(prop_schema, root_schema)
            nested_required = resolved.get("required")
            if nested_required is not None and prop_name in data:
                value = data[prop_name]
                if not isinstance(value, dict):
                    return False
                if not BaseJudge._check_required_recursive(
                    value, resolved, root_schema
                ):
                    return False

        return True
