import os
import sys
import unittest

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import unified_enrichment  # noqa: E402


class PopulateSignalsTests(unittest.TestCase):
    def test_populate_signals_with_llm_eval(self):
        entry = {
            "id": "test-mcp",
            "type": "mcp",
            "source": "awesome-mcp-servers",
            "stars": 200,
            "description": "A useful MCP server for development",
            "_llm_eval": {
                "coding_relevance": 5,
                "content_quality": 4,
                "specificity": 4,
                "reasoning": "Well-documented server",
                "evaluated_at": "2026-03-31T00:00:00",
                "evaluator": "test-model",
            },
        }
        unified_enrichment.populate_signals(entry)
        ev = entry["evaluation"]

        self.assertEqual(ev["coding_relevance"], 5)
        self.assertEqual(ev["content_quality"], 4)
        self.assertEqual(ev["specificity"], 4)
        self.assertEqual(ev["source_trust"], 4)  # awesome-mcp-servers
        self.assertEqual(ev["reason"], "Well-documented server")
        self.assertEqual(ev["evaluator"], "test-model")
        self.assertIn("confidence", ev)
        self.assertIn("evaluated_at", ev)
        # No final_score or decision (Layer 3 responsibility)
        self.assertNotIn("final_score", ev)
        self.assertNotIn("decision", ev)

    def test_populate_signals_heuristic_only(self):
        entry = {
            "id": "test-rule",
            "type": "rule",
            "source": "awesome-cursorrules",
            "stars": 50,
            "description": "A coding rule for Python development best practices",
        }
        unified_enrichment.populate_signals(entry)
        ev = entry["evaluation"]

        self.assertEqual(ev["source_trust"], 4)
        self.assertEqual(ev["evaluator"], "heuristic")
        self.assertLessEqual(ev["confidence"], 2)  # heuristic = low confidence
        self.assertIn("reason", ev)

    def test_populate_signals_no_specificity_for_rules(self):
        entry = {
            "id": "test-rule",
            "type": "rule",
            "source": "github-search",
        }
        unified_enrichment.populate_signals(entry)
        self.assertNotIn("specificity", entry["evaluation"])

    def test_populate_signals_specificity_for_mcp(self):
        entry = {
            "id": "test-mcp",
            "type": "mcp",
            "source": "mcp.so",
            "_llm_eval": {"specificity": 3, "evaluator": "model"},
        }
        unified_enrichment.populate_signals(entry)
        self.assertEqual(entry["evaluation"]["specificity"], 3)


class ComputeConfidenceTests(unittest.TestCase):
    def test_high_confidence_with_llm_and_signals(self):
        entry = {"stars": 200, "pushed_at": "2026-03-01T00:00:00Z", "description": "A well-documented tool"}
        c = unified_enrichment.compute_confidence(entry, has_llm=True)
        self.assertEqual(c, 5)

    def test_low_confidence_heuristic_only(self):
        entry = {"stars": 0, "description": "x"}
        c = unified_enrichment.compute_confidence(entry, has_llm=False)
        self.assertLessEqual(c, 1)  # base=1, penalty for short desc

    def test_confidence_clamped_1_to_5(self):
        entry = {"stars": 0, "description": ""}
        c = unified_enrichment.compute_confidence(entry, has_llm=False)
        self.assertGreaterEqual(c, 1)
        self.assertLessEqual(c, 5)


class SourceTrustMapTests(unittest.TestCase):
    def test_anthropics_highest(self):
        self.assertEqual(unified_enrichment.SOURCE_TRUST_MAP["anthropics-skills"], 5)

    def test_mcp_so_low(self):
        self.assertEqual(unified_enrichment.SOURCE_TRUST_MAP["mcp.so"], 2)

    def test_unknown_source_default(self):
        self.assertEqual(unified_enrichment.DEFAULT_SOURCE_TRUST, 2)


class GenerateHeuristicReasonTests(unittest.TestCase):
    def test_with_stars_and_install(self):
        entry = {"stars": 245, "install": {"method": "mcp_config"}}
        reason = unified_enrichment.generate_heuristic_reason(entry)
        self.assertIn("245 stars", reason)
        self.assertIn("Easy install", reason)

    def test_fallback_to_source(self):
        entry = {"source": "github-search"}
        reason = unified_enrichment.generate_heuristic_reason(entry)
        self.assertEqual(reason, "Accepted from github-search source")


