"""Writing Quality metric — evaluates document readability, professionalism, and structure."""

from __future__ import annotations

from ai_resource_eval.api.metric import BaseMetric


class WritingQuality(BaseMetric):
    """Evaluates the writing quality of the README.

    Considers readability, professional tone, logical structure, grammar,
    consistent formatting, and appropriate use of headings, lists, and
    code blocks.
    """

    @property
    def name(self) -> str:
        return "writing_quality"

    @property
    def requires_content(self) -> bool:
        return True

    def build_rubric(self) -> str:
        return (
            "## Dimension: writing_quality\n"
            "Evaluate the readability, professionalism, structure, and grammar of "
            "the README.\n"
            "\n"
            "### Score Anchors\n"
            "- **1 (Poor)**: The README is barely readable. It may contain mostly "
            "raw notes, machine-generated text without editing, severe grammar "
            "errors, no headings, or walls of unformatted text.\n"
            "- **2 (Below average)**: The README is understandable but disorganized. "
            "It may jump between topics without clear sections, have frequent grammar "
            "or spelling issues, or use inconsistent formatting.\n"
            "- **3 (Adequate)**: The README is organized with some headings and "
            "sections. Grammar is acceptable with minor errors. Formatting is "
            "mostly consistent but could be improved (e.g., missing code fences, "
            "inconsistent list styles).\n"
            "- **4 (Good)**: The README is well-structured with clear headings, "
            "logical flow, and professional tone. Code blocks are properly fenced. "
            "Grammar is clean with only occasional minor issues.\n"
            "- **5 (Excellent)**: The README reads like professional documentation. "
            "Clear hierarchy of headings, scannable layout with lists and tables, "
            "consistent Markdown formatting, polished grammar, and appropriate "
            "use of emphasis, links, and badges. Easy to navigate.\n"
            "\n"
            "### Output\n"
            "Return: score (1-5), evidence (specific examples of good or bad writing "
            "from the README), missing (writing improvements that would help), "
            "suggestion (concrete advice to raise the quality).\n"
        )
