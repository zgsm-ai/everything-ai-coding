"""Bridge between ai-resource-eval harness and the catalog pipeline.

Reads catalog entries, delegates evaluation to the local harness package
(ai-resource-eval), and maps results back as flattened score-only
fields (no evidence/missing/suggestion).
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config resolution
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_EVAL_CONFIG_DIR = _PROJECT_ROOT / "eval_config"

_TYPE_TO_CONFIG = {
    "mcp": "mcp_server.yaml",
    "skill": "skill.yaml",
    "rule": "rule.yaml",
    "prompt": "prompt.yaml",
}


def resolve_task_config(resource_type: str) -> str:
    """Return absolute path to the task YAML for a resource type."""
    filename = _TYPE_TO_CONFIG.get(resource_type, "skill.yaml")
    return str(_EVAL_CONFIG_DIR / filename)


# ---------------------------------------------------------------------------
# Result → Entry mapping
# ---------------------------------------------------------------------------

def map_result_to_entry(entry: dict[str, Any], result: dict[str, Any] | None) -> None:
    """Map an EvalResult dict onto a catalog entry (in-place).

    Flattens metric scores to integers (no evidence/missing/suggestion).
    Preserves existing evaluation if result is None (harness skipped entry).
    """
    if result is None:
        return

    # Build flattened evaluation sub-object
    evaluation: dict[str, Any] = {}
    for metric_name, metric_data in result.get("metrics", {}).items():
        # Store only the score integer, discard evidence/missing/suggestion
        if isinstance(metric_data, dict):
            evaluation[metric_name] = metric_data.get("score", 0)
        else:
            evaluation[metric_name] = metric_data

    # Copy governance fields
    evaluation["final_score"] = result.get("final_score", 0)
    evaluation["decision"] = result.get("decision", "review")
    evaluation["model_id"] = result.get("model_id")
    evaluation["rubric_version"] = result.get("rubric_version")
    evaluation["evaluated_at"] = result.get("evaluated_at")

    # Preserve source_trust / confidence from prior enrichment if present
    prior = entry.get("evaluation", {})
    for keep_field in ("source_trust", "confidence", "reason"):
        if keep_field in prior and keep_field not in evaluation:
            evaluation[keep_field] = prior[keep_field]

    entry["evaluation"] = evaluation

    # Map health signals
    if result.get("health"):
        entry["health"] = result["health"]

    # Top-level promotion (consumed by sort + downstream scripts)
    entry["final_score"] = result.get("final_score", 0)
    entry["decision"] = result.get("decision", "review")


# ---------------------------------------------------------------------------
# Harness invocation
# ---------------------------------------------------------------------------

def run_eval(
    entries: list[dict[str, Any]],
    cache_dir: str = ".eval_cache",
    incremental: bool = True,
    concurrency: int = 4,
) -> dict[str, dict[str, Any]]:
    """Run the eval harness and return {entry_id: result_dict}.

    Groups entries by type and runs each group with its task config.
    Returns only entries that were successfully evaluated.
    """
    try:
        from ai_resource_eval.api.types import EvalItem
        from ai_resource_eval.runner import EvalRunner
        from ai_resource_eval.tasks.loader import load_task_config_from_path
    except ImportError:
        logger.warning(
            "ai-resource-eval package not found. "
            "Ensure ai-resource-eval is installed: "
            "pip install -e ai-resource-eval"
        )
        return {}

    # Resolve judge from environment
    judge = _build_judge()
    if judge is None:
        logger.warning("No LLM API key configured, skipping evaluation")
        return {}

    # Group entries by type
    groups: dict[str, list[dict]] = {}
    for entry in entries:
        t = entry.get("type", "skill")
        groups.setdefault(t, []).append(entry)

    all_results: dict[str, dict[str, Any]] = {}

    for resource_type, group in groups.items():
        config_path = resolve_task_config(resource_type)
        try:
            task_config = load_task_config_from_path(config_path)
        except (FileNotFoundError, ValueError) as exc:
            logger.warning("Failed to load config for %s: %s, using skill fallback", resource_type, exc)
            task_config = load_task_config_from_path(resolve_task_config("skill"))

        # Convert dicts to EvalItem
        eval_items = []
        for e in group:
            try:
                eval_items.append(EvalItem(**e))
            except Exception as exc:
                logger.debug("Skipping entry %s: %s", e.get("id"), exc)

        runner = EvalRunner(
            task_config=task_config,
            judge=judge,
            cache_dir=cache_dir,
            concurrency=concurrency,
            incremental=incremental,
            interactive=False,
            on_fail="skip",
        )

        results = runner.run(eval_items)
        for r in results:
            rd = r.model_dump() if hasattr(r, "model_dump") else r
            all_results[rd["entry_id"]] = rd

    return all_results


def _build_judge():
    """Build a judge instance from environment variables."""
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("JUDGE_API_KEY")
    if not api_key:
        return None

    base_url = os.environ.get("LLM_BASE_URL") or os.environ.get("JUDGE_BASE_URL", "")
    model = os.environ.get("LLM_MODEL") or os.environ.get("JUDGE_MODEL", "")

    # Try DeepSeek first (cheapest)
    if not base_url or "deepseek" in base_url:
        from ai_resource_eval.judges.deepseek import DeepSeekJudge
        return DeepSeekJudge(api_key=api_key, model=model or "deepseek-chat")

    # Generic OpenAI-compatible
    from ai_resource_eval.judges.openai_compat import OpenAICompatJudge
    return OpenAICompatJudge(base_url=base_url, api_key=api_key, model=model)


# ---------------------------------------------------------------------------
# Pipeline entry point (called from enrichment_orchestrator)
# ---------------------------------------------------------------------------

def eval_and_map(
    entries: list[dict[str, Any]],
    cache_dir: str = ".eval_cache",
    incremental: bool = True,
    concurrency: int = 4,
) -> None:
    """Run eval harness on entries and map results back in-place.

    This is the main entry point called from the pipeline.
    """
    results = run_eval(
        entries,
        cache_dir=cache_dir,
        incremental=incremental,
        concurrency=concurrency,
    )

    mapped = 0
    for entry in entries:
        result = results.get(entry.get("id"))
        map_result_to_entry(entry, result)
        if result:
            mapped += 1

    logger.info("Eval bridge: mapped %d / %d entries", mapped, len(entries))
