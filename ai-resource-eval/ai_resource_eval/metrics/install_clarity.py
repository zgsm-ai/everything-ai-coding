"""Install Clarity metric — evaluates installation/configuration guide quality."""

from __future__ import annotations

from ai_resource_eval.api.metric import BaseMetric


class InstallClarity(BaseMetric):
    """Evaluates how clear and actionable the installation and configuration
    instructions are.

    A high score means a developer can go from zero to a working setup by
    following the README alone.  A low score means the install process is
    undocumented, ambiguous, or requires significant guesswork.
    """

    @property
    def name(self) -> str:
        return "install_clarity"

    @property
    def requires_content(self) -> bool:
        return True

    def build_rubric(self) -> str:
        return (
            "## Dimension: install_clarity\n"
            "Evaluate how clear and actionable the installation and configuration "
            "instructions are in the README.\n"
            "\n"
            "### Score Anchors\n"
            "- **1 (No install guidance)**: The README contains no installation "
            "instructions at all, or says only 'install it' with no further detail.\n"
            "- **2 (Minimal)**: A single install command is present (e.g., "
            "'npm install foo') but there is no mention of prerequisites, "
            "configuration, or what to do after installation.\n"
            "- **3 (Basic)**: Install steps are documented with the primary method "
            "(e.g., pip, npm, brew). Some prerequisites are mentioned. But "
            "configuration is vague, and alternative install methods or "
            "platform-specific notes are absent.\n"
            "- **4 (Clear)**: Step-by-step installation with prerequisites listed. "
            "Configuration is documented with examples (e.g., env vars, config "
            "files). The developer can get started with minimal guesswork. Minor "
            "gaps may exist for edge-case environments.\n"
            "- **5 (Exemplary)**: Complete, copy-paste-ready installation guide. "
            "Multiple methods documented (e.g., npm + Docker + manual). "
            "Prerequisites explicit with version requirements. Configuration fully "
            "documented with defaults, examples, and troubleshooting tips. "
            "Quick-start section gets the user to 'hello world' in minutes.\n"
            "\n"
            "### Output\n"
            "Return: score (1-5), evidence (what install/config info is present), "
            "missing (what install/config info is absent), "
            "suggestion (specific steps to make installation easier).\n"
        )
