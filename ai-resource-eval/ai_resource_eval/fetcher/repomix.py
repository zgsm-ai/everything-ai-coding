"""Repomix fetcher — pack a full repository via ``npx repomix``.

Uses ``npx repomix --remote {owner}/{repo} --style markdown --compress``
to produce a single compressed markdown file containing the full repo content.
Requires Node.js / npx to be available on the system.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path

_REPOMIX_TIMEOUT = 60  # seconds


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class RepomixUnavailableError(RuntimeError):
    """Raised when Repomix (npx) is not available on the system."""


# ---------------------------------------------------------------------------
# RepomixFetcher
# ---------------------------------------------------------------------------


class RepomixFetcher:
    """Fetch full repository content via Repomix.

    Runs ``npx repomix --remote {owner}/{repo} --style markdown --compress``
    and returns the packed content alongside its SHA-256 hash.
    """

    @staticmethod
    def is_available() -> bool:
        """Check whether ``npx`` is available on PATH."""
        return shutil.which("npx") is not None

    def fetch(self, repo: str) -> tuple[str, str] | None:
        """Run Repomix for the given *repo* (``"owner/repo"`` format).

        Parameters
        ----------
        repo:
            GitHub repository in ``"owner/repo"`` format.

        Returns
        -------
        tuple[str, str] | None
            ``(content, content_hash)`` on success, or ``None`` if the command
            fails or times out.

        Raises
        ------
        RepomixUnavailableError
            If ``npx`` is not available on the system.
        """
        if not self.is_available():
            raise RepomixUnavailableError(
                "npx is not available on PATH — install Node.js to use Repomix"
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "repomix-output.md"

            cmd = [
                "npx",
                "repomix",
                "--remote",
                repo,
                "--style",
                "markdown",
                "--compress",
                "--output",
                str(output_path),
            ]

            try:
                subprocess.run(
                    cmd,
                    timeout=_REPOMIX_TIMEOUT,
                    capture_output=True,
                    check=True,
                )
            except subprocess.TimeoutExpired:
                return None
            except subprocess.CalledProcessError:
                return None

            if not output_path.exists():
                return None

            content = output_path.read_text(encoding="utf-8")
            if not content:
                return None

            content_hash = hashlib.sha256(content.encode()).hexdigest()
            return content, content_hash
