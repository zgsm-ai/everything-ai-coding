"""Tests for llm_search_enricher.py — LLM batch search term generation."""

import json
import os
import sys
import tempfile
from unittest.mock import patch
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import llm_search_enricher


class TestEnrichSearchTerms:
    """Test suite for enrich_search_terms()."""

    def setup_method(self):
        """Create a temp cache file for each test."""
        self.tmpdir = tempfile.mkdtemp()
        self.cache_path = os.path.join(self.tmpdir, ".llm_search_cache.json")
        llm_search_enricher.CACHE_PATH = self.cache_path

    def _make_entry(self, eid, name="Test Tool", desc="A test tool", tags=None):
        return {
            "id": eid,
            "name": name,
            "description": desc,
            "tags": tags or ["python", "cli"],
            "type": "mcp",
            "source_url": f"https://github.com/org/{eid}",
        }

    @patch.dict(os.environ, {"LLM_BASE_URL": "http://llm.test/v1", "LLM_API_KEY": "key123"})
    @patch("llm_search_enricher._call_llm_batch")
    def test_successful_enrichment(self, mock_llm):
        """WHEN entries provided → return dict mapping id to search term list."""
        entries = [self._make_entry(f"entry-{i}") for i in range(3)]
        mock_llm.return_value = {
            f"entry-{i}": ["search term", "搜索词", "alternative"] for i in range(3)
        }
        result = llm_search_enricher.enrich_search_terms(entries)
        assert len(result) == 3
        for terms in result.values():
            assert len(terms) == 3

    @patch.dict(os.environ, {}, clear=True)
    def test_no_env_vars_returns_empty(self):
        """WHEN LLM_BASE_URL or LLM_API_KEY not set → return {} without crash."""
        entries = [self._make_entry("entry-1")]
        os.environ.pop("LLM_BASE_URL", None)
        os.environ.pop("LLM_API_KEY", None)
        result = llm_search_enricher.enrich_search_terms(entries)
        assert result == {}

    @patch.dict(os.environ, {"LLM_BASE_URL": "http://llm.test/v1", "LLM_API_KEY": "key123"})
    @patch("llm_search_enricher._call_llm_batch")
    def test_cache_hit_skips_api(self, mock_llm):
        """WHEN entry id in cache with valid timestamp → use cached, no API call."""
        cache = {
            "entry-cached": {
                "terms": ["cached term", "缓存词"],
                "cached_at": datetime.now().isoformat(),
            }
        }
        with open(self.cache_path, "w") as f:
            json.dump(cache, f)

        entries = [self._make_entry("entry-cached")]
        result = llm_search_enricher.enrich_search_terms(entries)
        assert result == {"entry-cached": ["cached term", "缓存词"]}
        mock_llm.assert_not_called()

    @patch.dict(os.environ, {"LLM_BASE_URL": "http://llm.test/v1", "LLM_API_KEY": "key123"})
    @patch("llm_search_enricher._call_llm_batch")
    def test_cache_expired_triggers_api(self, mock_llm):
        """WHEN cache entry older than 30 days → re-generate via LLM."""
        expired_date = (datetime.now() - timedelta(days=31)).isoformat()
        cache = {
            "entry-old": {
                "terms": ["old term"],
                "cached_at": expired_date,
            }
        }
        with open(self.cache_path, "w") as f:
            json.dump(cache, f)

        entries = [self._make_entry("entry-old")]
        mock_llm.return_value = {"entry-old": ["new term", "新词"]}
        result = llm_search_enricher.enrich_search_terms(entries)
        assert result == {"entry-old": ["new term", "新词"]}
        mock_llm.assert_called_once()

    @patch.dict(os.environ, {"LLM_BASE_URL": "http://llm.test/v1", "LLM_API_KEY": "key123"})
    @patch("llm_search_enricher._call_llm_batch")
    def test_batch_failure_skips_gracefully(self, mock_llm):
        """WHEN LLM batch returns {} → those entries have no search_terms, no crash."""
        entries = [self._make_entry(f"entry-{i}") for i in range(3)]
        mock_llm.return_value = {}
        result = llm_search_enricher.enrich_search_terms(entries)
        assert result == {}

    @patch.dict(os.environ, {"LLM_BASE_URL": "http://llm.test/v1", "LLM_API_KEY": "key123"})
    @patch("llm_search_enricher._call_llm_batch")
    def test_dedup_preserves_order(self, mock_llm):
        """WHEN LLM returns duplicate terms → dedup while preserving order."""
        entries = [self._make_entry("entry-1")]
        mock_llm.return_value = {
            "entry-1": ["Deploy", " deploy ", "DEPLOY", "CI/CD", "ci/cd"]
        }
        result = llm_search_enricher.enrich_search_terms(entries)
        terms = result["entry-1"]
        assert terms == ["Deploy", "CI/CD"]

    @patch.dict(os.environ, {"LLM_BASE_URL": "http://llm.test/v1", "LLM_API_KEY": "key123"})
    @patch("llm_search_enricher._call_llm_batch")
    def test_cache_written_after_enrichment(self, mock_llm):
        """After enrichment, results are persisted to cache file."""
        entries = [self._make_entry("entry-new")]
        mock_llm.return_value = {"entry-new": ["term1", "term2"]}
        llm_search_enricher.enrich_search_terms(entries)
        with open(self.cache_path) as f:
            cache = json.load(f)
        assert "entry-new" in cache
        assert cache["entry-new"]["terms"] == ["term1", "term2"]

    @patch.dict(os.environ, {"LLM_BASE_URL": "http://llm.test/v1", "LLM_API_KEY": "key123"})
    @patch("llm_search_enricher._call_llm_batch")
    def test_mixed_cache_and_uncached(self, mock_llm):
        """WHEN some entries cached, some not → only uncached entries hit LLM."""
        cache = {
            "entry-cached": {
                "terms": ["cached"],
                "cached_at": datetime.now().isoformat(),
            }
        }
        with open(self.cache_path, "w") as f:
            json.dump(cache, f)

        entries = [
            self._make_entry("entry-cached"),
            self._make_entry("entry-new"),
        ]
        mock_llm.return_value = {"entry-new": ["new term"]}
        result = llm_search_enricher.enrich_search_terms(entries)
        assert result == {"entry-cached": ["cached"], "entry-new": ["new term"]}
        # LLM batch should only contain the uncached entry
        call_args = mock_llm.call_args[0][0]
        assert len(call_args) == 1
        assert call_args[0]["id"] == "entry-new"
