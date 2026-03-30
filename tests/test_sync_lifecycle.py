import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import sync_mcp  # noqa: E402
import sync_skills  # noqa: E402


class SyncMcpLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.orig_catalog_dir = sync_mcp.CATALOG_DIR
        sync_mcp.CATALOG_DIR = self.tmpdir
        self.output_path = os.path.join(self.tmpdir, "index.json")
        with open(self.output_path, "w", encoding="utf-8") as f:
            json.dump(
                [
                    {
                        "id": "persisted-mcp",
                        "type": "mcp",
                        "source_url": "https://github.com/org/persisted-mcp",
                        "added_at": "2025-02-02",
                    }
                ],
                f,
            )

    def tearDown(self):
        sync_mcp.CATALOG_DIR = self.orig_catalog_dir

    @patch("sync_mcp.enrich_missing_configs", side_effect=lambda entries: entries)
    @patch("sync_mcp.merge_three_sources")
    @patch("sync_mcp.parse_awesome_mcp_zh", return_value=[])
    @patch("sync_mcp.parse_awesome_mcp_servers_wong2", return_value=[])
    @patch("sync_mcp.load_seed", return_value=[])
    def test_sync_preserves_added_at_for_existing_entries(
        self,
        mock_seed,
        mock_wong2,
        mock_zh,
        mock_merge,
        mock_enrich,
    ):
        mock_merge.return_value = [
            {
                "id": "persisted-mcp",
                "name": "Persisted MCP",
                "type": "mcp",
                "description": "test",
                "source_url": "https://github.com/org/persisted-mcp",
                "stars": 10,
                "category": "tooling",
                "tags": [],
                "tech_stack": [],
                "install": {"method": "manual"},
                "source": "test",
                "last_synced": "2026-03-30",
            }
        ]

        sync_mcp.sync()

        with open(self.output_path, "r", encoding="utf-8") as f:
            result = json.load(f)
        self.assertEqual(result[0]["added_at"], "2025-02-02")

    def test_backfill_index_adds_added_at_for_existing_entries(self):
        with open(self.output_path, "w", encoding="utf-8") as f:
            json.dump(
                [
                    {
                        "id": "missing-added-at",
                        "type": "mcp",
                        "source_url": "https://github.com/org/missing-added-at",
                        "last_synced": "2026-03-25",
                    }
                ],
                f,
            )

        sync_mcp.backfill_index_added_at()

        with open(self.output_path, "r", encoding="utf-8") as f:
            result = json.load(f)
        self.assertEqual(result[0]["added_at"], "2026-03-25")


class SyncSkillsLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.orig_catalog_dir = sync_skills.CATALOG_DIR
        sync_skills.CATALOG_DIR = self.tmpdir
        self.output_path = os.path.join(self.tmpdir, "index.json")
        with open(self.output_path, "w", encoding="utf-8") as f:
            json.dump(
                [
                    {
                        "id": "persisted-skill",
                        "type": "skill",
                        "source_url": "https://github.com/org/persisted-skill",
                        "added_at": "2025-03-03",
                    }
                ],
                f,
            )

    def tearDown(self):
        sync_skills.CATALOG_DIR = self.orig_catalog_dir

    @patch("sync_skills.evaluate_skills", return_value=[])
    @patch("sync_skills.discover_skills", return_value=[])
    @patch("sync_skills.translate_descriptions")
    @patch("sync_skills.parse_openclaw_skills", return_value=[])
    @patch("sync_skills.parse_antigravity_skills", return_value=[])
    @patch("sync_skills.parse_ai_agent_skills", return_value=[])
    @patch("sync_skills.parse_anthropic_skills")
    def test_sync_preserves_added_at_for_existing_entries(
        self,
        mock_anthropic,
        mock_ai_agent,
        mock_antigravity,
        mock_openclaw,
        mock_translate,
        mock_discover,
        mock_evaluate,
    ):
        mock_anthropic.return_value = [
            {
                "id": "persisted-skill",
                "name": "Persisted Skill",
                "type": "skill",
                "description": "test",
                "source_url": "https://github.com/org/persisted-skill",
                "stars": None,
                "category": "tooling",
                "tags": [],
                "tech_stack": [],
                "install": {
                    "method": "git_clone",
                    "repo": "https://github.com/org/persisted-skill",
                    "files": [],
                },
                "source": "test",
                "last_synced": "2026-03-30",
            }
        ]

        sync_skills.sync()

        with open(self.output_path, "r", encoding="utf-8") as f:
            result = json.load(f)
        self.assertEqual(result[0]["added_at"], "2025-03-03")

    def test_backfill_index_adds_added_at_for_existing_entries(self):
        with open(self.output_path, "w", encoding="utf-8") as f:
            json.dump(
                [
                    {
                        "id": "missing-added-at",
                        "type": "skill",
                        "source_url": "https://github.com/org/missing-added-at",
                        "last_synced": "2026-03-25",
                    }
                ],
                f,
            )

        sync_skills.backfill_index_added_at()

        with open(self.output_path, "r", encoding="utf-8") as f:
            result = json.load(f)
        self.assertEqual(result[0]["added_at"], "2026-03-25")


if __name__ == "__main__":
    unittest.main()
