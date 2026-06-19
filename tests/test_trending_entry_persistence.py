"""Round-over-round persistence regression for active-discovery entries.

Background (root cause): ``sync_skills.py`` and ``sync_plugins_official.py``
used to ``save_index(all_entries)`` blanket-overwrite their per-type index,
erasing the github-trending / 促升-slug entries that ``triage_github_trending.py``
wrote the previous cycle. ``known_repos`` then prevents triage from
re-discovering already-ingested repos, so those entries were lost forever.

These tests pin the fix: both sync scripts must PRESERVE existing
active-discovery (``source == github-trending`` or ``source ∈ promoted slugs``)
entries when they overwrite the index, while still adding/updating their own
Tier1/2 (skills) and marketplace (plugins) entries.

Coverage:
  - skills: existing github-trending + 促升 + Tier1 → after sync write, all
    survive; Tier1 is regenerated; 0-entry guard / overlay_added_at / dedup
    semantics unchanged.
  - plugins: existing github-trending + 促升 + same-monorepo multi-plugin
    (shared source_url) survive a fresh official sync; shared-URL entries are
    NOT deduped away.
  - recover_trending_entries.py: pulls active-discovery entries from a (mocked)
    git history, merge-preserves into current, idempotent by id (+url for
    skills), --dry-run writes nothing, never clobbers fresh entries.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import sync_skills as ss  # noqa: E402
import sync_plugins_official as spo  # noqa: E402
import recover_trending_entries as rec  # noqa: E402


PROMOTED_SLUG = "mattpocock/skills"


# ---------------------------------------------------------------------------
# Unit: domain predicate + merge helpers (shared shape across both scripts)
# ---------------------------------------------------------------------------


def test_is_trending_owned_predicate():
    slugs = {PROMOTED_SLUG}
    assert ss._is_trending_owned({"source": "github-trending"}, slugs) is True
    assert ss._is_trending_owned({"source": PROMOTED_SLUG}, slugs) is True
    # Tier1/2 own sources are NOT in the active-discovery domain.
    assert ss._is_trending_owned({"source": "anthropics/skills"}, slugs) is False
    assert ss._is_trending_owned({"source": "ComposioHQ/awesome-claude-skills"}, slugs) is False
    assert ss._is_trending_owned({}, slugs) is False
    # Empty promoted set → only github-trending counts.
    assert ss._is_trending_owned({"source": PROMOTED_SLUG}, set()) is False
    assert ss._is_trending_owned({"source": "github-trending"}, set()) is True


def test_merge_keep_foreign_skills_id_and_url_dedup():
    primary = [
        {"id": "a", "source": "anthropics/skills", "source_url": "https://github.com/x/a"},
    ]
    foreign = [
        {"id": "a", "source": "github-trending", "source_url": "https://github.com/x/a"},  # id collision
        {"id": "b", "source": "github-trending", "source_url": "https://github.com/x/a"},  # url collision
        {"id": "c", "source": "github-trending", "source_url": "https://github.com/x/c"},  # new
    ]
    out = ss._merge_keep_foreign(primary, foreign, dedup_url=True)
    ids = [e["id"] for e in out]
    assert ids == ["a", "c"]  # a stays primary (not overwritten), c added, b dropped on url collision


def test_merge_keep_foreign_plugins_id_only_keeps_shared_url():
    """Plugins must dedup by id only — same-monorepo plugins share a source_url."""
    primary = [
        {"id": "mono-p1", "source": "claude-plugins-official", "source_url": "https://github.com/o/mono"},
    ]
    foreign = [
        {"id": "mono-p1", "source": "github-trending", "source_url": "https://github.com/o/mono"},  # id dup → drop
        {"id": "mono-p2", "source": "github-trending", "source_url": "https://github.com/o/mono"},  # shared url, new id → keep
    ]
    out = spo._merge_keep_foreign(primary, foreign)
    ids = {e["id"] for e in out}
    assert ids == {"mono-p1", "mono-p2"}  # shared-url p2 survives (id-only dedup)


# ---------------------------------------------------------------------------
# skills sync write-path persistence
# ---------------------------------------------------------------------------


@pytest.fixture
def _skills_catalog_dir(tmp_path, monkeypatch):
    catalog_dir = tmp_path / "skills"
    catalog_dir.mkdir()
    monkeypatch.setattr(ss, "CATALOG_DIR", str(catalog_dir))
    return catalog_dir


def _seed_index(path, entries):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f)


def test_sync_skills_preserves_active_discovery_entries(_skills_catalog_dir, monkeypatch):
    catalog_dir = _skills_catalog_dir
    index_path = os.path.join(str(catalog_dir), "index.json")

    # Existing index: 1 github-trending + 1 促升 slug + 1 Tier1 (stale copy).
    existing = [
        {"id": "gt-1", "name": "GT One", "type": "skill", "source": "github-trending",
         "source_url": "https://github.com/trend/one", "added_at": "2026-01-01"},
        {"id": "promo-1", "name": "Promo One", "type": "skill", "source": PROMOTED_SLUG,
         "source_url": "https://github.com/mattpocock/skills/tree/main/x", "added_at": "2026-01-01"},
        {"id": "tier1-1", "name": "Old Tier1", "type": "skill", "source": "anthropics/skills",
         "source_url": "https://github.com/anthropics/skills/tree/main/t1", "added_at": "2026-01-01"},
    ]
    _seed_index(index_path, existing)

    # Make sync's discovery produce ONLY a fresh Tier1 entry (mock network).
    fresh_tier1 = {
        "id": "tier1-1", "name": "Fresh Tier1", "type": "skill", "source": "anthropics/skills",
        "source_url": "https://github.com/anthropics/skills/tree/main/t1",
    }
    monkeypatch.setattr(ss, "parse_anthropic_skills", lambda: [dict(fresh_tier1)])
    monkeypatch.setattr(ss, "parse_ai_agent_skills", lambda: [])
    monkeypatch.setattr(ss, "parse_antigravity_skills", lambda: [])
    monkeypatch.setattr(ss, "parse_vasilyu_skills", lambda: [])
    monkeypatch.setattr(ss, "parse_claude_office_skills", lambda: [])
    monkeypatch.setattr(ss, "parse_composio_office_skills", lambda dirs: [])
    monkeypatch.setattr(ss, "discover_skills", lambda t1: [])
    monkeypatch.setattr(ss, "parse_openclaw_skills", lambda t1: [])
    monkeypatch.setattr(ss, "_supplement_openclaw_descriptions", lambda c: None)
    monkeypatch.setattr(ss, "load_plugin_sources", lambda: None)
    monkeypatch.setattr(ss, "is_plugin_source", lambda url: False)
    # 促升 slug set comes from the real promoted list normally; pin it for the test.
    monkeypatch.setattr(ss, "_load_promoted_slugs", lambda: {PROMOTED_SLUG})

    ss.sync()

    with open(index_path, encoding="utf-8") as f:
        written = json.load(f)
    by_id = {e["id"]: e for e in written}

    # All three survive.
    assert set(by_id) == {"gt-1", "promo-1", "tier1-1"}
    # Active-discovery entries preserved verbatim (source intact).
    assert by_id["gt-1"]["source"] == "github-trending"
    assert by_id["promo-1"]["source"] == PROMOTED_SLUG
    # Tier1 regenerated to the FRESH copy (sync owns it).
    assert by_id["tier1-1"]["name"] == "Fresh Tier1"
    # overlay_added_at carried the original added_at forward for the regenerated entry.
    assert by_id["tier1-1"]["added_at"] == "2026-01-01"


def test_sync_skills_zero_entry_guard_keeps_existing(_skills_catalog_dir, monkeypatch):
    """If discovery yields nothing, the 0-entry clobber guard must keep the index."""
    catalog_dir = _skills_catalog_dir
    index_path = os.path.join(str(catalog_dir), "index.json")
    existing = [
        {"id": "gt-1", "name": "GT One", "type": "skill", "source": "github-trending",
         "source_url": "https://github.com/trend/one", "added_at": "2026-01-01"},
        {"id": "tier1-1", "name": "Old Tier1", "type": "skill", "source": "anthropics/skills",
         "source_url": "https://github.com/anthropics/skills/tree/main/t1", "added_at": "2026-01-01"},
    ]
    _seed_index(index_path, existing)

    for fn in ("parse_anthropic_skills", "parse_ai_agent_skills", "parse_antigravity_skills",
               "parse_vasilyu_skills", "parse_claude_office_skills"):
        monkeypatch.setattr(ss, fn, lambda: [])
    monkeypatch.setattr(ss, "parse_composio_office_skills", lambda dirs: [])
    monkeypatch.setattr(ss, "discover_skills", lambda t1: [])
    monkeypatch.setattr(ss, "parse_openclaw_skills", lambda t1: [])
    monkeypatch.setattr(ss, "_supplement_openclaw_descriptions", lambda c: None)
    monkeypatch.setattr(ss, "load_plugin_sources", lambda: None)

    ss.sync()

    with open(index_path, encoding="utf-8") as f:
        written = json.load(f)
    # Untouched: 0-entry guard returned before any write.
    assert {e["id"] for e in written} == {"gt-1", "tier1-1"}


# ---------------------------------------------------------------------------
# plugin (sync_plugins_official) write-path persistence
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _stub_marketplace_verifier(monkeypatch):
    monkeypatch.setattr(
        spo.marketplace_verifier,
        "verify_marketplace",
        lambda repo, plugin_name, cache: (None, False),
    )


def _install_fake_http_official(monkeypatch, marketplaces):
    """Fake HTTP layer for the official sync.

    The marketplace flow uses ``_http_get`` (returns bytes → json.loads), so a
    dict payload must be JSON-encoded to bytes. ``marketplaces`` maps repo slug
    → marketplace.json dict.
    """
    def fake_http_get(url, timeout=30):
        for slug, payload in marketplaces.items():
            if f"/{slug}/" in url and url.endswith("marketplace.json"):
                return json.dumps(payload).encode("utf-8")
        return None

    def fake_http_get_json(url, timeout=30):
        return None

    monkeypatch.setattr(spo, "_http_get", fake_http_get)
    monkeypatch.setattr(spo, "_http_get_json", fake_http_get_json)


def test_sync_plugins_official_preserves_active_discovery(monkeypatch, tmp_path):
    output_path = tmp_path / "plugins" / "index.json"

    # Seed existing index with active-discovery plugins, including two
    # same-monorepo plugins that legitimately share a source_url.
    existing = [
        {"id": "gt-plugin-1", "name": "GT Plugin", "type": "plugin", "source": "github-trending",
         "source_url": "https://github.com/trend/plug", "added_at": "2026-01-01"},
        {"id": "promo-mono-p1", "name": "Mono P1", "type": "plugin", "source": PROMOTED_SLUG,
         "source_url": "https://github.com/mattpocock/skills", "added_at": "2026-01-01"},
        {"id": "promo-mono-p2", "name": "Mono P2", "type": "plugin", "source": PROMOTED_SLUG,
         "source_url": "https://github.com/mattpocock/skills", "added_at": "2026-01-01"},
        # An official-marketplace leftover the sync WILL regenerate (not foreign).
        {"id": "stale-official", "name": "Stale", "type": "plugin", "source": "claude-plugins-official",
         "source_url": "https://github.com/anthropics/claude-plugins-official", "added_at": "2026-01-01"},
    ]
    _seed_index(str(output_path), existing)

    _install_fake_http_official(monkeypatch, {
        "anthropics/claude-plugins-official": {
            "name": "official", "plugins": [{"name": "official-plugin", "source": "./official-plugin"}],
        },
        "obra/superpowers-marketplace": {"name": "obra", "plugins": []},
        "affaan-m/ECC": {"name": "ecc", "plugins": []},
    })
    monkeypatch.setattr(spo, "_load_promoted_slugs", lambda: {PROMOTED_SLUG})

    rc = spo.main(["--output", str(output_path)])
    assert rc == 0

    with open(output_path, encoding="utf-8") as f:
        written = json.load(f)
    by_id = {e["id"]: e for e in written}

    # Active-discovery plugins all preserved, including BOTH shared-URL monorepo plugins.
    assert "gt-plugin-1" in by_id
    assert "promo-mono-p1" in by_id
    assert "promo-mono-p2" in by_id  # shared source_url must NOT cause a drop
    # Sync's own fresh official plugin is present.
    assert any(e["source"] == "claude-plugins-official" for e in written)


# ---------------------------------------------------------------------------
# recover_trending_entries.py
# ---------------------------------------------------------------------------


def _patch_git_show(monkeypatch, skills_hist, plugins_hist, catalog_hist=None):
    def fake_git_show(sha, rel_path):
        if rel_path.endswith("skills/index.json"):
            return skills_hist
        if rel_path.endswith("plugins/index.json"):
            return plugins_hist
        if rel_path == "catalog/index.json":
            return list(catalog_hist or [])
        return []
    monkeypatch.setattr(rec, "git_show_index", fake_git_show)


def test_recover_dry_run_reports_and_writes_nothing(monkeypatch, tmp_path):
    skills_index = tmp_path / "skills" / "index.json"
    plugins_index = tmp_path / "plugins" / "index.json"
    catalog_index = tmp_path / "index.json"

    current_skills = [
        {"id": "cur-1", "type": "skill", "source": "anthropics/skills",
         "source_url": "https://github.com/anthropics/skills/tree/main/c1"},
    ]
    current_plugins = [
        {"id": "cur-p1", "type": "plugin", "source": "claude-plugins-official",
         "source_url": "https://github.com/anthropics/claude-plugins-official"},
    ]
    current_catalog = [
        {"id": "cur-1", "type": "skill", "source": "anthropics/skills",
         "source_url": "https://github.com/anthropics/skills/tree/main/c1"},
        {"id": "cur-p1", "type": "plugin", "source": "claude-plugins-official",
         "source_url": "https://github.com/anthropics/claude-plugins-official"},
    ]
    _seed_index(str(skills_index), current_skills)
    _seed_index(str(plugins_index), current_plugins)
    _seed_index(str(catalog_index), current_catalog)

    skills_hist = current_skills + [
        {"id": "lost-gt", "type": "skill", "source": "github-trending",
         "source_url": "https://github.com/trend/lost"},
        {"id": "lost-promo", "type": "skill", "source": PROMOTED_SLUG,
         "source_url": "https://github.com/mattpocock/skills/tree/main/lost"},
        {"id": "non-trending-noise", "type": "skill", "source": "some/other",
         "source_url": "https://github.com/some/other"},  # NOT active-discovery → ignored
    ]
    plugins_hist = current_plugins + [
        {"id": "lost-gt-plug", "type": "plugin", "source": "github-trending",
         "source_url": "https://github.com/trend/plug"},
    ]
    catalog_hist = current_catalog + [
        {"id": "lost-gt", "type": "skill", "source": "github-trending",
         "source_url": "https://github.com/trend/lost"},
        {"id": "lost-gt-plug", "type": "plugin", "source": "github-trending",
         "source_url": "https://github.com/trend/plug"},
    ]
    _patch_git_show(monkeypatch, skills_hist, plugins_hist, catalog_hist)
    monkeypatch.setattr(rec, "_load_promoted_slugs", lambda: {PROMOTED_SLUG})

    rc = rec.main([
        "--skills-index", str(skills_index),
        "--plugins-index", str(plugins_index),
        "--catalog-index", str(catalog_index),
    ])  # no --apply → dry-run
    assert rc == 0

    # Dry-run wrote nothing.
    with open(skills_index, encoding="utf-8") as f:
        assert {e["id"] for e in json.load(f)} == {"cur-1"}
    with open(plugins_index, encoding="utf-8") as f:
        assert {e["id"] for e in json.load(f)} == {"cur-p1"}
    with open(catalog_index, encoding="utf-8") as f:
        assert {e["id"] for e in json.load(f)} == {"cur-1", "cur-p1"}


def test_recover_apply_backfills_only_active_discovery(monkeypatch, tmp_path):
    skills_index = tmp_path / "skills" / "index.json"
    plugins_index = tmp_path / "plugins" / "index.json"
    catalog_index = tmp_path / "index.json"

    current_skills = [
        {"id": "cur-1", "type": "skill", "source": "anthropics/skills",
         "source_url": "https://github.com/anthropics/skills/tree/main/c1"},
        # Already-recovered github-trending entry (idempotency target).
        {"id": "lost-gt", "type": "skill", "source": "github-trending",
         "source_url": "https://github.com/trend/lost"},
    ]
    current_plugins = [
        {"id": "cur-p1", "type": "plugin", "source": "claude-plugins-official",
         "source_url": "https://github.com/anthropics/claude-plugins-official"},
    ]
    current_catalog = [
        {"id": "cur-1", "type": "skill", "source": "anthropics/skills",
         "source_url": "https://github.com/anthropics/skills/tree/main/c1"},
        {"id": "cur-p1", "type": "plugin", "source": "claude-plugins-official",
         "source_url": "https://github.com/anthropics/claude-plugins-official"},
    ]
    _seed_index(str(skills_index), current_skills)
    _seed_index(str(plugins_index), current_plugins)
    _seed_index(str(catalog_index), current_catalog)

    skills_hist = [
        {"id": "lost-gt", "type": "skill", "source": "github-trending",
         "source_url": "https://github.com/trend/lost"},  # already present → skip (idempotent)
        {"id": "lost-promo", "type": "skill", "source": PROMOTED_SLUG,
         "source_url": "https://github.com/mattpocock/skills/tree/main/lost"},  # new → add
        {"id": "noise", "type": "skill", "source": "x/y",
         "source_url": "https://github.com/x/y"},  # not active-discovery → ignore
    ]
    plugins_hist = [
        {"id": "lost-gt-plug", "type": "plugin", "source": "github-trending",
         "source_url": "https://github.com/trend/plug"},  # new → add
        # Same-monorepo second plugin sharing the URL — plugins dedup by id only.
        {"id": "lost-gt-plug-2", "type": "plugin", "source": "github-trending",
         "source_url": "https://github.com/trend/plug"},
    ]
    catalog_hist = [
        # Mixed skills + plugins; same-monorepo plugins sharing a URL must survive (id-only).
        {"id": "cur-1", "type": "skill", "source": "anthropics/skills",
         "source_url": "https://github.com/anthropics/skills/tree/main/c1"},  # already present → skip (not even active-discovery)
        {"id": "lost-promo", "type": "skill", "source": PROMOTED_SLUG,
         "source_url": "https://github.com/mattpocock/skills/tree/main/lost"},  # new → add
        {"id": "lost-gt-plug", "type": "plugin", "source": "github-trending",
         "source_url": "https://github.com/trend/plug"},  # new → add
        {"id": "lost-gt-plug-2", "type": "plugin", "source": "github-trending",
         "source_url": "https://github.com/trend/plug"},  # shared URL, new id → add (id-only)
        {"id": "catalog-noise", "type": "skill", "source": "x/y",
         "source_url": "https://github.com/x/y"},  # not active-discovery → ignore
    ]
    _patch_git_show(monkeypatch, skills_hist, plugins_hist, catalog_hist)
    monkeypatch.setattr(rec, "_load_promoted_slugs", lambda: {PROMOTED_SLUG})

    rc = rec.main([
        "--apply",
        "--skills-index", str(skills_index),
        "--plugins-index", str(plugins_index),
        "--catalog-index", str(catalog_index),
    ])
    assert rc == 0

    with open(skills_index, encoding="utf-8") as f:
        skills_out = {e["id"] for e in json.load(f)}
    # cur-1 untouched, lost-gt not duplicated, lost-promo recovered, noise NOT pulled in.
    assert skills_out == {"cur-1", "lost-gt", "lost-promo"}

    with open(plugins_index, encoding="utf-8") as f:
        plugins_out = {e["id"] for e in json.load(f)}
    # Both shared-URL monorepo plugins recovered (id-only dedup), cur-p1 kept.
    assert plugins_out == {"cur-p1", "lost-gt-plug", "lost-gt-plug-2"}

    with open(catalog_index, encoding="utf-8") as f:
        catalog_out = {e["id"] for e in json.load(f)}
    # Merged catalog: current entries kept, lost-gt not duplicated, both shared-URL
    # monorepo plugins recovered (id-only), promo skill recovered, noise NOT pulled in.
    assert catalog_out == {
        "cur-1", "cur-p1", "lost-promo", "lost-gt-plug", "lost-gt-plug-2",
    }


def test_recover_idempotent_second_run_adds_nothing(monkeypatch, tmp_path):
    skills_index = tmp_path / "skills" / "index.json"
    plugins_index = tmp_path / "plugins" / "index.json"
    catalog_index = tmp_path / "index.json"
    _seed_index(str(skills_index), [])
    _seed_index(str(plugins_index), [])
    _seed_index(str(catalog_index), [])

    skills_hist = [
        {"id": "lost-promo", "type": "skill", "source": PROMOTED_SLUG,
         "source_url": "https://github.com/mattpocock/skills/tree/main/lost"},
    ]
    plugins_hist = []
    catalog_hist = [
        {"id": "lost-promo", "type": "skill", "source": PROMOTED_SLUG,
         "source_url": "https://github.com/mattpocock/skills/tree/main/lost"},
    ]
    _patch_git_show(monkeypatch, skills_hist, plugins_hist, catalog_hist)
    monkeypatch.setattr(rec, "_load_promoted_slugs", lambda: {PROMOTED_SLUG})

    common = [
        "--apply",
        "--skills-index", str(skills_index),
        "--plugins-index", str(plugins_index),
        "--catalog-index", str(catalog_index),
    ]
    assert rec.main(common) == 0
    with open(skills_index, encoding="utf-8") as f:
        first = {e["id"] for e in json.load(f)}
    assert first == {"lost-promo"}
    with open(catalog_index, encoding="utf-8") as f:
        first_catalog = {e["id"] for e in json.load(f)}
    assert first_catalog == {"lost-promo"}

    # Second run: lost-promo already present → 0 added, files unchanged.
    assert rec.main(common) == 0
    with open(skills_index, encoding="utf-8") as f:
        second = json.load(f)
    assert {e["id"] for e in second} == {"lost-promo"}
    assert len(second) == 1
    with open(catalog_index, encoding="utf-8") as f:
        second_catalog = json.load(f)
    assert {e["id"] for e in second_catalog} == {"lost-promo"}
    assert len(second_catalog) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
