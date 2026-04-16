"""GitHub README fetcher — fetch raw content from GitHub repositories.

Derives ``raw.githubusercontent.com`` URLs from ``source_url`` and tries each
path in ``content_paths`` in order until one succeeds (HTTP 200).  Returns
``(content, content_hash)`` or ``None`` when all paths 404.
"""

from __future__ import annotations

import hashlib
import re

import httpx

# Matches "https://github.com/owner/repo" with optional /tree|blob/ref/subpath.
_GITHUB_REPO_RE = re.compile(
    r"https://github\.com/([^/]+)/([^/]+)"
    r"(?:/(?:tree|blob)/([^/]+)(?:/(.+))?)?"
)

_RAW_BASE = "https://raw.githubusercontent.com"

_DEFAULT_CONTENT_PATHS = ["README.md"]

_TIMEOUT = 30.0  # seconds


class GitHubFetcher:
    """Fetch README content from a GitHub repository.

    Parameters
    ----------
    content_paths:
        Ordered list of file paths to try within the repository root.
        Defaults to ``["README.md"]``.
    """

    def __init__(self, content_paths: list[str] | None = None) -> None:
        self._content_paths = content_paths or list(_DEFAULT_CONTENT_PATHS)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_owner_repo(
        source_url: str,
    ) -> tuple[str, str, str, str] | None:
        """Extract ``(owner, repo, ref, subpath)`` from a GitHub URL.

        Returns ``None`` for non-GitHub URLs.

        *ref* defaults to ``"HEAD"`` and *subpath* defaults to ``""`` when the
        URL does not contain ``/tree/<ref>/…`` or ``/blob/<ref>/…`` segments.
        """
        m = _GITHUB_REPO_RE.match(source_url)
        if m is None:
            return None
        owner = m.group(1)
        repo = m.group(2)
        # Strip trailing ".git" if present.
        if repo.endswith(".git"):
            repo = repo[: -len(".git")]
        ref = m.group(3) or "HEAD"
        subpath = (m.group(4) or "").rstrip("/")
        return owner, repo, ref, subpath

    @staticmethod
    def _content_hash(text: str) -> str:
        """Return the SHA-256 hex digest of *text*."""
        return hashlib.sha256(text.encode()).hexdigest()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch(self, source_url: str) -> tuple[str, str] | None:
        """Fetch content from a GitHub repository.

        Derives ``raw.githubusercontent.com`` URLs from *source_url* and tries
        each path in ``content_paths`` in order.

        Returns
        -------
        tuple[str, str] | None
            ``(content, content_hash)`` on success, or ``None`` when all paths
            return non-200 responses or the URL is not a GitHub URL.
        """
        parsed = self._extract_owner_repo(source_url)
        if parsed is None:
            return None

        owner, repo, ref, subpath = parsed

        # Strip fragment from subpath (e.g. "PROMPTS.md#slug" → "PROMPTS.md")
        fragment = self._extract_fragment(source_url)
        if fragment and "#" in (subpath or ""):
            subpath = subpath.split("#")[0]

        prefix = f"{_RAW_BASE}/{owner}/{repo}/{ref}"

        # Detect blob URLs pointing to a specific file (subpath ends with
        # a file extension like .md, .txt, .csv).  In this case fetch the
        # file directly instead of appending content_paths.
        is_file = bool(
            subpath and re.search(r"\.\w+$", subpath)
        )

        if is_file:
            # Direct file fetch — don't iterate content_paths
            raw_url = f"{prefix}/{subpath}"
            try:
                with httpx.Client(timeout=_TIMEOUT) as client:
                    response = client.get(raw_url)
                    if response.status_code == 200:
                        content = response.text
                        if fragment:
                            section = self._extract_section(content, fragment)
                            if section:
                                content = section
                        return content, self._content_hash(content)
            except httpx.HTTPError:
                pass
            return None

        if subpath:
            prefix = f"{prefix}/{subpath}"

        with httpx.Client(timeout=_TIMEOUT) as client:
            for path in self._content_paths:
                url = f"{prefix}/{path}"
                try:
                    response = client.get(url)
                except httpx.HTTPError:
                    continue

                if response.status_code == 200:
                    content = response.text
                    if fragment:
                        section = self._extract_section(content, fragment)
                        if section:
                            content = section
                    return content, self._content_hash(content)

        return None

    # ------------------------------------------------------------------
    # Section extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_fragment(url: str) -> str | None:
        """Extract the ``#fragment`` from a URL, or None."""
        idx = url.find("#")
        if idx < 0:
            return None
        return url[idx + 1 :]

    @staticmethod
    def _extract_section(text: str, slug: str) -> str | None:
        """Extract a Markdown section matching *slug* from *text*.

        Finds the ``## Title`` whose GitHub-style slug matches, then returns
        everything from that heading to the next ``##`` heading (exclusive).
        """
        for m in re.finditer(r"^(##\s+.+)$", text, re.MULTILINE):
            heading = m.group(1)
            # GitHub slug: lowercase, strip non-alnum except spaces/hyphens,
            # spaces → hyphens
            h_slug = re.sub(r"[^a-z0-9 -]", "", heading.lower())
            h_slug = re.sub(r"\s+", "-", h_slug).strip("-")
            h_slug = re.sub(r"-+", "-", h_slug)
            # Remove leading "##-" or "## " artifact
            if h_slug.startswith("--"):
                h_slug = h_slug.lstrip("-")

            if h_slug == slug:
                start = m.start()
                # Find next ## heading
                rest = text[m.end() :]
                nxt = re.search(r"^## ", rest, re.MULTILINE)
                end = m.end() + nxt.start() if nxt else len(text)
                return text[start:end].strip()

        return None
