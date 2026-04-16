"""Coding Relevance metric — evaluates how relevant a resource is to AI-assisted coding."""

from __future__ import annotations

from ai_resource_eval.api.metric import BaseMetric


class CodingRelevance(BaseMetric):
    """Evaluates whether the resource is genuinely useful for AI-assisted coding workflows.

    Examines the README for evidence of concrete coding-related functionality,
    such as code generation, editing, debugging, testing, deployment, or
    developer tooling integration.
    """

    @property
    def name(self) -> str:
        return "coding_relevance"

    @property
    def requires_content(self) -> bool:
        return True

    def build_rubric(self) -> str:
        return (
            "## Dimension: coding_relevance\n"
            "Evaluate how relevant this resource is to AI-assisted coding workflows.\n"
            "\n"
            "### Score Anchors\n"
            "- **1 (Not relevant)**: The README describes a resource with no clear "
            "connection to coding, development, or software engineering. It may be a "
            "general-purpose AI tool, a non-technical product, or completely off-topic.\n"
            "- **2 (Weakly relevant)**: The resource has a tangential connection to "
            "coding (e.g., a generic AI chat tool that *could* answer coding questions "
            "but is not designed for it). No code-specific features are documented.\n"
            "- **3 (Moderately relevant)**: The resource addresses a development-adjacent "
            "concern (e.g., documentation generation, project management, or API "
            "exploration) but does not directly assist with writing, editing, or "
            "understanding code.\n"
            "- **4 (Highly relevant)**: The resource directly supports coding workflows "
            "such as code completion, debugging, testing, linting, deployment, or IDE "
            "integration. The README describes concrete developer-facing features.\n"
            "- **5 (Essential coding tool)**: The resource is purpose-built for AI-assisted "
            "coding. The README demonstrates deep integration with editors/IDEs, code "
            "generation, refactoring, code review, or developer infrastructure. Clear "
            "code examples and developer-centric use cases are documented.\n"
            "\n"
            "### Output\n"
            "Return: score (1-5), evidence (quotes/observations from README supporting "
            "your score), missing (what is absent that would raise the score), "
            "suggestion (actionable improvement advice).\n"
        )
