"""Interactive fallback fetcher — TTY-based menu for failed content fetches.

When a primary fetch (GitHub README) fails and the process is attached to a
TTY, this fetcher presents a questionary select menu offering alternative
strategies: provide a URL, paste content, use Repomix, skip, or skip all.

In non-TTY mode the fetcher returns ``None`` immediately (the caller should
fall back to its ``--on-fail`` strategy).
"""

from __future__ import annotations

import hashlib
import sys

from ai_resource_eval.api.types import EvalItem
from ai_resource_eval.fetcher.repomix import RepomixFetcher
from ai_resource_eval.fetcher.web import WebFetcher

# Menu option labels
_OPT_ALT_URL = "Provide alternative URL"
_OPT_PASTE = "Paste raw content"
_OPT_REPOMIX = "Fetch via Repomix"
_OPT_SKIP = "Skip this entry"
_OPT_SKIP_ALL = "Skip all remaining failures"


class InteractiveFetcher:
    """Interactive fallback fetcher with TTY detection and questionary menu.

    Parameters
    ----------
    web_fetcher:
        A ``WebFetcher`` instance for fetching alternative URLs.
    repomix_fetcher:
        A ``RepomixFetcher`` instance for full-repo packing.
    """

    def __init__(
        self,
        web_fetcher: WebFetcher,
        repomix_fetcher: RepomixFetcher,
    ) -> None:
        self._web_fetcher = web_fetcher
        self._repomix_fetcher = repomix_fetcher
        self._skip_all = False

    @property
    def skip_all(self) -> bool:
        """Whether the user has elected to skip all remaining failures."""
        return self._skip_all

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _content_hash(text: str) -> str:
        """Return the SHA-256 hex digest of *text*."""
        return hashlib.sha256(text.encode()).hexdigest()

    def _build_choices(self, entry: EvalItem) -> list[str]:
        """Build the menu choices, hiding Repomix if unavailable."""
        choices = [_OPT_ALT_URL, _OPT_PASTE]

        # Only show Repomix option if npx is available and entry has a GitHub URL.
        if RepomixFetcher.is_available() and entry.source_url:
            choices.append(_OPT_REPOMIX)

        choices.extend([_OPT_SKIP, _OPT_SKIP_ALL])
        return choices

    def _handle_alt_url(self) -> tuple[str, str] | None:
        """Prompt for a URL and fetch via WebFetcher."""
        import questionary

        url = questionary.text("Enter alternative URL:").ask()
        if not url:
            return None
        return self._web_fetcher.fetch(url)

    def _handle_paste(self) -> tuple[str, str] | None:
        """Accept multiline pasted content (until empty line or EOF)."""
        import questionary

        content = questionary.text(
            "Paste content (press Enter twice to finish):",
            multiline=True,
        ).ask()
        if not content or not content.strip():
            return None
        content = content.strip()
        return content, self._content_hash(content)

    def _handle_repomix(self, entry: EvalItem) -> tuple[str, str] | None:
        """Extract owner/repo and fetch via RepomixFetcher."""
        from ai_resource_eval.scoring.star_router import StarRouter

        repo = StarRouter.extract_repo(entry.source_url)
        if repo is None:
            return None
        return self._repomix_fetcher.fetch(repo)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch(self, entry: EvalItem) -> tuple[str, str] | None:
        """Interactively resolve a content fetch failure.

        Returns ``None`` immediately if:
        - ``skip_all`` has been set by a previous call
        - stdin is not a TTY

        Otherwise presents a questionary menu and returns
        ``(content, content_hash)`` or ``None``.

        Parameters
        ----------
        entry:
            The ``EvalItem`` whose content could not be fetched.

        Returns
        -------
        tuple[str, str] | None
            ``(content, content_hash)`` on success, or ``None`` if the user
            skips or if the chosen strategy fails.
        """
        if self._skip_all:
            return None

        if not sys.stdin.isatty():
            return None

        import questionary
        from rich.console import Console

        console = Console(stderr=True)
        label = entry.name or entry.id
        console.print(
            f"\n[yellow]Content fetch failed for:[/yellow] {label}",
        )
        if entry.source_url:
            console.print(f"  [dim]{entry.source_url}[/dim]")

        choices = self._build_choices(entry)
        answer = questionary.select(
            "How would you like to proceed?",
            choices=choices,
        ).ask()

        if answer is None or answer == _OPT_SKIP:
            return None

        if answer == _OPT_SKIP_ALL:
            self._skip_all = True
            return None

        if answer == _OPT_ALT_URL:
            return self._handle_alt_url()

        if answer == _OPT_PASTE:
            return self._handle_paste()

        if answer == _OPT_REPOMIX:
            return self._handle_repomix(entry)

        return None
