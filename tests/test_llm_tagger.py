"""Tests for llm_tagger.py — LLM batch tagging for entries with insufficient tags."""

import json
import os
import sys
import tempfile
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import llm_tagger


class TestLlmTagEntries:
    """Test suite for llm_tag_entries()."""

    def setup_method(self):
        """Create a temp cache file for each test."""
        self.tmpdir = tempfile.mkdtemp()
        self.cache_path = os.path.join(self.tmpdir, ".llm_tag_cache.json")
        llm_tagger.CACHE_PATH = self.cache_path

    def _make_entry(self, eid, tags=None, name="Test Tool", desc="A tool"):
        return {
            "id": eid,
            "name": name,
            "description": desc,
            "tags": tags or [],
            "source_url": f"https://github.com/org/{eid}",
        }

    @patch.dict(os.environ, {"LLM_BASE_URL": "http://llm.test/v1", "LLM_API_KEY": "key123"})
    @patch("llm_tagger._call_llm_batch")
    def test_successful_batch_tagging(self, mock_llm):
        """WHEN 40 entries with empty tags → return dict mapping id to lowercase tag list."""
        entries = [self._make_entry(f"entry-{i}") for i in range(40)]
        mock_llm.return_value = {
            f"entry-{i}": ["MCP", "Python", "AI"] for i in range(40)
        }
        result = llm_tagger.llm_tag_entries(entries)
        assert len(result) == 40
        # Tags should be lowercased and stripped
        for tags in result.values():
            assert all(t == t.lower().strip() for t in tags)

    @patch.dict(os.environ, {}, clear=True)
    def test_api_unavailable_returns_empty(self):
        """WHEN LLM_BASE_URL or LLM_API_KEY not set → return {} without crash."""
        entries = [self._make_entry("entry-1")]
        # Remove env vars
        os.environ.pop("LLM_BASE_URL", None)
        os.environ.pop("LLM_API_KEY", None)
        result = llm_tagger.llm_tag_entries(entries)
        assert result == {}

    @patch.dict(os.environ, {"LLM_BASE_URL": "http://llm.test/v1", "LLM_API_KEY": "key123"})
    @patch("llm_tagger._call_llm_batch")
    def test_partial_results(self, mock_llm):
        """WHEN LLM returns tags for only 30 of 40 entries → 30 get tags, 10 unchanged."""
        entries = [self._make_entry(f"entry-{i}") for i in range(40)]
        partial = {f"entry-{i}": ["python"] for i in range(30)}
        mock_llm.return_value = partial
        result = llm_tagger.llm_tag_entries(entries)
        assert len(result) == 30

    @patch.dict(os.environ, {"LLM_BASE_URL": "http://llm.test/v1", "LLM_API_KEY": "key123"})
    @patch("llm_tagger._call_llm_batch")
    def test_cache_hit_skips_api(self, mock_llm):
        """WHEN entry id in cache with valid result → use cached, no API call."""
        # Pre-populate cache
        cache = {
            "entry-cached": {
                "tags": ["python", "cli"],
                "cached_at": datetime.now().isoformat(),
            }
        }
        with open(self.cache_path, "w") as f:
            json.dump(cache, f)

        entries = [self._make_entry("entry-cached")]
        result = llm_tagger.llm_tag_entries(entries)
        assert result == {"entry-cached": ["python", "cli"]}
        mock_llm.assert_not_called()

    @patch.dict(os.environ, {"LLM_BASE_URL": "http://llm.test/v1", "LLM_API_KEY": "key123"})
    @patch("llm_tagger._call_llm_batch")
    def test_skip_entries_with_enough_tags(self, mock_llm):
        """WHEN entry has >=2 tags → not sent to LLM."""
        entries = [
            self._make_entry("has-tags", tags=["python", "cli"]),
            self._make_entry("no-tags"),
        ]
        mock_llm.return_value = {"no-tags": ["ai", "mcp"]}
        result = llm_tagger.llm_tag_entries(entries)
        assert "has-tags" not in result
        assert result.get("no-tags") == ["ai", "mcp"]

    @patch.dict(os.environ, {"LLM_BASE_URL": "http://llm.test/v1", "LLM_API_KEY": "key123"})
    @patch("llm_tagger._call_llm_batch")
    def test_prompt_includes_high_freq_tags(self, mock_llm):
        """WHEN prompt is constructed THEN it includes high-frequency reference vocabulary."""
        entries = [self._make_entry("test-entry")]
        existing_tags = ["python"] * 50 + ["react"] * 40 + ["docker"] * 30
        mock_llm.return_value = {"test-entry": ["python"]}
        llm_tagger.llm_tag_entries(entries, existing_tag_freq=existing_tags)
        # Check the prompt passed to _call_llm_batch
        call_args = mock_llm.call_args
        # Second arg is the prompt reference vocab
        prompt_vocab = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("reference_vocab", [])
        assert "python" in prompt_vocab
        assert "react" in prompt_vocab

    @patch.dict(os.environ, {"LLM_BASE_URL": "http://llm.test/v1", "LLM_API_KEY": "key123"})
    @patch("llm_tagger._call_llm_batch")
    def test_output_lowercased_deduped(self, mock_llm):
        """WHEN LLM returns tags → .lower().strip() + dedup applied."""
        entries = [self._make_entry("entry-1")]
        mock_llm.return_value = {
            "entry-1": ["Python", " React ", "python", "DOCKER", "react"]
        }
        result = llm_tagger.llm_tag_entries(entries)
        tags = result["entry-1"]
        assert tags == ["python", "react", "docker"]

    @patch.dict(os.environ, {"LLM_BASE_URL": "http://llm.test/v1", "LLM_API_KEY": "key123"})
    @patch("llm_tagger._call_llm_batch")
    def test_cache_written_after_tagging(self, mock_llm):
        """After tagging, results are persisted to cache file."""
        entries = [self._make_entry("entry-new")]
        mock_llm.return_value = {"entry-new": ["ai", "mcp"]}
        llm_tagger.llm_tag_entries(entries)
        with open(self.cache_path) as f:
            cache = json.load(f)
        assert "entry-new" in cache
        assert cache["entry-new"]["tags"] == ["ai", "mcp"]
