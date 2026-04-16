"""Description Accuracy metric — compares catalog description vs README content."""

from __future__ import annotations

from ai_resource_eval.api.metric import BaseMetric


class DescAccuracy(BaseMetric):
    """Evaluates how accurately the short description field reflects the actual
    README content.

    A high score means the description is a faithful, non-misleading summary of
    what the README documents.  A low score means the description is vague,
    exaggerated, outdated, or contradicts the README.
    """

    @property
    def name(self) -> str:
        return "desc_accuracy"

    @property
    def requires_content(self) -> bool:
        return True

    def build_rubric(self) -> str:
        return (
            "## Dimension: desc_accuracy\n"
            "Evaluate how accurately the catalog description field matches the actual "
            "README content. The description is provided alongside the README.\n"
            "\n"
            "### Score Anchors\n"
            "- **1 (Misleading)**: The description claims features or capabilities "
            "that are not mentioned anywhere in the README, or contradicts what the "
            "README says. The description may be for a different project entirely.\n"
            "- **2 (Vague / outdated)**: The description is so generic it could apply "
            "to many projects (e.g., 'A useful tool'). Or it references features that "
            "the README no longer documents, suggesting staleness.\n"
            "- **3 (Partially accurate)**: The description captures the general domain "
            "of the project but misses key capabilities, overstates scope, or omits "
            "important qualifiers (e.g., says 'full IDE' when README shows it is a "
            "plugin).\n"
            "- **4 (Mostly accurate)**: The description correctly summarizes the core "
            "purpose and main features. Minor details may be missing or slightly "
            "embellished, but nothing misleading.\n"
            "- **5 (Faithful summary)**: The description is a precise, honest summary "
            "of what the README documents. Key features, scope, and limitations are "
            "all reflected. No exaggeration or omission of important caveats.\n"
            "\n"
            "### Output\n"
            "Return: score (1-5), evidence (specific matches or mismatches between "
            "description and README), missing (description claims not supported by "
            "README, or README content not reflected in description), "
            "suggestion (how to improve the description).\n"
        )
