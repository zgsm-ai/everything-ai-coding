import os
import sys
import json
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import llm_evaluator  # noqa: E402


class TypeConfigsTests(unittest.TestCase):
    def test_all_types_have_configs(self):
        for t in ["mcp", "skill", "rule", "prompt"]:
            self.assertIn(t, llm_evaluator.TYPE_CONFIGS)
            self.assertIn("system_prompt", llm_evaluator.TYPE_CONFIGS[t])
            self.assertIn("dimensions", llm_evaluator.TYPE_CONFIGS[t])

    def test_mcp_skill_have_specificity(self):
        self.assertIn("specificity", llm_evaluator.TYPE_CONFIGS["mcp"]["dimensions"])
        self.assertIn("specificity", llm_evaluator.TYPE_CONFIGS["skill"]["dimensions"])

    def test_rule_prompt_no_specificity(self):
        self.assertNotIn("specificity", llm_evaluator.TYPE_CONFIGS["rule"]["dimensions"])
        self.assertNotIn("specificity", llm_evaluator.TYPE_CONFIGS["prompt"]["dimensions"])


class CacheMigrationTests(unittest.TestCase):
    def test_load_cache_migrates_from_old_location(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            old_path = os.path.join(tmpdir, "old_cache.json")
            new_path = os.path.join(tmpdir, "new_cache.json")
            old_data = {"test-id": {"coding_relevance": 4, "quality_score": 5, "evaluated_at": "2026-03-01T00:00:00"}}
            with open(old_path, "w") as f:
                json.dump(old_data, f)

            with patch.object(llm_evaluator, "CACHE_PATH", new_path), \
                 patch.object(llm_evaluator, "OLD_CACHE_PATH", old_path):
                cache = llm_evaluator.load_cache()

            self.assertEqual(cache["skill:test-id"]["coding_relevance"], 4)
            self.assertEqual(cache["skill:test-id"]["content_quality"], 5)
            # New cache file should have been created
            self.assertTrue(os.path.exists(new_path))

    def test_migrated_entries_are_expired(self):
        """Legacy entries get epoch evaluated_at so is_cache_valid returns False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_path = os.path.join(tmpdir, "old_cache.json")
            new_path = os.path.join(tmpdir, "new_cache.json")
            old_data = {"test-id": {"coding_relevance": 4, "quality_score": 5, "evaluated_at": "2026-03-01T00:00:00"}}
            with open(old_path, "w") as f:
                json.dump(old_data, f)

            with patch.object(llm_evaluator, "CACHE_PATH", new_path), \
                 patch.object(llm_evaluator, "OLD_CACHE_PATH", old_path):
                cache = llm_evaluator.load_cache()

            migrated = cache["skill:test-id"]
            self.assertFalse(llm_evaluator.is_cache_valid(migrated))

    def test_old_cache_merged_into_partial_new_cache(self):
        """Old cache entries are merged even when new cache already has some entries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_path = os.path.join(tmpdir, "old_cache.json")
            new_path = os.path.join(tmpdir, "new_cache.json")
            old_data = {
                "already-migrated": {"coding_relevance": 3, "quality_score": 3, "evaluated_at": "2026-01-01T00:00:00"},
                "not-yet-migrated": {"coding_relevance": 2, "quality_score": 2, "evaluated_at": "2026-01-01T00:00:00"},
            }
            # New cache has one entry from a previous partial run
            new_data = {"skill:already-migrated": {"coding_relevance": 5, "content_quality": 5, "evaluated_at": "2026-03-25T00:00:00", "evaluator": "fresh"}}
            with open(old_path, "w") as f:
                json.dump(old_data, f)
            with open(new_path, "w") as f:
                json.dump(new_data, f)

            with patch.object(llm_evaluator, "CACHE_PATH", new_path), \
                 patch.object(llm_evaluator, "OLD_CACHE_PATH", old_path):
                cache = llm_evaluator.load_cache()

            # Fresh entry in new cache must NOT be overwritten by old cache
            self.assertEqual(cache["skill:already-migrated"]["evaluator"], "fresh")
            # Previously missing entry must be merged in
            self.assertIn("skill:not-yet-migrated", cache)

    def test_load_cache_prefers_new_location(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            old_path = os.path.join(tmpdir, "old_cache.json")
            new_path = os.path.join(tmpdir, "new_cache.json")
            with open(old_path, "w") as f:
                json.dump({"old": True}, f)
            with open(new_path, "w") as f:
                json.dump({"new": True}, f)

            with patch.object(llm_evaluator, "CACHE_PATH", new_path), \
                 patch.object(llm_evaluator, "OLD_CACHE_PATH", old_path):
                cache = llm_evaluator.load_cache()

            self.assertIn("new", cache)
            self.assertNotIn("old", cache)


class EnrichQualityTests(unittest.TestCase):
    @patch("llm_evaluator._call_llm")
    @patch("llm_evaluator.save_cache")
    @patch("llm_evaluator.load_cache", return_value={})
    def test_enrich_quality_returns_eval_data(self, mock_load, mock_save, mock_call):
        mock_call.return_value = [
            {
                "id": "test-mcp",
                "coding_relevance": 4,
                "content_quality": 3,
                "specificity": 4,
                "reasoning": "Useful server",
            }
        ]
        entries = [
            {"id": "test-mcp", "name": "Test MCP", "type": "mcp", "description": "test"}
        ]
        with patch.object(llm_evaluator, "LLM_BASE_URL", "http://test"), \
             patch.object(llm_evaluator, "LLM_API_KEY", "key"):
            result = llm_evaluator.enrich_quality(entries)

        self.assertIn("test-mcp", result)
        self.assertEqual(result["test-mcp"]["coding_relevance"], 4)
        self.assertEqual(result["test-mcp"]["content_quality"], 3)

    @patch("llm_evaluator.load_cache", return_value={})
    def test_enrich_quality_empty_when_no_llm_and_no_cache(self, mock_load):
        """No LLM + no cache = empty results."""
        with patch.object(llm_evaluator, "LLM_BASE_URL", ""), \
             patch.object(llm_evaluator, "LLM_API_KEY", ""):
            result = llm_evaluator.enrich_quality([{"id": "x", "type": "mcp"}])
        self.assertEqual(result, {})

    @patch("llm_evaluator.load_cache")
    def test_enrich_quality_returns_cache_when_no_llm(self, mock_load):
        """No LLM credentials but warm cache — cached scores are returned."""
        from datetime import datetime
        fresh_ts = datetime.now().isoformat()
        mock_load.return_value = {
            "mcp:cached-mcp": {
                "coding_relevance": 5,
                "content_quality": 4,
                "specificity": 3,
                "evaluated_at": fresh_ts,
                "evaluator": "test-model",
            }
        }
        entries = [{"id": "cached-mcp", "type": "mcp"}]
        with patch.object(llm_evaluator, "LLM_BASE_URL", ""), \
             patch.object(llm_evaluator, "LLM_API_KEY", ""):
            result = llm_evaluator.enrich_quality(entries)
        self.assertIn("cached-mcp", result)
        self.assertEqual(result["cached-mcp"]["coding_relevance"], 5)

    @patch("llm_evaluator._call_llm")
    @patch("llm_evaluator.save_cache")
    @patch("llm_evaluator.load_cache")
    def test_batch_failure_falls_back_to_expired_cache(self, mock_load, mock_save, mock_call):
        """When _call_llm fails, expired cache entries are used as fallback."""
        mock_load.return_value = {
            "mcp:stale-mcp": {
                "coding_relevance": 3,
                "content_quality": 2,
                "evaluated_at": "2020-01-01T00:00:00",  # expired
                "evaluator": "old-model",
            }
        }
        mock_call.return_value = None  # batch failure
        entries = [{"id": "stale-mcp", "type": "mcp", "description": "test"}]
        with patch.object(llm_evaluator, "LLM_BASE_URL", "http://test"), \
             patch.object(llm_evaluator, "LLM_API_KEY", "key"):
            result = llm_evaluator.enrich_quality(entries)
        self.assertIn("stale-mcp", result)
        self.assertEqual(result["stale-mcp"]["coding_relevance"], 3)


if __name__ == "__main__":
    unittest.main()
