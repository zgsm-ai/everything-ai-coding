"""Tests for get_repo_languages() in utils.py."""

import json
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError
from io import BytesIO

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from utils import get_repo_languages


class TestGetRepoLanguages:
    """Test suite for get_repo_languages."""

    def setup_method(self):
        """Clear the cache before each test."""
        from utils import _repo_languages_cache
        _repo_languages_cache.clear()

    @patch("utils.github_api")
    def test_successful_return(self, mock_api):
        """WHEN API returns languages dict THEN return list of language names."""
        mock_api.return_value = {"Python": 45000, "JavaScript": 12000}
        result = get_repo_languages("https://github.com/owner/repo")
        assert result == ["Python", "JavaScript"]
        mock_api.assert_called_once_with("repos/owner/repo/languages")

    @patch("utils.github_api")
    def test_repo_not_found_404(self, mock_api):
        """WHEN API returns None (404) THEN return []."""
        mock_api.return_value = None
        result = get_repo_languages("https://github.com/owner/nonexistent")
        assert result == []

    @patch("utils.github_api")
    def test_rate_limit(self, mock_api):
        """WHEN API returns None (rate limited) THEN return [] without crash."""
        mock_api.return_value = None
        result = get_repo_languages("https://github.com/owner/repo")
        assert result == []

    @patch("utils.github_api")
    def test_cache_dedup(self, mock_api):
        """WHEN called twice for same repo THEN API called only once."""
        mock_api.return_value = {"Python": 45000}
        r1 = get_repo_languages("https://github.com/Owner/Repo")
        r2 = get_repo_languages("https://github.com/owner/repo")
        assert r1 == ["Python"]
        assert r2 == ["Python"]
        assert mock_api.call_count == 1

    def test_non_github_url(self):
        """WHEN called with non-GitHub URL THEN return []."""
        result = get_repo_languages("https://gitlab.com/owner/repo")
        assert result == []

    @patch("utils.github_api")
    def test_empty_languages(self, mock_api):
        """WHEN repo has no languages THEN return []."""
        mock_api.return_value = {}
        result = get_repo_languages("https://github.com/owner/empty-repo")
        assert result == []

    @patch("utils.github_api")
    def test_url_with_trailing_slash(self, mock_api):
        """WHEN URL has trailing slash or .git THEN still works."""
        mock_api.return_value = {"Rust": 30000}
        result = get_repo_languages("https://github.com/owner/repo.git")
        assert result == ["Rust"]
