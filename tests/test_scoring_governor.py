import os
import sys
import unittest
import unittest.mock

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import scoring_governor  # noqa: E402


class ApplyGovernanceTests(unittest.TestCase):
    def test_harness_passthrough(self):
        """Entries with final_score from harness are passed through as-is."""
        entries = [
            {
                "id": "e1",
                "type": "mcp",
                "evaluation": {
                    "model_id": "deepseek-chat",
                    "final_score": 85.0,
                    "decision": "accept",
                },
            },
        ]
        result = scoring_governor.apply_governance(entries)
        self.assertEqual(result[0]["final_score"], 85.0)
        self.assertEqual(result[0]["decision"], "accept")

    def test_unevaluated_gets_defaults(self):
        """Entries without final_score get score=0, decision=review."""
        entries = [{"id": "e1", "type": "mcp"}]
        result = scoring_governor.apply_governance(entries)
        self.assertEqual(result[0]["final_score"], 0)
        self.assertEqual(result[0]["decision"], "review")
        self.assertEqual(result[0]["evaluation"]["final_score"], 0)
        self.assertEqual(result[0]["evaluation"]["decision"], "review")

    def test_reject_filtered_when_not_dry_run(self):
        entries = [
            {
                "id": "bad",
                "type": "mcp",
                "evaluation": {"final_score": 30.0, "decision": "reject"},
            },
        ]
        with unittest.mock.patch.dict(os.environ, {"EVAL_DRY_RUN": "false"}):
            result = scoring_governor.apply_governance(entries)
        self.assertEqual(len(result), 0)

    def test_reject_kept_in_dry_run(self):
        entries = [
            {
                "id": "bad",
                "type": "mcp",
                "evaluation": {"final_score": 30.0, "decision": "reject"},
            },
        ]
        with unittest.mock.patch.dict(os.environ, {"EVAL_DRY_RUN": "true"}):
            result = scoring_governor.apply_governance(entries)
        self.assertEqual(len(result), 1)

    def test_mixed_entries(self):
        """Mix of harness-evaluated, unevaluated, and rejected entries."""
        entries = [
            {"id": "good", "evaluation": {"final_score": 80.0, "decision": "accept"}},
            {"id": "new", "type": "skill"},
            {"id": "bad", "evaluation": {"final_score": 20.0, "decision": "reject"}},
        ]
        with unittest.mock.patch.dict(os.environ, {"EVAL_DRY_RUN": "false"}):
            result = scoring_governor.apply_governance(entries)
        ids = [e["id"] for e in result]
        self.assertIn("good", ids)
        self.assertIn("new", ids)  # unevaluated → review → kept
        self.assertNotIn("bad", ids)  # reject → filtered


if __name__ == "__main__":
    unittest.main()
