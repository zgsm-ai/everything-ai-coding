"""Tests for ``scripts/sync_plugins_dev.py`` (Task 7.6).

The tests stub out the network layer by monkey-patching ``_http_get_json`` so
that no real requests hit ``claude-plugins.dev``. Pagination tests use a
stateful queue of canned responses; failure tests force the stub to raise.

Coverage matches Task 7.6 requirements:

  * Star-threshold filtering (< 5 stars dropped).
  * Pagination stop conditions (short page, max_pages cap).
  * Source-aware dedup against an existing on-disk index.
  * Failure isolation (exit 0 on errors, existing file untouched).
  * Empty-response handling (exit 0, file untouched).
  * ``_compute_manifest_completeness`` strata (1.0 / 0.7).
  * Entry shape — id / type / source / source_priority /
    bundle.skills_namespaces / install.method.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

# Make scripts/ importable.
sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "scripts"),
)

import sync_plugins_dev as spd  # noqa: E402


# 模块默认 MIN_STARS=5000（生产阈值，让 dev 收录稳定在 ~700 条精选）。
# 测试 fixture 用的小 stars（10/100/42 等）在生产阈值下会全部被过滤；
# autouse fixture 把阈值降到 5，让"语义过滤逻辑"测试维持原意。
@pytest.fixture(autouse=True)
def _relax_min_stars_for_tests(monkeypatch):
    monkeypatch.setattr(spd, "MIN_STARS", 5)
    # Stub out the marketplace manifest fetch — the sync's `_entry_from_plugin`
    # calls marketplace_verifier.verify_marketplace which would otherwise hit
    # raw.githubusercontent.com. Tests focus on the sync orchestration, not the
    # verifier's HTTP layer (covered by test_marketplace_verifier.py).
    monkeypatch.setattr(
        spd.marketplace_verifier,
        "verify_marketplace",
        lambda repo, plugin_name, cache: (None, False),
    )


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _make_plugin(
    name: str,
    *,
    namespace: str = "test-ns",
    stars: int = 10,
    description: str = "A test plugin",
    version: str = "1.0.0",
    author: str = "tester",
    git_url: str | None = None,
    skills: list[str] | None = None,
) -> dict:
    """Build one claude-plugins.dev API plugin dict."""
    return {
        "id": f"{namespace}::{name}",
        "name": name,
        "namespace": namespace,
        "description": description,
        "version": version,
        "author": author,
        "stars": stars,
        "gitUrl": git_url or f"https://github.com/{namespace}/{name}",
        "keywords": [],
        "category": "developer-tools",
        "skills": skills or [],
    }


def _api_response(plugins: list[dict], *, total: int | None = None,
                  limit: int = 100) -> dict:
    """Build a claude-plugins.dev API response envelope."""
    return {
        "plugins": plugins,
        "total": total if total is not None else len(plugins),
        "limit": limit,
        "offset": 0,
    }


def _install_paged_http(monkeypatch: pytest.MonkeyPatch,
                        responses: list[dict | Exception | None]) -> list[str]:
    """Install a stateful ``_http_get_json`` that pops one response per call.

    Returns a list that records every URL the script asked for (for
    assertions on call counts and pagination behavior).
    """
    pending = list(responses)
    seen_urls: list[str] = []

    def fake_get_json(url: str, timeout: int = 30):
        seen_urls.append(url)
        if not pending:
            # Default to a short empty page so the loop terminates if the
            # script asks for more pages than the test queued up. The
            # individual tests still assert on len(seen_urls) so a stray
            # extra call surfaces clearly.
            return _api_response([], limit=100)
        item = pending.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(spd, "_http_get_json", fake_get_json)
    # Disable on-disk cache writes so the test suite never touches
    # the real ``.plugins_dev_cache/`` directory.
    monkeypatch.setattr(spd, "_write_page_cache", lambda *a, **kw: None)
    return seen_urls


# ---------------------------------------------------------------------------
# Star-threshold filter
# ---------------------------------------------------------------------------


def test_filter_low_stars(monkeypatch, tmp_path):
    """Plugins with stars < 5 are dropped during pagination."""
    plugins = [
        _make_plugin("ten", stars=10),
        _make_plugin("four", stars=4),       # below threshold → dropped
        _make_plugin("hundred", stars=100),
    ]
    seen = _install_paged_http(
        monkeypatch,
        [_api_response(plugins, limit=100)],  # short page → loop ends
    )

    output_path = tmp_path / "plugins" / "index.json"
    rc = spd.main(["--output", str(output_path)])
    assert rc == 0
    assert len(seen) == 1  # only one page fetched

    with open(output_path, encoding="utf-8") as f:
        entries = json.load(f)
    names = sorted(e["name"] for e in entries)
    assert names == ["hundred", "ten"]
    # The filtered-out one truly does not appear.
    assert "four" not in names


# ---------------------------------------------------------------------------
# Pagination — stop on short page
# ---------------------------------------------------------------------------


def test_pagination_stops_on_short_page(monkeypatch, tmp_path):
    """Page 1 full (100), page 2 short (50) → loop stops; total=150."""
    page1 = [_make_plugin(f"p1-{i}", stars=10) for i in range(100)]
    page2 = [_make_plugin(f"p2-{i}", stars=10) for i in range(50)]
    seen = _install_paged_http(
        monkeypatch,
        [
            _api_response(page1, limit=100),
            _api_response(page2, limit=100),
            # If the script wrongly asks for page 3, the helper falls back
            # to an empty page so the test surface is the seen-urls count.
        ],
    )

    output_path = tmp_path / "plugins" / "index.json"
    rc = spd.main(["--output", str(output_path)])
    assert rc == 0
    assert len(seen) == 2, f"Expected exactly 2 page fetches, got {seen}"

    with open(output_path, encoding="utf-8") as f:
        entries = json.load(f)
    assert len(entries) == 150


# ---------------------------------------------------------------------------
# Pagination — stop on max_pages cap
# ---------------------------------------------------------------------------


def test_pagination_stops_on_max_pages(monkeypatch, tmp_path):
    """Infinite full pages + ``--limit-pages 3`` → exactly 3 fetches."""
    # Stateful generator: every call returns a fresh full page (100 plugins)
    # with unique names so dedup-by-id doesn't drop anything inside the loop.
    counter = {"page": 0}
    seen_urls: list[str] = []

    def fake_get_json(url: str, timeout: int = 30):
        seen_urls.append(url)
        counter["page"] += 1
        plugins = [
            _make_plugin(f"page{counter['page']}-{i}", stars=10)
            for i in range(100)
        ]
        return _api_response(plugins, limit=100, total=10000)

    monkeypatch.setattr(spd, "_http_get_json", fake_get_json)
    monkeypatch.setattr(spd, "_write_page_cache", lambda *a, **kw: None)

    output_path = tmp_path / "plugins" / "index.json"
    rc = spd.main(["--output", str(output_path), "--limit-pages", "3"])
    assert rc == 0
    assert len(seen_urls) == 3, (
        f"Expected exactly 3 page fetches (max_pages cap), got {len(seen_urls)}"
    )

    with open(output_path, encoding="utf-8") as f:
        entries = json.load(f)
    assert len(entries) == 300


# ---------------------------------------------------------------------------
# Dedup against existing on-disk index
# ---------------------------------------------------------------------------


def test_dedup_against_existing_official_entries(monkeypatch, tmp_path):
    """Existing official entry must win on source_url collision.

    Pre-seed the output file with one official entry (source_priority=1000,
    source="claude-plugins-official"). The API returns two community plugins:
    one with the same gitUrl (must be skipped) and one with a different one
    (must be added). The official entry must remain byte-for-byte identical.
    """
    output_path = tmp_path / "plugins" / "index.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    official_entry = {
        "id": "anthropic-claude-code",
        "name": "claude-code",
        "type": "plugin",
        "description": "Official plugin (do not overwrite)",
        "source_url": "https://github.com/anthropics/claude-code",
        "category": "developer-tools",
        "tags": ["official"],
        "tech_stack": [],
        "source": "claude-plugins-official",
        "source_priority": 1000,
        "marketplace_url": (
            "https://github.com/anthropics/claude-plugins-official"
        ),
        "platforms": ["claude-code"],
        "install": {
            "method": "plugin_marketplace",
            "marketplace": "anthropics/claude-plugins-official",
            "plugin_name": "claude-code",
        },
        "bundle": {
            "skills_count": 0,
            "commands_count": 0,
            "agents_count": 0,
            "mcp_servers_count": 0,
            "skills_namespaces": [],
            "hooks_count": 0,
            "hook_events": [],
            "mcp_server_names": [],
            "is_marketplace_repo": False,
        },
        "manifest_completeness": 1.0,
        "last_synced": "2025-01-01",
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump([official_entry], f, indent=2)

    # API: one collision (same gitUrl, different namespace/name) + one fresh.
    plugins = [
        _make_plugin(
            "claude-code-clone",
            namespace="community",
            stars=42,
            git_url="https://github.com/anthropics/claude-code",
        ),
        _make_plugin(
            "fresh-plugin",
            namespace="community",
            stars=20,
            git_url="https://github.com/community/fresh-plugin",
        ),
    ]
    _install_paged_http(monkeypatch, [_api_response(plugins, limit=100)])

    rc = spd.main(["--output", str(output_path)])
    assert rc == 0

    with open(output_path, encoding="utf-8") as f:
        entries = json.load(f)
    assert len(entries) == 2, (
        f"Expected existing 1 + new 1 = 2 entries, got {len(entries)}: "
        f"{[e.get('id') for e in entries]}"
    )

    # The official entry must be preserved byte-for-byte.
    by_id = {e["id"]: e for e in entries}
    assert "anthropic-claude-code" in by_id
    assert by_id["anthropic-claude-code"] == official_entry

    # The new community entry is the non-colliding one.
    community_ids = [
        eid for eid in by_id
        if by_id[eid].get("source") == "claude-plugins-dev"
    ]
    assert len(community_ids) == 1
    new_entry = by_id[community_ids[0]]
    assert new_entry["name"] == "fresh-plugin"
    assert new_entry["source_url"] == "https://github.com/community/fresh-plugin"


def test_skips_plugin_source_repo(monkeypatch, tmp_path):
    """Repos listed in plugin_sources.json are not imported as dev entries."""
    plugins = [
        _make_plugin(
            "everything-claude-code",
            namespace="affaan-m",
            stars=10000,
            git_url="https://github.com/affaan-m/everything-claude-code",
        ),
        _make_plugin(
            "ordinary",
            namespace="community",
            stars=10000,
            git_url="https://github.com/community/ordinary",
        ),
    ]
    _install_paged_http(monkeypatch, [_api_response(plugins, limit=100)])
    monkeypatch.setattr(
        spd,
        "is_plugin_source",
        lambda url: url == "https://github.com/affaan-m/everything-claude-code",
    )

    output_path = tmp_path / "plugins" / "index.json"
    rc = spd.main(["--output", str(output_path)])
    assert rc == 0

    with open(output_path, encoding="utf-8") as f:
        entries = json.load(f)

    assert [e["name"] for e in entries] == ["ordinary"]


def test_prunes_existing_plugin_source_repo(monkeypatch, tmp_path):
    """Previously imported dev entries are removed after repo skip is added."""
    output_path = tmp_path / "plugins" / "index.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    stale = {
        "id": "affaan-m-everything-claude-code-everything-claude-code",
        "name": "everything-claude-code",
        "type": "plugin",
        "source": "claude-plugins-dev",
        "source_url": "https://github.com/affaan-m/everything-claude-code",
    }
    keep = {
        "id": "community-ordinary",
        "name": "ordinary",
        "type": "plugin",
        "source": "claude-plugins-dev",
        "source_url": "https://github.com/community/ordinary",
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump([stale, keep], f, indent=2)

    _install_paged_http(
        monkeypatch,
        [
            _api_response(
                [
                    _make_plugin(
                        "ordinary",
                        namespace="community",
                        stars=10000,
                        git_url="https://github.com/community/ordinary",
                    )
                ],
                limit=100,
            )
        ],
    )
    monkeypatch.setattr(
        spd,
        "is_plugin_source",
        lambda url: url == "https://github.com/affaan-m/everything-claude-code",
    )

    rc = spd.main(["--output", str(output_path)])
    assert rc == 0

    with open(output_path, encoding="utf-8") as f:
        entries = json.load(f)

    assert entries == [keep]


# ---------------------------------------------------------------------------
# Failure isolation — exception during fetch
# ---------------------------------------------------------------------------


def test_failure_in_fetch_returns_zero_exit(monkeypatch, tmp_path):
    """Exception in ``_http_get_json`` must NOT crash CI.

    main() returns 0 and the existing on-disk file is untouched.
    """
    output_path = tmp_path / "plugins" / "index.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    sentinel = [{"id": "preexisting", "name": "keep-me", "type": "plugin"}]
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(sentinel, f, indent=2)
    original_mtime = os.path.getmtime(output_path)

    def fake_get_json(url: str, timeout: int = 30):
        raise RuntimeError("simulated network kaboom")

    monkeypatch.setattr(spd, "_http_get_json", fake_get_json)
    monkeypatch.setattr(spd, "_write_page_cache", lambda *a, **kw: None)

    rc = spd.main(["--output", str(output_path)])
    assert rc == 0  # task 7.5: never block CI

    # File is untouched (content + mtime).
    with open(output_path, encoding="utf-8") as f:
        after = json.load(f)
    assert after == sentinel
    assert os.path.getmtime(output_path) == original_mtime


# ---------------------------------------------------------------------------
# Empty-response handling
# ---------------------------------------------------------------------------


def test_zero_plugins_returns_zero_exit(monkeypatch, tmp_path, caplog):
    """API returns an empty plugins list → exit 0, output file untouched."""
    output_path = tmp_path / "plugins" / "index.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    sentinel = [{"id": "preexisting", "name": "keep-me", "type": "plugin"}]
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(sentinel, f, indent=2)
    original_mtime = os.path.getmtime(output_path)

    _install_paged_http(monkeypatch, [_api_response([], limit=100)])

    with caplog.at_level("WARNING", logger="sync_plugins_dev"):
        rc = spd.main(["--output", str(output_path)])
    assert rc == 0

    # Warning surfaces the zero-result branch.
    assert any(
        "0 entries" in rec.getMessage() or "leaving" in rec.getMessage()
        for rec in caplog.records
    )

    # File untouched.
    with open(output_path, encoding="utf-8") as f:
        after = json.load(f)
    assert after == sentinel
    assert os.path.getmtime(output_path) == original_mtime


# ---------------------------------------------------------------------------
# manifest_completeness strata
# ---------------------------------------------------------------------------


def test_manifest_completeness_full_when_all_fields_present():
    """name + version + description + author all set → 1.0."""
    score = spd._compute_manifest_completeness(
        {
            "name": "alpha",
            "version": "1.0.0",
            "description": "An alpha plugin",
            "author": "tester",
        }
    )
    assert score == 1.0


def test_manifest_completeness_partial():
    """Missing one of the four required fields → 0.7."""
    # Missing version.
    score_no_version = spd._compute_manifest_completeness(
        {
            "name": "alpha",
            "description": "An alpha plugin",
            "author": "tester",
        }
    )
    assert score_no_version == 0.7

    # Missing description.
    score_no_desc = spd._compute_manifest_completeness(
        {
            "name": "alpha",
            "version": "1.0.0",
            "author": "tester",
        }
    )
    assert score_no_desc == 0.7


# ---------------------------------------------------------------------------
# Entry shape
# ---------------------------------------------------------------------------


def test_entry_shape_basic(monkeypatch, tmp_path):
    """One plugin → entry has every required catalog field."""
    plugin = _make_plugin(
        "shaped",
        namespace="acme",
        stars=42,
        description="Shape probe",
        skills=["ship-it", "review-pr"],
    )
    _install_paged_http(monkeypatch, [_api_response([plugin], limit=100)])

    # Disable the live PluginContentFetcher so this test stays offline; the
    # entry-shape assertions below cover the API-hint fallback path.
    monkeypatch.setattr(spd, "PluginContentFetcher", None)

    output_path = tmp_path / "plugins" / "index.json"
    rc = spd.main(["--output", str(output_path)])
    assert rc == 0

    with open(output_path, encoding="utf-8") as f:
        entries = json.load(f)
    assert len(entries) == 1
    entry = entries[0]

    # Required identity fields.
    assert "id" in entry and entry["id"]
    assert entry["type"] == "plugin"
    assert entry["source"] == "claude-plugins-dev"
    assert entry["source_priority"] == 700

    # bundle.skills_namespaces populated from API ``skills`` array.
    assert entry["bundle"]["skills_namespaces"] == [
        "shaped:ship-it",
        "shaped:review-pr",
    ]
    assert entry["bundle"]["skills_count"] == 2

    # install.method is the marketplace install indicator.
    assert entry["install"]["method"] == "plugin_marketplace"
    assert entry["install"]["plugin_name"] == "shaped"
    assert entry["install"]["marketplace"] == "acme"

    # Spot-check a few other documented fields.
    assert entry["platforms"] == ["claude-code"]
    assert entry["stars"] == 42
    assert entry["version"] == "1.0.0"
    assert entry["source_url"] == "https://github.com/acme/shaped"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
