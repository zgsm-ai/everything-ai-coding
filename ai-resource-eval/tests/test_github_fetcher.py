"""Tests for ai_resource_eval.fetcher.github — GitHubFetcher URL parsing."""

from __future__ import annotations

import pytest

from ai_resource_eval.fetcher.github import GitHubFetcher


# ---------------------------------------------------------------------------
# _extract_owner_repo
# ---------------------------------------------------------------------------


class TestExtractOwnerRepo:
    """Verify URL parsing extracts owner, repo, ref, and subpath correctly."""

    def test_plain_repo_url(self) -> None:
        result = GitHubFetcher._extract_owner_repo(
            "https://github.com/owner/repo"
        )
        assert result == ("owner", "repo", "HEAD", "")

    def test_repo_with_trailing_slash(self) -> None:
        result = GitHubFetcher._extract_owner_repo(
            "https://github.com/owner/repo/"
        )
        # Regex anchors at the repo segment; trailing slash is ignored.
        assert result is not None
        owner, repo, ref, subpath = result
        assert owner == "owner"
        assert repo == "repo"

    def test_tree_url_with_ref_and_subpath(self) -> None:
        result = GitHubFetcher._extract_owner_repo(
            "https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem"
        )
        assert result == ("modelcontextprotocol", "servers", "main", "src/filesystem")

    def test_tree_url_with_deep_subpath(self) -> None:
        result = GitHubFetcher._extract_owner_repo(
            "https://github.com/owner/repo/tree/develop/packages/core/src"
        )
        assert result == ("owner", "repo", "develop", "packages/core/src")

    def test_blob_url(self) -> None:
        result = GitHubFetcher._extract_owner_repo(
            "https://github.com/owner/repo/blob/main/README.md"
        )
        assert result == ("owner", "repo", "main", "README.md")

    def test_tree_url_ref_only_no_subpath(self) -> None:
        result = GitHubFetcher._extract_owner_repo(
            "https://github.com/owner/repo/tree/v2.0"
        )
        assert result == ("owner", "repo", "v2.0", "")

    def test_dot_git_suffix_stripped(self) -> None:
        result = GitHubFetcher._extract_owner_repo(
            "https://github.com/owner/repo.git"
        )
        assert result is not None
        assert result[1] == "repo"

    def test_non_github_url_returns_none(self) -> None:
        result = GitHubFetcher._extract_owner_repo(
            "https://gitlab.com/owner/repo"
        )
        assert result is None

    def test_trailing_slash_on_subpath_stripped(self) -> None:
        result = GitHubFetcher._extract_owner_repo(
            "https://github.com/owner/repo/tree/main/src/filesystem/"
        )
        assert result is not None
        assert result[3] == "src/filesystem"


# ---------------------------------------------------------------------------
# fetch — URL construction (mocked HTTP)
# ---------------------------------------------------------------------------


class TestFetchURLConstruction:
    """Verify that fetch() builds the correct raw.githubusercontent.com URLs."""

    def test_plain_repo_url_uses_head(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A bare repo URL should request HEAD/<content_path>."""
        requested_urls: list[str] = []

        class FakeResponse:
            status_code = 200
            text = "# Hello"

        class FakeClient:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

            def get(self, url):
                requested_urls.append(url)
                return FakeResponse()

        import ai_resource_eval.fetcher.github as mod

        monkeypatch.setattr(mod.httpx, "Client", lambda **kw: FakeClient())

        fetcher = GitHubFetcher()
        fetcher.fetch("https://github.com/owner/repo")

        assert requested_urls == [
            "https://raw.githubusercontent.com/owner/repo/HEAD/README.md"
        ]

    def test_tree_url_includes_ref_and_subpath(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A tree URL with ref/subpath should embed them in the raw URL."""
        requested_urls: list[str] = []

        class FakeResponse:
            status_code = 200
            text = "# Filesystem MCP"

        class FakeClient:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

            def get(self, url):
                requested_urls.append(url)
                return FakeResponse()

        import ai_resource_eval.fetcher.github as mod

        monkeypatch.setattr(mod.httpx, "Client", lambda **kw: FakeClient())

        fetcher = GitHubFetcher()
        fetcher.fetch(
            "https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem"
        )

        assert requested_urls == [
            "https://raw.githubusercontent.com/modelcontextprotocol/servers/main/src/filesystem/README.md"
        ]

    def test_custom_content_paths_with_subpath(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Multiple content_paths should each be appended after the subpath prefix."""
        requested_urls: list[str] = []

        class FakeResponse:
            status_code = 404
            text = ""

        class FakeClient:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

            def get(self, url):
                requested_urls.append(url)
                return FakeResponse()

        import ai_resource_eval.fetcher.github as mod

        monkeypatch.setattr(mod.httpx, "Client", lambda **kw: FakeClient())

        fetcher = GitHubFetcher(content_paths=["README.md", "SKILL.md"])
        result = fetcher.fetch(
            "https://github.com/owner/repo/tree/develop/packages/core"
        )

        assert result is None
        assert requested_urls == [
            "https://raw.githubusercontent.com/owner/repo/develop/packages/core/README.md",
            "https://raw.githubusercontent.com/owner/repo/develop/packages/core/SKILL.md",
        ]
