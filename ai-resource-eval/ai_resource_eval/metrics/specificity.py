"""Specificity metric — evaluates whether the tool solves one clear problem."""

from __future__ import annotations

from ai_resource_eval.api.metric import BaseMetric


class Specificity(BaseMetric):
    """Evaluates how focused and specific the resource is.

    A high score means the resource clearly solves one well-defined problem.
    A low score means the resource tries to do everything or has an unclear
    focus, making it hard for a developer to know when to use it.
    """

    @property
    def name(self) -> str:
        return "specificity"

    @property
    def requires_content(self) -> bool:
        return True

    def build_rubric(self) -> str:
        return (
            "## Dimension: specificity\n"
            "Evaluate whether the resource has a clear, focused purpose with "
            "well-defined scope boundaries. A good coding resource solves one "
            "problem well and helps developers decide quickly whether it fits "
            "their needs.\n"
            "\n"
            "### Score Anchors\n"
            "- **1 (Unfocused)**: The README describes a grab-bag of unrelated "
            "features with no clear core purpose. It is impossible to summarize "
            "what problem this resource solves in one sentence.\n"
            "- **2 (Broad / scattered)**: The resource has a vaguely stated goal but "
            "the README lists many loosely related features. The scope is too wide "
            "for a developer to quickly understand when they would use this.\n"
            "- **3 (Moderate focus)**: The resource has a discernible core purpose "
            "but also includes tangential features or capabilities that dilute the "
            "focus. A developer can guess the main use case but may be unsure about "
            "scope boundaries or when NOT to use it.\n"
            "- **4 (Focused)**: The resource clearly targets a specific problem or "
            "workflow. The README communicates the primary use case early. Every "
            "documented feature serves the core purpose. A developer can quickly "
            "tell whether this resource is relevant. However, scope boundaries, "
            "limitations, or 'when not to use this' guidance is absent.\n"
            "- **5 (Laser-focused with boundaries)**: All criteria of score 4, "
            "PLUS the README explicitly defines scope boundaries — what the "
            "resource does NOT do, known limitations, or guidance on when to use "
            "alternatives. Concrete use-case examples demonstrate the intended "
            "workflow. A developer can decide within 30 seconds whether this "
            "resource fits their needs AND what falls outside its scope.\n"
            "\n"
            "IMPORTANT: A resource that merely states its purpose clearly (even "
            "in one sentence) but does not communicate scope boundaries should "
            "receive at most a 4. Score 5 requires explicit boundary-setting.\n"
            "\n"
            "### Output\n"
            "Return: score (1-5), evidence (indicators of focus, scope boundaries, "
            "or lack thereof), missing (what would make the purpose and boundaries "
            "clearer), suggestion (how to sharpen the value proposition and scope).\n"
        )
