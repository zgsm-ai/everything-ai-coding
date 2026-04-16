"""Star-noise routing: detect and downweight shared-repo star inflation."""

from __future__ import annotations

import re
from collections import Counter
from fnmatch import fnmatch

from ai_resource_eval.api.types import EvalItem, StarRoutingConfig

# Matches "https://github.com/owner/repo" with optional trailing path.
_GITHUB_REPO_RE = re.compile(r"https://github\.com/([^/]+/[^/]+)")


class StarRouter:
    """Decides whether an entry's star count should carry weight.

    ``star_weight`` is binary: **1.0** (stars count) or **0.0** (stars ignored).

    Zero-weight is assigned when:
    * the entry has no stars (``None`` or ``0``);
    * its ``source`` matches any pattern in *zero_weight_sources* (glob via
      :func:`fnmatch.fnmatch`);
    * its GitHub repo appears in ≥ *monorepo_threshold* entries (dynamic
      monorepo detection).
    """

    def __init__(self, config: StarRoutingConfig) -> None:
        self._zero_weight_sources = config.zero_weight_sources
        self._monorepo_threshold = config.monorepo_threshold
        # Cached repo counts keyed by id(all_entries) to avoid recomputing.
        self._repo_counts_cache: tuple[int, Counter[str | None]] | None = None

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    @staticmethod
    def extract_repo(source_url: str | None) -> str | None:
        """Extract ``owner/repo`` from a GitHub URL.

        Returns ``None`` for non-GitHub URLs or when *source_url* is ``None``.

        Examples::

            >>> StarRouter.extract_repo("https://github.com/owner/repo/tree/main/sub")
            'owner/repo'
            >>> StarRouter.extract_repo("https://gitlab.com/owner/repo") is None
            True
        """
        if source_url is None:
            return None
        m = _GITHUB_REPO_RE.match(source_url)
        if m is None:
            return None
        repo = m.group(1)
        # Strip a trailing ".git" if present.
        if repo.endswith(".git"):
            repo = repo[: -len(".git")]
        return repo

    def compute_star_weight(
        self,
        entry: EvalItem,
        all_entries: list[EvalItem],
    ) -> float:
        """Return ``0.0`` or ``1.0`` for *entry* given the full batch.

        Decision order:
        1. ``stars`` is ``None`` or ``0`` → **0.0**
        2. ``source`` matches a *zero_weight_sources* pattern → **0.0**
        3. Entry's repo appears ≥ *monorepo_threshold* times → **0.0**
        4. Otherwise → **1.0**
        """
        # 1. Missing / zero stars ------------------------------------------------
        if entry.stars is None or entry.stars == 0:
            return 0.0

        # 2. Source-field pattern match ------------------------------------------
        if entry.source is not None:
            for pattern in self._zero_weight_sources:
                if fnmatch(entry.source, pattern):
                    return 0.0

        # 3. Dynamic monorepo detection ------------------------------------------
        repo = self.extract_repo(entry.source_url)
        if repo is not None:
            repo_counts = self._get_repo_counts(all_entries)
            if repo_counts.get(repo, 0) >= self._monorepo_threshold:
                return 0.0

        # 4. Standalone ----------------------------------------------------------
        return 1.0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_repo_counts(self, all_entries: list[EvalItem]) -> Counter[str | None]:
        """Return cached repo-occurrence counts for *all_entries*."""
        key = id(all_entries)
        if self._repo_counts_cache is None or self._repo_counts_cache[0] != key:
            counts: Counter[str | None] = Counter(
                self.extract_repo(e.source_url) for e in all_entries
            )
            self._repo_counts_cache = (key, counts)
        return self._repo_counts_cache[1]
