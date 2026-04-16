"""Tests for ai_resource_eval.scoring.star_router — StarRouter."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_resource_eval.api.types import EvalItem, StarRoutingConfig
from ai_resource_eval.scoring.star_router import StarRouter

FIXTURES = Path(__file__).parent / "fixtures"

# Zero-weight sources matching the task YAML configuration.
ZERO_WEIGHT_SOURCES = [
    "antigravity-skills",
    "ai-agent-skills",
    "davila7/*",
    "vasilyu-skills",
    "anthropics-skills",
    "anthropics/claude-code",
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def catalog() -> list[EvalItem]:
    """Load the 80-entry catalog_sample.json fixture."""
    raw = json.loads((FIXTURES / "catalog_sample.json").read_text())
    return [EvalItem(**entry) for entry in raw]


@pytest.fixture()
def config() -> StarRoutingConfig:
    """Default StarRoutingConfig with zero_weight_sources and threshold=5."""
    return StarRoutingConfig(
        zero_weight_sources=ZERO_WEIGHT_SOURCES,
        monorepo_threshold=5,
    )


@pytest.fixture()
def router(config: StarRoutingConfig) -> StarRouter:
    """Return a StarRouter with the standard task configuration."""
    return StarRouter(config)


def _make_item(**overrides) -> EvalItem:
    """Create a minimal EvalItem with sensible defaults, overridable."""
    defaults = {
        "id": "test-item",
        "name": "test/name",
        "stars": 100,
        "source": None,
        "source_url": None,
    }
    defaults.update(overrides)
    return EvalItem(**defaults)


# ===================================================================
# extract_repo — static method
# ===================================================================


class TestExtractRepo:
    """Tests for StarRouter.extract_repo()."""

    def test_standard_github_url(self):
        url = "https://github.com/owner/repo"
        assert StarRouter.extract_repo(url) == "owner/repo"

    def test_github_url_with_trailing_path(self):
        url = "https://github.com/owner/repo/tree/main/sub/dir"
        assert StarRouter.extract_repo(url) == "owner/repo"

    def test_github_url_with_dot_git(self):
        url = "https://github.com/owner/repo.git"
        assert StarRouter.extract_repo(url) == "owner/repo"

    def test_non_github_url_returns_none(self):
        url = "https://gitlab.com/owner/repo"
        assert StarRouter.extract_repo(url) is None

    def test_none_returns_none(self):
        assert StarRouter.extract_repo(None) is None

    def test_arbitrary_url_returns_none(self):
        url = "https://example.com/some/path"
        assert StarRouter.extract_repo(url) is None

    def test_npm_url_returns_none(self):
        url = "https://www.npmjs.com/package/some-pkg"
        assert StarRouter.extract_repo(url) is None


# ===================================================================
# Catalog-based tests — source pattern matching
# ===================================================================


class TestSourcePatternMatching:
    """Test zero-weight detection using real catalog entries."""

    def test_antigravity_skills_entries_zero_weight(self, router, catalog):
        """All entries with source='antigravity-skills' get star_weight=0.0."""
        ag_entries = [e for e in catalog if e.source == "antigravity-skills"]
        assert len(ag_entries) > 0, "Fixture must contain antigravity-skills entries"

        for entry in ag_entries:
            weight = router.compute_star_weight(entry, catalog)
            assert weight == 0.0, (
                f"Entry {entry.id!r} (source={entry.source!r}) "
                f"should have star_weight=0.0"
            )

    def test_anthropics_claude_code_entries_zero_weight(self, router, catalog):
        """All entries with source='anthropics/claude-code' get star_weight=0.0."""
        ac_entries = [e for e in catalog if e.source == "anthropics/claude-code"]
        assert len(ac_entries) > 0, "Fixture must contain anthropics/claude-code entries"

        for entry in ac_entries:
            weight = router.compute_star_weight(entry, catalog)
            assert weight == 0.0, (
                f"Entry {entry.id!r} (source={entry.source!r}) "
                f"should have star_weight=0.0"
            )

    def test_davila7_glob_match_zero_weight(self, router, catalog):
        """Entries with source matching 'davila7/*' glob get star_weight=0.0."""
        davila_entries = [
            e for e in catalog
            if e.source is not None and e.source.startswith("davila7/")
        ]
        assert len(davila_entries) > 0, "Fixture must contain davila7/* entries"

        for entry in davila_entries:
            weight = router.compute_star_weight(entry, catalog)
            assert weight == 0.0, (
                f"Entry {entry.id!r} (source={entry.source!r}) "
                f"should have star_weight=0.0"
            )

    def test_mcp_so_standalone_entries_weight_one(self, router, catalog):
        """Entries from mcp.so with standalone repos get star_weight=1.0."""
        mcp_entries = [
            e for e in catalog
            if e.source == "mcp.so" and e.stars is not None and e.stars > 0
        ]
        assert len(mcp_entries) > 0, "Fixture must contain mcp.so entries with stars"

        for entry in mcp_entries:
            weight = router.compute_star_weight(entry, catalog)
            assert weight == 1.0, (
                f"Entry {entry.id!r} (source={entry.source!r}) "
                f"should have star_weight=1.0"
            )


# ===================================================================
# Monorepo dynamic detection
# ===================================================================


class TestMonorepoDetection:
    """Test dynamic monorepo detection (>= threshold entries sharing repo)."""

    def test_monorepo_entries_detected_in_catalog(self, router, catalog):
        """Entries from a repo appearing >= 5 times get star_weight=0.0.

        antigravity-awesome-skills has 8 entries in the fixture, all sharing
        the same GitHub repo. Even without the source pattern match, the
        monorepo detection would catch them.
        """
        # Use a router that does NOT have source pattern matching,
        # to isolate monorepo detection.
        clean_config = StarRoutingConfig(
            zero_weight_sources=[],
            monorepo_threshold=5,
        )
        clean_router = StarRouter(clean_config)

        # antigravity entries share sickn33/antigravity-awesome-skills (8 entries)
        ag_entries = [
            e for e in catalog
            if e.source_url is not None
            and "antigravity-awesome-skills" in e.source_url
            and e.stars is not None
            and e.stars > 0
        ]
        assert len(ag_entries) >= 5, "Fixture must have >= 5 antigravity repo entries"

        for entry in ag_entries:
            weight = clean_router.compute_star_weight(entry, catalog)
            assert weight == 0.0, (
                f"Entry {entry.id!r} from monorepo should be detected as 0.0"
            )

    def test_anthropics_claude_code_monorepo_at_threshold(self, router, catalog):
        """anthropics/claude-code has exactly 5 entries (== threshold) -> 0.0."""
        clean_config = StarRoutingConfig(
            zero_weight_sources=[],
            monorepo_threshold=5,
        )
        clean_router = StarRouter(clean_config)

        ac_entries = [
            e for e in catalog
            if e.source_url is not None
            and "github.com/anthropics/claude-code" in e.source_url
            and e.stars is not None
            and e.stars > 0
        ]
        assert len(ac_entries) == 5, (
            f"Expected 5 anthropics/claude-code entries, got {len(ac_entries)}"
        )

        for entry in ac_entries:
            weight = clean_router.compute_star_weight(entry, catalog)
            assert weight == 0.0, (
                f"Entry {entry.id!r} at threshold should be detected as 0.0"
            )

    def test_synthetic_monorepo_detection(self):
        """Synthetic test: 5 entries sharing a repo triggers monorepo detection."""
        config = StarRoutingConfig(
            zero_weight_sources=[],
            monorepo_threshold=5,
        )
        router = StarRouter(config)

        shared_entries = [
            _make_item(
                id=f"mono-{i}",
                stars=500,
                source_url=f"https://github.com/org/monorepo/tree/main/pkg-{i}",
            )
            for i in range(5)
        ]
        standalone = _make_item(
            id="standalone",
            stars=200,
            source_url="https://github.com/other/standalone-repo",
        )
        all_entries = shared_entries + [standalone]

        for entry in shared_entries:
            assert router.compute_star_weight(entry, all_entries) == 0.0

        assert router.compute_star_weight(standalone, all_entries) == 1.0

    def test_below_threshold_not_monorepo(self):
        """4 entries from the same repo (below threshold=5) are NOT monorepo."""
        config = StarRoutingConfig(
            zero_weight_sources=[],
            monorepo_threshold=5,
        )
        router = StarRouter(config)

        entries = [
            _make_item(
                id=f"pkg-{i}",
                stars=100,
                source_url=f"https://github.com/org/repo/tree/main/pkg-{i}",
            )
            for i in range(4)
        ]

        for entry in entries:
            assert router.compute_star_weight(entry, entries) == 1.0


# ===================================================================
# Standalone repo (not in zero-weight list, below threshold)
# ===================================================================


class TestStandaloneRepo:
    """Standalone repos (not in zero-weight, below monorepo threshold) -> 1.0."""

    def test_standalone_with_stars(self, router):
        entry = _make_item(
            id="standalone",
            stars=42,
            source="some-other-source",
            source_url="https://github.com/user/standalone-tool",
        )
        all_entries = [entry]
        assert router.compute_star_weight(entry, all_entries) == 1.0

    def test_standalone_no_source(self, router):
        """An entry with source=None and valid stars is standalone -> 1.0."""
        entry = _make_item(
            id="no-source",
            stars=10,
            source=None,
            source_url="https://github.com/user/repo",
        )
        all_entries = [entry]
        assert router.compute_star_weight(entry, all_entries) == 1.0


# ===================================================================
# Edge cases: stars=None, stars=0
# ===================================================================


class TestEdgeCaseStars:
    """Entries with no stars or zero stars always get 0.0."""

    def test_stars_none(self, router):
        entry = _make_item(id="no-stars", stars=None)
        assert router.compute_star_weight(entry, [entry]) == 0.0

    def test_stars_zero(self, router):
        entry = _make_item(id="zero-stars", stars=0)
        assert router.compute_star_weight(entry, [entry]) == 0.0

    def test_stars_none_even_if_source_is_standalone(self, router):
        """stars=None takes precedence over being a standalone repo."""
        entry = _make_item(
            id="null-stars-standalone",
            stars=None,
            source="mcp.so",
            source_url="https://github.com/user/standalone",
        )
        assert router.compute_star_weight(entry, [entry]) == 0.0

    def test_stars_zero_even_if_source_is_standalone(self, router):
        """stars=0 takes precedence over being a standalone repo."""
        entry = _make_item(
            id="zero-stars-standalone",
            stars=0,
            source="mcp.so",
            source_url="https://github.com/user/standalone",
        )
        assert router.compute_star_weight(entry, [entry]) == 0.0


# ===================================================================
# Decision order / priority
# ===================================================================


class TestDecisionPriority:
    """Verify the documented decision order is respected."""

    def test_zero_stars_checked_before_source(self):
        """Rule 1 (stars=None/0) fires before rule 2 (source pattern)."""
        config = StarRoutingConfig(
            zero_weight_sources=["bad-source"],
            monorepo_threshold=5,
        )
        router = StarRouter(config)

        # Entry matches both rule 1 (stars=None) and rule 2 (source match).
        entry = _make_item(id="both", stars=None, source="bad-source")
        # Should still return 0.0 — but the point is it does not crash.
        assert router.compute_star_weight(entry, [entry]) == 0.0

    def test_source_pattern_checked_before_monorepo(self):
        """Rule 2 (source pattern) fires before rule 3 (monorepo)."""
        config = StarRoutingConfig(
            zero_weight_sources=["my-source"],
            monorepo_threshold=5,
        )
        router = StarRouter(config)

        entries = [
            _make_item(
                id=f"e-{i}",
                stars=1000,
                source="my-source",
                source_url=f"https://github.com/org/repo/tree/main/pkg-{i}",
            )
            for i in range(6)
        ]

        # All should be 0.0 via source match (rule 2).
        for entry in entries:
            assert router.compute_star_weight(entry, entries) == 0.0

    def test_non_github_url_still_standalone(self, router):
        """An entry with a non-GitHub URL (extract_repo -> None) is standalone."""
        entry = _make_item(
            id="gitlab",
            stars=50,
            source="some-other-source",
            source_url="https://gitlab.com/user/repo",
        )
        assert router.compute_star_weight(entry, [entry]) == 1.0

    def test_no_source_url_standalone(self, router):
        """An entry with source_url=None and valid stars is standalone -> 1.0."""
        entry = _make_item(
            id="no-url",
            stars=50,
            source="some-other-source",
            source_url=None,
        )
        assert router.compute_star_weight(entry, [entry]) == 1.0


# ===================================================================
# Cache behaviour (internal implementation detail)
# ===================================================================


class TestRepoCountsCache:
    """Verify that repo counts are cached per all_entries list identity."""

    def test_same_list_object_cached(self, router):
        entries = [
            _make_item(
                id="e1",
                stars=10,
                source_url="https://github.com/a/b",
            ),
        ]
        # Call twice with the same list object.
        router.compute_star_weight(entries[0], entries)
        router.compute_star_weight(entries[0], entries)

        # Internal cache should be populated.
        assert router._repo_counts_cache is not None
        assert router._repo_counts_cache[0] == id(entries)

    def test_different_list_object_recomputes(self, router):
        list1 = [_make_item(id="e1", stars=10, source_url="https://github.com/a/b")]
        list2 = [_make_item(id="e2", stars=20, source_url="https://github.com/c/d")]

        router.compute_star_weight(list1[0], list1)
        cache_id_1 = router._repo_counts_cache[0]

        router.compute_star_weight(list2[0], list2)
        cache_id_2 = router._repo_counts_cache[0]

        assert cache_id_1 != cache_id_2
