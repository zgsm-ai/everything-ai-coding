import os
import sys
import json
import hashlib
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import deep_reviewer  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_entry(entry_type, entry_id="test-id", source_url="", **extra):
    """Build a minimal entry dict for testing."""
    entry = {"id": entry_id, "type": entry_type, "name": "Test", "description": "desc"}
    if source_url:
        entry["source_url"] = source_url
    entry.update(extra)
    return entry


def _sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ===========================================================================
# 1. URL Construction (build_content_url)
# ===========================================================================

class BuildContentUrlTests(unittest.TestCase):

    # --- MCP ---

    def test_mcp_standard_github_url(self):
        entry = _make_entry("mcp", source_url="https://github.com/owner/repo")
        result = deep_reviewer.build_content_url(entry)
        self.assertIsNotNone(result)
        repo_slug, primary, fallback = result
        self.assertEqual(repo_slug, "owner/repo")
        self.assertEqual(primary, "README.md")
        self.assertIsNone(fallback)

    def test_mcp_github_url_with_git_suffix(self):
        entry = _make_entry("mcp", source_url="https://github.com/owner/repo.git")
        result = deep_reviewer.build_content_url(entry)
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "owner/repo")
        self.assertEqual(result[1], "README.md")

    def test_mcp_github_url_with_trailing_slash(self):
        entry = _make_entry("mcp", source_url="https://github.com/owner/repo/")
        result = deep_reviewer.build_content_url(entry)
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "owner/repo")

    def test_mcp_non_github_url_returns_none(self):
        entry = _make_entry("mcp", source_url="https://gitlab.com/owner/repo")
        result = deep_reviewer.build_content_url(entry)
        self.assertIsNone(result)

    def test_mcp_no_source_url_returns_none(self):
        entry = _make_entry("mcp")
        result = deep_reviewer.build_content_url(entry)
        self.assertIsNone(result)

    # --- Skill ---

    def test_skill_subdirectory_url(self):
        entry = _make_entry(
            "skill",
            source_url="https://github.com/owner/repo/tree/main/skills/foo",
        )
        result = deep_reviewer.build_content_url(entry)
        self.assertIsNotNone(result)
        repo_slug, primary, fallback = result
        self.assertEqual(repo_slug, "owner/repo")
        self.assertEqual(primary, "skills/foo/SKILL.md")
        self.assertEqual(fallback, "skills/foo/README.md")

    def test_skill_root_level_repo(self):
        entry = _make_entry("skill", source_url="https://github.com/owner/skill-repo")
        result = deep_reviewer.build_content_url(entry)
        self.assertIsNotNone(result)
        repo_slug, primary, fallback = result
        self.assertEqual(repo_slug, "owner/skill-repo")
        self.assertEqual(primary, "SKILL.md")
        self.assertEqual(fallback, "README.md")

    # --- Rule ---

    def test_rule_with_install_files(self):
        entry = _make_entry(
            "rule",
            install={"files": ["https://raw.githubusercontent.com/o/r/main/.cursorrules"]},
        )
        result = deep_reviewer.build_content_url(entry)
        self.assertIsNotNone(result)
        repo_slug, primary, fallback = result
        self.assertEqual(repo_slug, "__raw_url__")
        self.assertEqual(primary, "https://raw.githubusercontent.com/o/r/main/.cursorrules")
        self.assertIsNone(fallback)

    def test_rule_without_install_files_returns_none(self):
        entry = _make_entry("rule")
        result = deep_reviewer.build_content_url(entry)
        self.assertIsNone(result)

    def test_rule_empty_files_list_returns_none(self):
        entry = _make_entry("rule", install={"files": []})
        result = deep_reviewer.build_content_url(entry)
        self.assertIsNone(result)

    # --- Prompt ---

    def test_prompt_returns_none(self):
        entry = _make_entry("prompt", source_url="https://github.com/owner/repo")
        result = deep_reviewer.build_content_url(entry)
        self.assertIsNone(result)

    # --- Unknown type ---

    def test_unknown_type_returns_none(self):
        entry = _make_entry("unknown", source_url="https://github.com/owner/repo")
        result = deep_reviewer.build_content_url(entry)
        self.assertIsNone(result)


# ===========================================================================
# 2. Cache logic (_is_cache_hit)
# ===========================================================================

