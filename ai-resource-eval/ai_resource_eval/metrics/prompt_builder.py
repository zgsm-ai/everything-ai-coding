"""Merged prompt builder — assembles metric rubrics into a single LLM system prompt."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ai_resource_eval.api.metric import BaseMetric
from ai_resource_eval.api.registry import Registry
from ai_resource_eval.api.types import EnrichmentData, MetricResult

from ai_resource_eval.metrics.coding_relevance import CodingRelevance
from ai_resource_eval.metrics.doc_completeness import DocCompleteness
from ai_resource_eval.metrics.desc_accuracy import DescAccuracy
from ai_resource_eval.metrics.writing_quality import WritingQuality
from ai_resource_eval.metrics.specificity import Specificity
from ai_resource_eval.metrics.install_clarity import InstallClarity


# ---------------------------------------------------------------------------
# LLM response model
# ---------------------------------------------------------------------------


class LLMEvalResponse(BaseModel):
    """Expected JSON output from the LLM evaluation call.

    The LLM must return one ``MetricResult`` per dimension, keyed by metric
    name (e.g. ``"coding_relevance"``).  When enrichment is enabled, also
    contains an ``enrichment`` object.
    """

    metrics: dict[str, MetricResult] = Field(
        ...,
        description="Mapping of metric name to its evaluation result",
    )
    enrichment: EnrichmentData | None = Field(
        None,
        description="Enrichment fields (tags, summary, etc.) when enabled",
    )


# ---------------------------------------------------------------------------
# Prompt building functions
# ---------------------------------------------------------------------------


_SYSTEM_PREAMBLE = (
    "You are an expert evaluator of AI coding resources. You will be given a "
    "README (and optionally a catalog description) for a coding resource. "
    "Evaluate it across the following dimensions.\n"
    "\n"
    "For each dimension, return a JSON object with:\n"
    "- score: integer 1-5 (follow the anchors strictly)\n"
    "- evidence: list of strings — quotes or observations from the README\n"
    "- missing: list of strings — what is absent that would improve the score\n"
    "- suggestion: string — one actionable improvement tip\n"
    "\n"
    "Return your evaluation as a JSON object with a top-level key 'metrics' "
    "mapping each dimension name to its result object.\n"
    "\n"
    "---\n\n"
)

_ENRICHMENT_SECTION = (
    "## Enrichment Fields\n\n"
    "In addition to the metrics above, produce an 'enrichment' object at the "
    "same level as 'metrics' in your JSON output. The enrichment object MUST "
    "contain the following fields:\n\n"
    "- **summary**: A concise one-sentence description of the resource's core "
    "functionality. MUST be in English (≤150 characters), regardless of the "
    "README's original language.\n"
    "- **summary_zh**: A concise one-sentence description in Chinese "
    "(≤100 characters), regardless of the README's original language.\n"
    "- **tags**: A list of 3-5 lowercase kebab-case tags derived from the "
    "README content (e.g. ['mcp-server', 'database', 'python']). Tags should "
    "be specific to the resource, not generic.\n"
    "- **tech_stack**: A list of programming languages, frameworks, and tools "
    "mentioned or used in the README (e.g. ['python', 'fastapi', 'docker']).\n"
    "- **search_terms**: A list of 3-5 search-friendly terms/phrases in mixed "
    "languages (English + Chinese) for semantic recall (e.g. "
    "['binary analysis', '二进制分析', 'reverse engineering']).\n"
    "- **highlights**: A list of 2-3 short feature highlights in Chinese "
    "(≤60 characters each), suitable for catalog display "
    "(e.g. ['支持 15+ 数据库类型', 'Docker 一键部署']).\n"
    "\n"
    "---\n\n"
)


def build_system_prompt(
    metrics: list[BaseMetric],
    *,
    enrichment: bool = False,
) -> str:
    """Concatenate all metric rubrics into one system prompt.

    Parameters
    ----------
    metrics:
        List of metric instances whose rubrics should be included.
    enrichment:
        When True, append the enrichment section to the prompt.

    Returns
    -------
    str
        A complete system prompt ready to send to the LLM.
    """
    parts = [_SYSTEM_PREAMBLE]
    for metric in metrics:
        parts.append(metric.build_rubric())
        parts.append("\n---\n\n")
    if enrichment:
        parts.append(_ENRICHMENT_SECTION)
    return "".join(parts)


def build_output_schema(
    metric_names: list[str],
    *,
    enrichment: bool = False,
) -> dict:
    """Return the JSON schema for the expected LLM evaluation output.

    The schema describes a top-level ``metrics`` object where each key is a
    metric name and each value conforms to ``MetricResult``.  When
    *enrichment* is True, an ``enrichment`` object is added to the schema.

    Parameters
    ----------
    metric_names:
        List of dimension names that the LLM should produce results for.
    enrichment:
        When True, include the enrichment object in the schema.

    Returns
    -------
    dict
        A JSON-serialisable schema dict.
    """
    metric_result_schema = MetricResult.model_json_schema()

    required = ["metrics"]
    properties: dict = {
        "metrics": {
            "type": "object",
            "required": metric_names,
            "properties": {
                name: {"$ref": "#/$defs/MetricResult"}
                for name in metric_names
            },
            "additionalProperties": False,
        },
    }
    defs: dict = {
        "MetricResult": metric_result_schema,
    }

    if enrichment:
        enrichment_schema = EnrichmentData.model_json_schema()
        properties["enrichment"] = {"$ref": "#/$defs/EnrichmentData"}
        required.append("enrichment")
        defs["EnrichmentData"] = enrichment_schema

    return {
        "type": "object",
        "required": required,
        "properties": properties,
        "$defs": defs,
    }


# ---------------------------------------------------------------------------
# Default metric registry
# ---------------------------------------------------------------------------

#: Global registry containing the six default evaluation metrics.
metric_registry: Registry[BaseMetric] = Registry()

_DEFAULT_METRICS: list[type[BaseMetric]] = [
    CodingRelevance,
    DocCompleteness,
    DescAccuracy,
    WritingQuality,
    Specificity,
    InstallClarity,
]

for _cls in _DEFAULT_METRICS:
    _instance = _cls()
    metric_registry.register(_instance.name, _instance)
