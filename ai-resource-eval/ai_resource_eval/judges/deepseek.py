"""DeepSeekJudge — pre-configured OpenAI-compatible judge for DeepSeek.

Registers itself in the global ``judge_registry`` on import.
"""

from __future__ import annotations

from ai_resource_eval.api.judge import JudgeProvider
from ai_resource_eval.api.registry import Registry
from ai_resource_eval.judges.openai_compat import OpenAICompatJudge

# DeepSeek pricing (per 1K tokens, as of 2025 pricing)
_DEEPSEEK_COST_PER_1K_PROMPT = 0.00014  # $0.14 / 1M tokens
_DEEPSEEK_COST_PER_1K_COMPLETION = 0.00028  # $0.28 / 1M tokens

# Global registry for judge providers
judge_registry: Registry[JudgeProvider] = Registry()


class DeepSeekJudge(OpenAICompatJudge):
    """DeepSeek-specific judge with preset base_url and cost rates.

    Parameters
    ----------
    api_key:
        DeepSeek API key.  Typically set via ``JUDGE_API_KEY`` env var.
    model:
        Model to use (default ``deepseek-chat``).
    """

    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-chat",
        cost_per_1k_prompt: float = _DEEPSEEK_COST_PER_1K_PROMPT,
        cost_per_1k_completion: float = _DEEPSEEK_COST_PER_1K_COMPLETION,
    ) -> None:
        super().__init__(
            base_url="https://api.deepseek.com",
            api_key=api_key,
            model=model,
            cost_per_1k_prompt=cost_per_1k_prompt,
            cost_per_1k_completion=cost_per_1k_completion,
        )


# Register a factory-style sentinel so the registry knows about the provider.
# Actual instantiation requires an API key, so we register the *class* rather
# than an instance — callers use ``judge_registry.get("deepseek")`` to get the
# class and then instantiate it.
judge_registry.register("deepseek", DeepSeekJudge)  # type: ignore[arg-type]