class CacheHitTests(unittest.TestCase):

    def test_cache_hit_within_30_days_matching_hash(self):
        content = "hello world"
        cache_entry = {
            "reviewed_at": datetime.now().isoformat(),
            "content_hash": _sha256(content),
        }
        self.assertTrue(deep_reviewer._is_cache_hit(cache_entry, content))

    def test_cache_expired_over_30_days(self):
        content = "hello world"
        old_date = (datetime.now() - timedelta(days=31)).isoformat()
        cache_entry = {
            "reviewed_at": old_date,
            "content_hash": _sha256(content),
        }
        self.assertFalse(deep_reviewer._is_cache_hit(cache_entry, content))

    def test_cache_content_hash_mismatch(self):
        content = "new content"
        cache_entry = {
            "reviewed_at": datetime.now().isoformat(),
            "content_hash": _sha256("old content"),
        }
        self.assertFalse(deep_reviewer._is_cache_hit(cache_entry, content))

    def test_cache_missing_reviewed_at(self):
        cache_entry = {"content_hash": _sha256("x")}
        self.assertFalse(deep_reviewer._is_cache_hit(cache_entry, "x"))

    def test_cache_empty_reviewed_at(self):
        cache_entry = {"reviewed_at": "", "content_hash": _sha256("x")}
        self.assertFalse(deep_reviewer._is_cache_hit(cache_entry, "x"))

    def test_cache_invalid_date_format(self):
        cache_entry = {"reviewed_at": "not-a-date", "content_hash": _sha256("x")}
        self.assertFalse(deep_reviewer._is_cache_hit(cache_entry, "x"))

    def test_cache_no_hash_still_valid_if_not_expired(self):
        """If cache has no content_hash stored, hash comparison is skipped (cached_hash is empty)."""
        cache_entry = {
            "reviewed_at": datetime.now().isoformat(),
            "content_hash": "",
        }
        self.assertTrue(deep_reviewer._is_cache_hit(cache_entry, "anything"))

    def test_cache_exactly_30_days_is_expired(self):
        """timedelta(days=30) >= timedelta(days=30) is True, so exactly 30 days is expired."""
        content = "test"
        boundary_date = (datetime.now() - timedelta(days=30)).isoformat()
        cache_entry = {
            "reviewed_at": boundary_date,
            "content_hash": _sha256(content),
        }
        self.assertFalse(deep_reviewer._is_cache_hit(cache_entry, content))


# ===========================================================================
# 3. Content fetch (fetch_content) with mocked HTTP
# ===========================================================================

class FetchContentTests(unittest.TestCase):

    @patch("deep_reviewer._fetch_url")
    def test_http_200_with_content(self, mock_fetch_url):
        mock_fetch_url.return_value = "# README\nSome content"
        entry = _make_entry("mcp", source_url="https://github.com/owner/repo")
        result = deep_reviewer.fetch_content(entry)
        self.assertEqual(result, "# README\nSome content")
        mock_fetch_url.assert_called_once_with(
            "https://raw.githubusercontent.com/owner/repo/main/README.md"
        )

    @patch("deep_reviewer._fetch_url")
    def test_http_200_empty_content(self, mock_fetch_url):
        mock_fetch_url.return_value = ""
        entry = _make_entry("mcp", source_url="https://github.com/owner/repo")
        result = deep_reviewer.fetch_content(entry)
        # Empty string from _fetch_url (404) with no fallback → return ""
        self.assertEqual(result, "")

    @patch("deep_reviewer._fetch_url")
    def test_http_404_both_paths_returns_empty(self, mock_fetch_url):
        """When both primary and fallback return empty string (404), fetch_content returns empty string."""
        mock_fetch_url.return_value = ""
        entry = _make_entry(
            "skill",
            source_url="https://github.com/owner/repo/tree/main/sub",
        )
        result = deep_reviewer.fetch_content(entry)
        self.assertEqual(result, "")
        # Should have tried both SKILL.md and README.md URLs
        self.assertEqual(mock_fetch_url.call_count, 2)

    @patch("deep_reviewer._fetch_url")
    def test_skill_fallback_to_readme(self, mock_fetch_url):
        """Skill: primary SKILL.md returns empty (404), fallback README.md succeeds."""
        mock_fetch_url.side_effect = ["", "Fallback content"]
        entry = _make_entry(
            "skill",
            source_url="https://github.com/owner/repo/tree/main/sub",
        )
        result = deep_reviewer.fetch_content(entry)
        self.assertEqual(result, "Fallback content")

    @patch("deep_reviewer._fetch_url")
    def test_rule_fetch_via_raw_url(self, mock_fetch_url):
        mock_fetch_url.return_value = "rule content here"
        entry = _make_entry(
            "rule",
            install={"files": ["https://raw.githubusercontent.com/o/r/main/.rules"]},
        )
        result = deep_reviewer.fetch_content(entry)
        self.assertEqual(result, "rule content here")
        mock_fetch_url.assert_called_once_with(
            "https://raw.githubusercontent.com/o/r/main/.rules"
        )

    def test_prompt_fetch_returns_none(self):
        entry = _make_entry("prompt", source_url="https://github.com/owner/repo")
        result = deep_reviewer.fetch_content(entry)
        self.assertIsNone(result)

    @patch("deep_reviewer._fetch_url")
    def test_content_truncated_to_limit(self, mock_fetch_url):
        long_content = "x" * 10000
        # _fetch_url already truncates to CONTENT_TRUNCATE internally
        mock_fetch_url.return_value = long_content[:deep_reviewer.CONTENT_TRUNCATE]
        entry = _make_entry("mcp", source_url="https://github.com/owner/repo")
        result = deep_reviewer.fetch_content(entry)
        self.assertEqual(len(result), deep_reviewer.CONTENT_TRUNCATE)

    @patch("deep_reviewer._fetch_url")
    def test_rule_fetch_network_error_returns_none(self, mock_fetch_url):
        mock_fetch_url.return_value = None  # network error
        entry = _make_entry(
            "rule",
            install={"files": ["https://raw.githubusercontent.com/o/r/main/.rules"]},
        )
        result = deep_reviewer.fetch_content(entry)
        self.assertIsNone(result)


