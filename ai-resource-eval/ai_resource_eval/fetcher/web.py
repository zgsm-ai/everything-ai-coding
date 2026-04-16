"""Generic web content fetcher — fetch and strip HTML from arbitrary URLs.

Performs an HTTP GET request, strips HTML tags to produce plaintext/markdown,
and returns ``(content, content_hash)`` or ``None`` on failure.
"""

from __future__ import annotations

import hashlib
import re
from html.parser import HTMLParser

import httpx

_TIMEOUT = 30.0  # seconds


# ---------------------------------------------------------------------------
# HTML → plaintext stripper
# ---------------------------------------------------------------------------


class _HTMLTextExtractor(HTMLParser):
    """Minimal HTML parser that extracts visible text content."""

    # Tags whose content should be suppressed entirely.
    _SKIP_TAGS = frozenset({"script", "style", "head", "meta", "link", "noscript"})

    def __init__(self) -> None:
        super().__init__()
        self._pieces: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._pieces.append(data)

    def get_text(self) -> str:
        raw = " ".join(self._pieces)
        # Collapse excessive whitespace while preserving paragraph breaks.
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()


def _strip_html(html: str) -> str:
    """Strip HTML tags and return visible text."""
    extractor = _HTMLTextExtractor()
    extractor.feed(html)
    return extractor.get_text()


# ---------------------------------------------------------------------------
# WebFetcher
# ---------------------------------------------------------------------------


class WebFetcher:
    """Fetch content from an arbitrary URL.

    Performs an HTTP GET, strips HTML tags to produce plaintext, and returns
    the content alongside its SHA-256 hash.
    """

    def fetch(self, url: str) -> tuple[str, str] | None:
        """Fetch content from *url*.

        Returns
        -------
        tuple[str, str] | None
            ``(content, content_hash)`` on success, or ``None`` on HTTP error
            or timeout.
        """
        try:
            with httpx.Client(timeout=_TIMEOUT, follow_redirects=True) as client:
                response = client.get(url)
                response.raise_for_status()
        except httpx.HTTPError:
            return None

        text = response.text
        content_type = response.headers.get("content-type", "")

        # Strip HTML if the response looks like HTML.
        if "html" in content_type.lower() or text.lstrip().startswith("<!"):
            text = _strip_html(text)

        if not text:
            return None

        content_hash = hashlib.sha256(text.encode()).hexdigest()
        return text, content_hash
