"""Smoke tests for platform skill invocation contracts.

These checks verify that each platform's `SKILL.md` advertises the same
command invocation style as the actual command files shipped in the repo.
"""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent.parent

PLATFORMS = {
    "claude-code": {
        "skill": ROOT / "platforms/claude-code/skills/coding-hub/SKILL.md",
        "command_dir": ROOT / "platforms/claude-code/commands/coding-hub",
        "commands": {
            "search": "search.md",
            "browse": "browse.md",
            "recommend": "recommend.md",
            "install": "install.md",
            "uninstall": "uninstall.md",
            "update": "update.md",
        },
        "expected_skill_triggers": [
            "/coding-hub:search <query>",
            "/coding-hub:browse [category]",
            "/coding-hub:recommend",
            "/coding-hub:install <name>",
            "/coding-hub:uninstall <name>",
            "/coding-hub:update <name>",
        ],
        "expected_inline_refs": [
            "/coding-hub:install <name>",
        ],
    },
    "costrict": {
        "skill": ROOT / "platforms/costrict/skills/coding-hub/SKILL.md",
        "command_dir": ROOT / "platforms/costrict/commands/coding-hub",
        "commands": {
            "search": "coding-hub-search.md",
            "browse": "coding-hub-browse.md",
            "recommend": "coding-hub-recommend.md",
            "install": "coding-hub-install.md",
            "uninstall": "coding-hub-uninstall.md",
            "update": "coding-hub-update.md",
        },
        "expected_skill_triggers": [
            "/coding-hub-search <query>",
            "/coding-hub-browse [category]",
            "/coding-hub-recommend",
            "/coding-hub-install <name>",
            "/coding-hub-uninstall <name>",
            "/coding-hub-update <name>",
        ],
        "expected_inline_refs": [
            "/coding-hub-install <name>",
        ],
    },
    "opencode": {
        "skill": ROOT / "platforms/opencode/skills/coding-hub/SKILL.md",
        "command_dir": ROOT / "platforms/opencode/command",
        "commands": {
            "search": "coding-hub-search.md",
            "browse": "coding-hub-browse.md",
            "recommend": "coding-hub-recommend.md",
            "install": "coding-hub-install.md",
            "uninstall": "coding-hub-uninstall.md",
            "update": "coding-hub-update.md",
        },
        "expected_skill_triggers": [
            "/coding-hub-search <query>",
            "/coding-hub-browse [category]",
            "/coding-hub-recommend",
            "/coding-hub-install <name>",
            "/coding-hub-uninstall <name>",
            "/coding-hub-update <name>",
        ],
        "expected_inline_refs": [
            "/coding-hub-install <name>",
        ],
    },
    "vscode-costrict": {
        "skill": ROOT / "platforms/vscode-costrict/skills/coding-hub/SKILL.md",
        "command_dir": ROOT / "platforms/vscode-costrict/commands/coding-hub",
        "commands": {
            "search": "coding-hub-search.md",
            "browse": "coding-hub-browse.md",
            "recommend": "coding-hub-recommend.md",
            "install": "coding-hub-install.md",
            "uninstall": "coding-hub-uninstall.md",
            "update": "coding-hub-update.md",
        },
        "expected_skill_triggers": [
            "/coding-hub-search <query>",
            "/coding-hub-browse [category]",
            "/coding-hub-recommend",
            "/coding-hub-install <name>",
            "/coding-hub-uninstall <name>",
            "/coding-hub-update <name>",
        ],
        "expected_inline_refs": [
            "/coding-hub-install <name>",
        ],
    },
}


class TestSkillInvocationContract(unittest.TestCase):
    def _read(self, path: Path) -> str:
        self.assertTrue(path.exists(), f"File not found: {path}")
        return path.read_text(encoding="utf-8")

    def test_command_files_exist(self):
        for platform, cfg in PLATFORMS.items():
            for action, rel_name in cfg["commands"].items():
                path = cfg["command_dir"] / rel_name
                self.assertTrue(path.exists(), f"{platform} missing command file for {action}: {path}")

    def test_skill_trigger_strings_match_platform_invocation_style(self):
        for platform, cfg in PLATFORMS.items():
            content = self._read(cfg["skill"])
            for trigger in cfg["expected_skill_triggers"]:
                self.assertIn(trigger, content, f"{platform} SKILL.md missing trigger: {trigger}")

    def test_command_descriptions_advertise_expected_usage(self):
        for platform, cfg in PLATFORMS.items():
            for action, rel_name in cfg["commands"].items():
                path = cfg["command_dir"] / rel_name
                content = self._read(path)
                expected_usage = cfg["expected_skill_triggers"][list(cfg["commands"]).index(action)].split(" | ")[0]
                # We only care that each command file contains the action-specific command string.
                expected_action_usage = next(
                    item for item in cfg["expected_skill_triggers"] if action in item
                )
                self.assertIn(expected_action_usage.split(" [")[0].split(" <")[0], content,
                              f"{platform} {action} command usage mismatch")

    def test_skill_body_refs_use_same_install_and_search_commands(self):
        for platform, cfg in PLATFORMS.items():
            content = self._read(cfg["skill"])
            for ref in cfg["expected_inline_refs"]:
                self.assertIn(ref, content, f"{platform} SKILL.md missing inline ref: {ref}")


if __name__ == "__main__":
    unittest.main()