# ===========================================================================
# 4. LLM failure keeps review
# ===========================================================================

class LLMFailureKeepsReviewTests(unittest.TestCase):

    @patch("deep_reviewer._save_cache")
    @patch("deep_reviewer._load_cache", return_value={})
    @patch("deep_reviewer._call_llm_reclassify", return_value=None)
    @patch("deep_reviewer.fetch_content")
    def test_llm_failure_keeps_review_decision(
        self, mock_fetch, mock_llm, mock_load_cache, mock_save_cache
    ):
        """When LLM fails (returns None), entry stays as 'review'."""
        mock_fetch.return_value = "Some valid content"
        entry = _make_entry("mcp", source_url="https://github.com/owner/repo")
        entry["evaluation"] = {"decision": "review", "final_score": 40}

        deep_reviewer.deep_review_entries([entry])

        # Decision should remain 'review' — not changed by _apply_classification
        self.assertEqual(entry["evaluation"]["decision"], "review")
        # deep_review_category should NOT be set
        self.assertNotIn("deep_review_category", entry["evaluation"])

    @patch("deep_reviewer._save_cache")
    @patch("deep_reviewer._load_cache", return_value={})
    @patch("deep_reviewer._call_llm_reclassify")
    @patch("deep_reviewer.fetch_content")
    def test_llm_success_updates_decision(
        self, mock_fetch, mock_llm, mock_load_cache, mock_save_cache
    ):
        """When LLM succeeds, entry gets reclassified."""
        mock_fetch.return_value = "Some valid content"
        mock_llm.return_value = {
            "id": "test-id",
            "category": "core",
            "reason": "Directly about coding",
        }
        entry = _make_entry("mcp", source_url="https://github.com/owner/repo")
        entry["evaluation"] = {"decision": "review", "final_score": 40}

        with patch("deep_reviewer.compute_final_score", return_value=80), \
             patch("deep_reviewer.judge_decision", return_value="accept"):
            deep_reviewer.deep_review_entries([entry])

        self.assertEqual(entry["evaluation"]["deep_review_category"], "core")
        self.assertEqual(entry["evaluation"]["coding_relevance"], 5)
        self.assertEqual(entry["evaluation"]["decision"], "accept")


# ===========================================================================
# 5. deep_review_entries integration (mocked fetch + LLM)
# ===========================================================================