class HeuristicBackfillTests(unittest.TestCase):
    def test_heuristic_coding_relevance_with_keywords(self):
        entry = {"description": "A CLI tool for API testing and debugging", "tags": ["cli"], "stars": 200}
        score = unified_enrichment._heuristic_coding_relevance(entry)
        # "cli", "api", "test", "debug" = 4 keywords → +2, stars > 100 → +1, base=2 → 5
        self.assertEqual(score, 5)

    def test_heuristic_coding_relevance_baseline(self):
        entry = {"description": "some tool", "tags": [], "stars": 0}
        score = unified_enrichment._heuristic_coding_relevance(entry)
        self.assertEqual(score, 2)  # base only

    def test_heuristic_content_quality_with_stars(self):
        entry = {"description": "A well-documented tool for managing container deployments efficiently with great support and docs", "stars": 600}
        score = unified_enrichment._heuristic_content_quality(entry)
        # desc >= 80 chars → +1, stars > 500 → +2, base=2 → 5
        self.assertEqual(score, 5)

    def test_heuristic_content_quality_short_desc(self):
        entry = {"description": "tool", "stars": 0}
        score = unified_enrichment._heuristic_content_quality(entry)
        # desc < 20 → -1, base=2 → 1
        self.assertEqual(score, 1)

    def test_populate_signals_backfills_when_no_llm(self):
        """Without LLM eval, coding_relevance and content_quality are backfilled."""
        entry = {
            "id": "no-llm",
            "type": "mcp",
            "source": "awesome-mcp-servers",
            "stars": 50,
            "description": "A server for code linting",
        }
        unified_enrichment.populate_signals(entry)
        ev = entry["evaluation"]
        # Must have values (from heuristic), not None
        self.assertIsNotNone(ev.get("coding_relevance"))
        self.assertIsNotNone(ev.get("content_quality"))
        self.assertGreaterEqual(ev["coding_relevance"], 1)
        self.assertGreaterEqual(ev["content_quality"], 1)


class EvaluationTimestampTests(unittest.TestCase):
    def test_preserves_evaluated_at_when_prior_scores_reused(self):
        """Prior evaluated_at is preserved when _prior_evaluation scores are reused."""
        entry = {
            "id": "test",
            "type": "mcp",
            "source": "test",
            "evaluation": {"evaluated_at": "2026-03-15T10:00:00", "evaluator": "claude-haiku-4-5-20251001"},
            "_prior_evaluation": {
                "coding_relevance": 4,
                "content_quality": 3,
                "specificity": 4,
                "evaluated_at": "2026-03-15T10:00:00",
                "evaluator": "claude-haiku-4-5-20251001",
                "confidence": 4,
                "reason": "Good server",
            },
        }
        unified_enrichment.populate_signals(entry)
        self.assertEqual(entry["evaluation"]["evaluated_at"], "2026-03-15T10:00:00")
        self.assertEqual(entry["evaluation"]["evaluator"], "claude-haiku-4-5-20251001")

    def test_fresh_timestamp_on_heuristic_backfill(self):
        """Heuristic backfill gets a fresh timestamp, not the overlaid one."""
        entry = {
            "id": "test",
            "type": "mcp",
            "source": "test",
            "evaluation": {"evaluated_at": "2026-03-15T10:00:00", "evaluator": "claude-haiku-4-5-20251001"},
        }
        unified_enrichment.populate_signals(entry)
        # Heuristic backfill should NOT retain the old model timestamp
        self.assertNotEqual(entry["evaluation"]["evaluated_at"], "2026-03-15T10:00:00")
        self.assertEqual(entry["evaluation"]["evaluator"], "heuristic")


class ApplyEnrichmentBackwardCompatTests(unittest.TestCase):
    def test_apply_enrichment_still_works(self):
        entry = {"id": "skill-a", "category": "tooling", "tags": ["Python"]}
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
        self.assertEqual(entry["evaluation"]["coding_relevance"], 5)
        self.assertEqual(entry["evaluation"]["content_quality"], 4)
        self.assertEqual(entry["evaluation"]["reason"], "Clear testing workflow")


if __name__ == "__main__":
    unittest.main()
