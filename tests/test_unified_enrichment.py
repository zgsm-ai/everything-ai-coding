import os
import sys
import unittest


SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import unified_enrichment  # noqa: E402


class UnifiedEnrichmentTests(unittest.TestCase):
    def test_apply_enrichment_updates_top_level_and_evaluation(self):
        entry = {
            "id": "skill-a",
            "category": "tooling",
            "tags": ["Python"],
        }

        unified_enrichment.apply_enrichment(
            entry,
            category="testing",
            tags=["Python", " Playwright ", "python"],
            description_zh="浏览器自动化技能",
            coding_relevance=5,
            content_quality=4,
            reason="Clear testing workflow",
        )

        self.assertEqual(entry["category"], "testing")
        self.assertEqual(entry["tags"], ["python", "playwright"])
        self.assertEqual(entry["description_zh"], "浏览器自动化技能")
        self.assertEqual(entry["coding_relevance"], 5)
        self.assertEqual(entry["quality_score"], 4)
        self.assertEqual(entry["evaluation"]["coding_relevance"], 5)
        self.assertEqual(entry["evaluation"]["content_quality"], 4)
        self.assertEqual(entry["evaluation"]["final_score"], 90)
        self.assertEqual(entry["evaluation"]["decision"], "accept")

    def test_ensure_evaluation_backfills_legacy_scores(self):
        entry = {
            "id": "legacy-skill",
            "coding_relevance": 4,
            "quality_score": 5,
        }

        unified_enrichment.ensure_evaluation(entry)

        self.assertEqual(entry["evaluation"]["coding_relevance"], 4)
        self.assertEqual(entry["evaluation"]["content_quality"], 5)
        self.assertEqual(entry["evaluation"]["final_score"], 90)


if __name__ == "__main__":
    unittest.main()