class DeepReviewEntriesTests(unittest.TestCase):

    @patch("deep_reviewer._save_cache")
    @patch("deep_reviewer._load_cache", return_value={})
    @patch("deep_reviewer._call_llm_reclassify")
    @patch("deep_reviewer.fetch_content")
    def test_empty_content_rejects_entry(
        self, mock_fetch, mock_llm, mock_load_cache, mock_save_cache
    ):
        """Empty content (404 / empty file) should reject with 'unrelated'."""
        mock_fetch.return_value = ""
        entry = _make_entry("mcp", source_url="https://github.com/owner/repo")
        entry["evaluation"] = {"decision": "review", "final_score": 40}

        with patch("deep_reviewer.compute_final_score", return_value=10), \
             patch("deep_reviewer.judge_decision", return_value="reject"):
            deep_reviewer.deep_review_entries([entry])

        self.assertEqual(entry["evaluation"]["deep_review_category"], "unrelated")
        self.assertEqual(entry["evaluation"]["coding_relevance"], 1)
        # LLM should NOT have been called for empty content
        mock_llm.assert_not_called()

    @patch("deep_reviewer._save_cache")
    @patch("deep_reviewer._load_cache", return_value={})
    @patch("deep_reviewer.fetch_content")
    def test_fetch_none_keeps_review(
        self, mock_fetch, mock_load_cache, mock_save_cache
    ):
        """Network error (fetch returns None) keeps decision as review."""
        mock_fetch.return_value = None
        entry = _make_entry("mcp", source_url="https://github.com/owner/repo")
        entry["evaluation"] = {"decision": "review", "final_score": 40}

        deep_reviewer.deep_review_entries([entry])

        self.assertEqual(entry["evaluation"]["decision"], "review")

    def test_non_review_entries_skipped(self):
        """Only entries with decision=='review' are processed."""
        entry = _make_entry("mcp", source_url="https://github.com/owner/repo")
        entry["evaluation"] = {"decision": "accept", "final_score": 80}

        # Should not attempt any fetch
        with patch("deep_reviewer.fetch_content") as mock_fetch:
            deep_reviewer.deep_review_entries([entry])
            mock_fetch.assert_not_called()

    def test_prompt_entries_skipped(self):
        """Prompt entries are filtered out even if decision=='review'."""
        entry = _make_entry("prompt", source_url="https://github.com/owner/repo")
        entry["evaluation"] = {"decision": "review", "final_score": 40}

        with patch("deep_reviewer.fetch_content") as mock_fetch:
            deep_reviewer.deep_review_entries([entry])
            mock_fetch.assert_not_called()

    @patch("deep_reviewer._save_cache")
    @patch("deep_reviewer._load_cache")
    @patch("deep_reviewer._call_llm_reclassify")
    @patch("deep_reviewer.fetch_content")
    def test_cache_hit_skips_llm(
        self, mock_fetch, mock_llm, mock_load_cache, mock_save_cache
    ):
        """When cache is valid, LLM should not be called."""
        content = "cached content"
        cache_data = {
            "mcp:test-id": {
                "category": "related",
                "reason": "cached reason",
                "content_hash": _sha256(content),
                "reviewed_at": datetime.now().isoformat(),
            }
        }
        mock_load_cache.return_value = cache_data
        mock_fetch.return_value = content

        entry = _make_entry("mcp", source_url="https://github.com/owner/repo")
        entry["evaluation"] = {"decision": "review", "final_score": 40}

        with patch("deep_reviewer.compute_final_score", return_value=60), \
             patch("deep_reviewer.judge_decision", return_value="accept"):
            deep_reviewer.deep_review_entries([entry])

        mock_llm.assert_not_called()
        self.assertEqual(entry["evaluation"]["deep_review_category"], "related")
        self.assertEqual(entry["evaluation"]["coding_relevance"], 3)

    @patch("deep_reviewer._save_cache")
    @patch("deep_reviewer._load_cache")
    @patch("deep_reviewer._call_llm_reclassify")
    @patch("deep_reviewer.fetch_content")
    def test_cache_expired_calls_llm(
        self, mock_fetch, mock_llm, mock_load_cache, mock_save_cache
    ):
        """When cache is expired (>30 days), LLM should be called."""
        content = "some content"
        old_date = (datetime.now() - timedelta(days=31)).isoformat()
        cache_data = {
            "mcp:test-id": {
                "category": "related",
                "reason": "old reason",
                "content_hash": _sha256(content),
                "reviewed_at": old_date,
            }
        }
        mock_load_cache.return_value = cache_data
        mock_fetch.return_value = content
        mock_llm.return_value = {
            "id": "test-id",
            "category": "core",
            "reason": "fresh eval",
        }

        entry = _make_entry("mcp", source_url="https://github.com/owner/repo")
        entry["evaluation"] = {"decision": "review", "final_score": 40}

        with patch("deep_reviewer.compute_final_score", return_value=85), \
             patch("deep_reviewer.judge_decision", return_value="accept"):
            deep_reviewer.deep_review_entries([entry])

        mock_llm.assert_called_once()
        self.assertEqual(entry["evaluation"]["deep_review_category"], "core")

    @patch("deep_reviewer._save_cache")
    @patch("deep_reviewer._load_cache")
    @patch("deep_reviewer._call_llm_reclassify")
    @patch("deep_reviewer.fetch_content")
    def test_cache_hash_mismatch_calls_llm(
        self, mock_fetch, mock_llm, mock_load_cache, mock_save_cache
    ):
        """When content hash changed, LLM should be called even if not expired."""
        cache_data = {
            "mcp:test-id": {
                "category": "related",
                "reason": "stale reason",
                "content_hash": _sha256("old content"),
                "reviewed_at": datetime.now().isoformat(),
            }
        }
        mock_load_cache.return_value = cache_data
        mock_fetch.return_value = "new content"
        mock_llm.return_value = {
            "id": "test-id",
            "category": "unrelated",
            "reason": "content changed",
        }

        entry = _make_entry("mcp", source_url="https://github.com/owner/repo")
        entry["evaluation"] = {"decision": "review", "final_score": 40}

        with patch("deep_reviewer.compute_final_score", return_value=20), \
             patch("deep_reviewer.judge_decision", return_value="reject"):
            deep_reviewer.deep_review_entries([entry])

        mock_llm.assert_called_once()
        self.assertEqual(entry["evaluation"]["deep_review_category"], "unrelated")


