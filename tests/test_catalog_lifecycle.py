import os
import sys
import unittest
from datetime import datetime, timezone


SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import catalog_lifecycle  # noqa: E402


class AddedAtOverlayTests(unittest.TestCase):
    def test_preserves_existing_added_at_by_id(self):
        existing = [
            {
                "id": "tool-a",
                "type": "mcp",
                "source_url": "https://github.com/org/tool-a",
                "added_at": "2025-01-10",
            }
        ]
        regenerated = [
            {
                "id": "tool-a",
                "type": "mcp",
                "source_url": "https://github.com/org/tool-a",
            },
            {
                "id": "tool-b",
                "type": "mcp",
                "source_url": "https://github.com/org/tool-b",
            },
        ]

        result = catalog_lifecycle.overlay_added_at(
            regenerated, existing, today="2026-03-30"
        )

        self.assertEqual(result[0]["added_at"], "2025-01-10")
        self.assertEqual(result[1]["added_at"], "2026-03-30")

    def test_falls_back_to_normalized_source_url(self):
        existing = [
            {
                "id": "old-id",
                "type": "skill",
                "source_url": "https://github.com/Org/Tool.git",
                "added_at": "2025-02-20",
            }
        ]
        regenerated = [
            {
                "id": "new-id",
                "type": "skill",
                "source_url": "https://github.com/org/tool/",
            }
        ]

        result = catalog_lifecycle.overlay_added_at(
            regenerated, existing, today="2026-03-30"
        )

        self.assertEqual(result[0]["added_at"], "2025-02-20")

    def test_only_mcp_and_skill_receive_added_at(self):
        regenerated = [
            {
                "id": "rule-a",
                "type": "rule",
                "source_url": "https://github.com/org/rule-a",
            },
            {
                "id": "prompt-a",
                "type": "prompt",
                "source_url": "https://github.com/org/prompt-a",
            },
        ]

        result = catalog_lifecycle.overlay_added_at(regenerated, [], today="2026-03-30")

        self.assertNotIn("added_at", result[0])
        self.assertNotIn("added_at", result[1])

    def test_backfill_missing_added_at_uses_last_synced(self):
        entries = [
            {
                "id": "existing-skill",
                "type": "skill",
                "source_url": "https://github.com/org/existing-skill",
                "last_synced": "2026-03-25",
            }
        ]

        result = catalog_lifecycle.backfill_missing_added_at(
            entries, today="2026-03-30"
        )

        self.assertEqual(result[0]["added_at"], "2026-03-25")

    def test_backfill_prefers_earlier_pushed_at_date_when_available(self):
        entries = [
            {
                "id": "older-mcp",
                "type": "mcp",
                "source_url": "https://github.com/org/older-mcp",
                "last_synced": "2026-03-25",
                "pushed_at": "2024-01-15T12:00:00Z",
            }
        ]

        result = catalog_lifecycle.backfill_missing_added_at(
            entries, today="2026-03-30"
        )

        self.assertEqual(result[0]["added_at"], "2024-01-15")

    def test_backfill_does_not_overwrite_existing_added_at(self):
        entries = [
            {
                "id": "existing-mcp",
                "type": "mcp",
                "source_url": "https://github.com/org/existing-mcp",
                "last_synced": "2026-03-25",
                "added_at": "2025-01-01",
            }
        ]

        result = catalog_lifecycle.backfill_missing_added_at(
            entries, today="2026-03-30"
        )

        self.assertEqual(result[0]["added_at"], "2025-01-01")


class IncrementalRecrawlCandidateTests(unittest.TestCase):
    def setUp(self):
        self.today = datetime(2026, 3, 30, tzinfo=timezone.utc)

    def _entry(
        self,
        entry_id,
        *,
        freshness_label="abandoned",
        added_at="2025-01-01",
        entry_type="mcp",
    ):
        return {
            "id": entry_id,
            "type": entry_type,
            "name": entry_id,
            "source_url": f"https://github.com/org/{entry_id}",
            "added_at": added_at,
            "health": {
                "freshness_label": freshness_label,
                "score": 42,
            },
        }

    def test_old_entry_is_queued_with_metadata(self):
        candidates, state = catalog_lifecycle.build_incremental_recrawl_candidates(
            [self._entry("old-tool")],
            {},
            now=self.today,
            threshold_days=365,
            cooldown_days=30,
            max_candidates=50,
        )

        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate["id"], "old-tool")
        self.assertEqual(candidate["type"], "mcp")
        self.assertEqual(candidate["enqueue_reason"], "age-threshold")
        self.assertIn("priority", candidate)
        self.assertIn("old-tool::mcp", state["items"])

    def test_recently_queued_entry_is_skipped_during_cooldown(self):
        existing_state = {
            "items": {
                "old-tool::mcp": {
                    "last_queued_at": "2026-03-20",
                }
            }
        }

        candidates, state = catalog_lifecycle.build_incremental_recrawl_candidates(
            [self._entry("old-tool")],
            existing_state,
            now=self.today,
            threshold_days=365,
            cooldown_days=30,
            max_candidates=50,
        )

        self.assertEqual(candidates, [])

    def test_abandoned_entries_are_prioritized_before_active_ones(self):
        entries = [
            self._entry(
                "active-tool",
                freshness_label="active",
                added_at="2024-01-01",
                entry_type="skill",
            ),
            self._entry(
                "abandoned-tool",
                freshness_label="abandoned",
                added_at="2024-01-01",
                entry_type="mcp",
            ),
        ]

        candidates, state = catalog_lifecycle.build_incremental_recrawl_candidates(
            entries,
            {},
            now=self.today,
            threshold_days=365,
            cooldown_days=30,
            max_candidates=50,
        )

        self.assertEqual(
            [c["id"] for c in candidates], ["abandoned-tool", "active-tool"]
        )


if __name__ == "__main__":
    unittest.main()
