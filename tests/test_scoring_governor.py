import os
import sys
import unittest

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import scoring_governor  # noqa: E402


class ComputeFinalScoreTests(unittest.TestCase):
    def test_mcp_with_all_signals(self):
        entry = {
            "type": "mcp",
            "evaluation": {
                "coding_relevance": 5,
                "content_quality": 4,
                "specificity": 4,
                "source_trust": 4,
                "confidence": 3,
            },
        }
        score = scoring_governor.compute_final_score(entry)
        # (5/5*100)*0.30 + (4/5*100)*0.25 + (4/5*100)*0.20 + (4/5*100)*0.15 + (3/5*100)*0.10
        # = 30 + 20 + 16 + 12 + 6 = 84
        self.assertEqual(score, 84)

    def test_rule_without_specificity(self):
        entry = {
            "type": "rule",
            "evaluation": {
                "coding_relevance": 4,
                "content_quality": 3,
                "source_trust": 3,
                "confidence": 2,
            },
        }
        score = scoring_governor.compute_final_score(entry)
        # (4/5*100)*0.35 + (3/5*100)*0.35 + (3/5*100)*0.15 + (2/5*100)*0.15
        # = 28 + 21 + 9 + 6 = 64
        self.assertEqual(score, 64)

    def test_empty_evaluation(self):
        entry = {"type": "mcp", "evaluation": {}}
        score = scoring_governor.compute_final_score(entry)
        self.assertEqual(score, 0)

    def test_score_clamped_to_100(self):
        entry = {
            "type": "mcp",
            "evaluation": {
                "coding_relevance": 5,
                "content_quality": 5,
                "specificity": 5,
                "source_trust": 5,
                "confidence": 5,
            },
        }
        score = scoring_governor.compute_final_score(entry)
        self.assertEqual(score, 100)


class JudgeDecisionTests(unittest.TestCase):
    def test_mcp_accept(self):
        entry = {"type": "mcp", "evaluation": {"final_score": 55}}
        self.assertEqual(scoring_governor.judge_decision(entry), "accept")

    def test_mcp_review(self):
        entry = {"type": "mcp", "evaluation": {"final_score": 40}}
        self.assertEqual(scoring_governor.judge_decision(entry), "review")

    def test_mcp_reject(self):
        entry = {"type": "mcp", "evaluation": {"final_score": 30}}
        self.assertEqual(scoring_governor.judge_decision(entry), "reject")

    def test_rule_accept(self):
        entry = {"type": "rule", "evaluation": {"final_score": 45}}
        self.assertEqual(scoring_governor.judge_decision(entry), "accept")

    def test_rule_review(self):
        entry = {"type": "rule", "evaluation": {"final_score": 30}}
        self.assertEqual(scoring_governor.judge_decision(entry), "review")

    def test_rule_reject(self):
        entry = {"type": "rule", "evaluation": {"final_score": 20}}
        self.assertEqual(scoring_governor.judge_decision(entry), "reject")

    def test_cr_le1_low_score_reject(self):
        """coding_relevance<=1 and final_score<35 -> reject regardless of type."""
        entry = {"type": "mcp", "evaluation": {"final_score": 30, "coding_relevance": 1}}
        self.assertEqual(scoring_governor.judge_decision(entry), "reject")

    def test_cr_le1_mid_score_review(self):
        """coding_relevance<=1 and 35<=final_score<55 -> review."""
        entry = {"type": "mcp", "evaluation": {"final_score": 45, "coding_relevance": 1}}
        self.assertEqual(scoring_governor.judge_decision(entry), "review")

    def test_cr_le1_high_score_still_review(self):
        """coding_relevance<=1 never auto-accepts, even with high final_score."""
        entry = {"type": "mcp", "evaluation": {"final_score": 60, "coding_relevance": 1}}
        self.assertEqual(scoring_governor.judge_decision(entry), "review")

    def test_cr_default_skips_hard_rule(self):
        """Without coding_relevance set, default cr=3 so hard rule is skipped."""
        entry = {"type": "mcp", "evaluation": {"final_score": 55}}
        self.assertEqual(scoring_governor.judge_decision(entry), "accept")


class ApplyGovernanceTests(unittest.TestCase):
    def test_rejects_filtered_out(self):
        entries = [
            {
                "id": "good",
                "type": "mcp",
                "evaluation": {
                    "coding_relevance": 5,
                    "content_quality": 4,
                    "specificity": 4,
                    "source_trust": 4,
                    "confidence": 3,
                },
            },
            {
                "id": "bad",
                "type": "mcp",
                "evaluation": {
                    "coding_relevance": 1,
                    "content_quality": 1,
                    "specificity": 1,
                    "source_trust": 1,
                    "confidence": 1,
                },
            },
        ]
        with unittest.mock.patch.object(scoring_governor, "EVAL_DRY_RUN", False):
            result = scoring_governor.apply_governance(entries)
        ids = [e["id"] for e in result]
        self.assertIn("good", ids)
        self.assertNotIn("bad", ids)

    def test_health_computed(self):
        entries = [
            {
                "id": "e1",
                "type": "mcp",
                "evaluation": {
                    "coding_relevance": 5,
                    "content_quality": 5,
                    "specificity": 5,
                    "source_trust": 5,
                    "confidence": 5,
                },
            },
        ]
        with unittest.mock.patch.object(scoring_governor, "EVAL_DRY_RUN", False):
            result = scoring_governor.apply_governance(entries)
        self.assertIn("health", result[0])
        self.assertIn("score", result[0]["health"])

    def test_dry_run_keeps_rejects(self):
        entries = [
            {
                "id": "bad",
                "type": "mcp",
                "evaluation": {
                    "coding_relevance": 1,
                    "content_quality": 1,
                    "specificity": 1,
                    "source_trust": 1,
                    "confidence": 1,
                },
            },
        ]
        with unittest.mock.patch.object(scoring_governor, "EVAL_DRY_RUN", True):
            result = scoring_governor.apply_governance(entries)
        self.assertEqual(len(result), 1)
        # Dry-run still computes governance metadata (score, decision, health)
        # so the catalog retains correct sorting — only rejection is suppressed.
        self.assertIn("final_score", result[0]["evaluation"])
        self.assertIn("health", result[0])


import unittest.mock  # noqa: E402

if __name__ == "__main__":
    unittest.main()