# ===========================================================================
# 6. _apply_classification unit tests
# ===========================================================================

class ApplyClassificationTests(unittest.TestCase):

    def test_core_sets_relevance_5(self):
        entry = _make_entry("mcp")
        entry["evaluation"] = {}
        with patch("deep_reviewer.compute_final_score", return_value=90), \
             patch("deep_reviewer.judge_decision", return_value="accept"):
            deep_reviewer._apply_classification(entry, "core", "test reason")
        self.assertEqual(entry["evaluation"]["coding_relevance"], 5)
        self.assertEqual(entry["evaluation"]["deep_review_category"], "core")
        self.assertEqual(entry["evaluation"]["deep_review_reason"], "test reason")

    def test_related_sets_relevance_3(self):
        entry = _make_entry("mcp")
        entry["evaluation"] = {}
        with patch("deep_reviewer.compute_final_score", return_value=60), \
             patch("deep_reviewer.judge_decision", return_value="accept"):
            deep_reviewer._apply_classification(entry, "related", "dev tool")
        self.assertEqual(entry["evaluation"]["coding_relevance"], 3)

    def test_unrelated_sets_relevance_1(self):
        entry = _make_entry("mcp")
        entry["evaluation"] = {}
        with patch("deep_reviewer.compute_final_score", return_value=20), \
             patch("deep_reviewer.judge_decision", return_value="reject"):
            deep_reviewer._apply_classification(entry, "unrelated", "not dev")
        self.assertEqual(entry["evaluation"]["coding_relevance"], 1)

    def test_creates_evaluation_if_missing(self):
        entry = _make_entry("mcp")
        # No evaluation key at all
        with patch("deep_reviewer.compute_final_score", return_value=50), \
             patch("deep_reviewer.judge_decision", return_value="review"):
            deep_reviewer._apply_classification(entry, "related", "reason")
        self.assertIn("evaluation", entry)
        self.assertEqual(entry["evaluation"]["coding_relevance"], 3)


# ===========================================================================
# 7. _parse_github_url edge cases
# ===========================================================================

class ParseGithubUrlTests(unittest.TestCase):

    def test_basic_url(self):
        result = deep_reviewer._parse_github_url("https://github.com/owner/repo")
        self.assertEqual(result, ("owner/repo", ""))

    def test_url_with_tree_path(self):
        result = deep_reviewer._parse_github_url(
            "https://github.com/owner/repo/tree/main/path/to/dir"
        )
        self.assertEqual(result, ("owner/repo", "path/to/dir"))

    def test_url_with_git_suffix(self):
        result = deep_reviewer._parse_github_url("https://github.com/owner/repo.git")
        self.assertEqual(result, ("owner/repo", ""))

    def test_non_github_url(self):
        result = deep_reviewer._parse_github_url("https://gitlab.com/owner/repo")
        self.assertIsNone(result)

    def test_http_url(self):
        result = deep_reviewer._parse_github_url("http://github.com/owner/repo")
        self.assertEqual(result, ("owner/repo", ""))

    def test_invalid_url(self):
        result = deep_reviewer._parse_github_url("not a url")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
