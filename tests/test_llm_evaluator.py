import os
import sys
import unittest
from unittest.mock import patch


SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import llm_evaluator  # noqa: E402


class LlmEvaluatorUnifiedEnrichmentTests(unittest.TestCase):
    @patch("llm_evaluator.call_llm")
    @patch("llm_evaluator.save_cache")
    @patch("llm_evaluator.load_cache", return_value={})
    def test_evaluate_skills_populates_evaluation_fields_via_unified_contract(
        self,
        mock_load_cache,
        mock_save_cache,
        mock_call_llm,
    ):
        candidate = {
            "id": "test-skill",
            "name": "Test Skill",
            "type": "skill",
            "description": "Testing helper for code workflows",
            "source_url": "https://github.com/org/test-skill",
            "stars": 100,
            "category": "tooling",
            "tags": ["Python"],
            "tech_stack": [],
            "install": {
                "method": "git_clone",
                "repo": "https://github.com/org/test-skill",
                "files": [],
            },
            "source": "registry",
            "last_synced": "2026-03-30",
            "_keyword_match": True,
        }
        mock_call_llm.return_value = [
            {
                "name": "Test Skill",
                "coding_relevance": 5,
                "quality_score": 4,
                "suggested_category": "testing",
                "suggested_tags": ["Python", "Playwright"],
                "description_zh": "测试与自动化开发技能",
                "reasoning": "Clear testing workflow",
            }
        ]

        with (
            patch.object(llm_evaluator, "LLM_BASE_URL", "http://llm.test/v1"),
            patch.object(llm_evaluator, "LLM_API_KEY", "test-key"),
            patch.object(llm_evaluator, "LLM_EVAL_LIMIT", 10),
        ):
            result = llm_evaluator.evaluate_skills([candidate])

        self.assertEqual(len(result), 1)
        entry = result[0]
        self.assertEqual(entry["category"], "testing")
        self.assertEqual(entry["tags"], ["python", "playwright"])
        self.assertEqual(entry["description_zh"], "测试与自动化开发技能")
        self.assertEqual(entry["evaluation"]["coding_relevance"], 5)
        self.assertEqual(entry["evaluation"]["content_quality"], 4)
        self.assertEqual(entry["evaluation"]["reason"], "Clear testing workflow")


if __name__ == "__main__":
    unittest.main()
