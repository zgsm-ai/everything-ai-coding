"""Document Completeness metric — evaluates README information completeness."""

from __future__ import annotations

from ai_resource_eval.api.metric import BaseMetric


class DocCompleteness(BaseMetric):
    """Evaluates the completeness of information in the README.

    Checks for the presence and quality of: installation instructions, usage
    methods, API documentation, code examples, configuration guidance, and
    prerequisites/requirements.
    """

    @property
    def name(self) -> str:
        return "doc_completeness"

    @property
    def requires_content(self) -> bool:
        return True

    def build_rubric(self) -> str:
        return (
            "## Dimension: doc_completeness\n"
            "Evaluate how complete the README is as a standalone document for a "
            "developer evaluating or adopting this resource.\n"
            "\n"
            "Key information areas to check:\n"
            "- Installation / setup instructions\n"
            "- Usage methods and examples\n"
            "- API documentation or reference\n"
            "- Code examples (runnable or illustrative)\n"
            "- Configuration options and guidance\n"
            "- Prerequisites and requirements (runtime, dependencies, OS)\n"
            "\n"
            "### Score Anchors\n"
            "- **1 (Bare minimum)**: README is essentially empty, a single sentence, "
            "or auto-generated boilerplate. None of the six information areas are "
            "covered.\n"
            "- **2 (Sparse)**: README covers 1-2 of the six areas, typically just a "
            "brief description and maybe a one-liner install command. No usage "
            "examples or API docs.\n"
            "- **3 (Partial)**: README covers 3-4 areas with at least shallow detail. "
            "For example, install instructions exist but usage is vague, or there are "
            "examples but no configuration guidance.\n"
            "- **4 (Thorough)**: README covers 5-6 areas. Install, usage, and examples "
            "are clear. Minor gaps remain (e.g., advanced configuration not documented, "
            "or prerequisites only partially listed).\n"
            "- **5 (Comprehensive)**: All six areas are well-covered with sufficient "
            "detail. A developer could install, configure, and start using the resource "
            "by reading the README alone. Edge cases, troubleshooting, or FAQ may also "
            "be present.\n"
            "\n"
            "### Output\n"
            "Return: score (1-5), evidence (which areas are present and how detailed), "
            "missing (which areas are absent or insufficient), "
            "suggestion (specific improvements to reach a higher score).\n"
        )
