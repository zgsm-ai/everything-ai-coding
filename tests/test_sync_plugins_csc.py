"""Tests for sync_plugins_csc — the first-party cospowers (yhangf/csc-plugins) sync.

Covers the pure, network-free logic (tree discovery, bundle counting,
merge-preserve idempotency) directly, and exercises entry construction /
collection by monkeypatching the module's two HTTP helpers so no real GitHub
call is made.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import sync_plugins_csc as scp  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures: a fake csc-plugins monorepo with 2 plugins
# ---------------------------------------------------------------------------

FAKE_TREE = [
    "README.md",
    "cospowers-requirements-plugin/.claude-plugin/plugin.json",
    "cospowers-requirements-plugin/.claude-plugin/marketplace.json",
    "cospowers-requirements-plugin/skills/aireq-evaluator/SKILL.md",
    "cospowers-requirements-plugin/skills/sysreq-evaluator/SKILL.md",
    "cospowers-requirements-plugin/skills/aireq-evaluator/README.zh.md",  # not a SKILL.md
    "cospowers-tdd-development-plugin/.claude-plugin/plugin.json",
    "cospowers-tdd-development-plugin/.claude-plugin/marketplace.json",
    "cospowers-tdd-development-plugin/skills/tdd-loop/SKILL.md",
    "cospowers-tdd-development-plugin/agents/code-reviewer.md",
    "cospowers-tdd-development-plugin/commands/run.md",
]

PLUGIN_JSON = {
    "cospowers-requirements-plugin": {
        "name": "cospowers-requirements",
        "description": "需求梳理插件",
        "version": "0.0.1",
    },
    "cospowers-tdd-development-plugin": {
        "name": "cospowers-tdd-development",
        "description": "TDD 编码插件",
        "version": "0.0.2",
    },
}

MARKETPLACE_JSON = {
    "cospowers-requirements-plugin": {"name": "ai-workers-requirements"},
    "cospowers-tdd-development-plugin": {"name": "ai-workers-tdd"},
}


@pytest.fixture
def fake_http(monkeypatch):
    """Route scp's HTTP helpers to the in-memory fixtures above."""

    def fake_get_json(url, timeout=30):
        if url.startswith("https://api.github.com/repos/yhangf/csc-plugins/git/trees/"):
            return {"tree": [{"type": "blob", "path": p} for p in FAKE_TREE]}
        if url == "https://api.github.com/repos/yhangf/csc-plugins":
            return {"stargazers_count": 7, "pushed_at": "2026-06-03T07:47:30Z"}
        for subdir, pj in PLUGIN_JSON.items():
            if url.endswith(f"{subdir}/.claude-plugin/plugin.json"):
                return pj
        for subdir, mj in MARKETPLACE_JSON.items():
            if url.endswith(f"{subdir}/.claude-plugin/marketplace.json"):
                return mj
        return None

    monkeypatch.setattr(scp, "_http_get_json", fake_get_json)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def test_discover_plugin_subdirs():
    subdirs = scp.discover_plugin_subdirs(FAKE_TREE)
    assert subdirs == [
        "cospowers-requirements-plugin",
        "cospowers-tdd-development-plugin",
    ]


def test_compute_bundle_counts_skills_namespaces_and_agents():
    b = scp.compute_bundle(
        FAKE_TREE, "cospowers-requirements-plugin", "cospowers-requirements"
    )
    assert b["skills_count"] == 2  # README.zh.md must NOT be counted
    assert b["skills_namespaces"] == [
        "cospowers-requirements:aireq-evaluator",
        "cospowers-requirements:sysreq-evaluator",
    ]
    assert b["agents_count"] == 0
    assert b["commands_count"] == 0

    b2 = scp.compute_bundle(
        FAKE_TREE, "cospowers-tdd-development-plugin", "cospowers-tdd-development"
    )
    assert b2["skills_count"] == 1
    assert b2["agents_count"] == 1
    assert b2["commands_count"] == 1


# ---------------------------------------------------------------------------
# Entry construction / collection
# ---------------------------------------------------------------------------

def test_collect_entries_shape(fake_http):
    entries = scp.collect_entries()
    assert len(entries) == 2
    by_id = {e["id"]: e for e in entries}

    req = by_id["cospowers-requirements"]
    assert req["id"] == req["name"] == "cospowers-requirements"  # id == plugin name
    assert req["type"] == "plugin"
    assert (
        req["source_url"]
        == "https://github.com/yhangf/csc-plugins/tree/main/cospowers-requirements-plugin"
    )
    assert req["source"] == "csc-plugins"
    assert req["final_score"] == 100
    assert req["health"]["score"] == 100
    assert req["stars"] == 7
    assert req["version"] == "0.0.1"
    # install block: marketplace-verified + required fields present
    inst = req["install"]
    assert inst["method"] == "plugin_marketplace"
    assert inst["plugin_name"] == "cospowers-requirements"
    assert inst["marketplace_repo"] == "yhangf/csc-plugins"
    assert inst["marketplace_name"] == "ai-workers-requirements"
    assert inst["marketplace_verified"] is True
    # provenance tags
    assert "cospowers" in req["tags"] and "ai-workers" in req["tags"]


def test_entries_satisfy_catalog_required_fields(fake_http):
    required = {
        "id", "name", "type", "description", "source_url", "stars",
        "category", "tags", "tech_stack", "install", "source", "last_synced",
    }
    for e in scp.collect_entries():
        assert required.issubset(e.keys()), f"missing {required - set(e.keys())}"


def test_entries_pass_download_catalog_verified_gate(fake_http):
    """The 6 install fields download_catalog._download_plugin requires + the
    marketplace_verified gate must be satisfied, or the .plugin.json never
    gets emitted (research/architecture.md §3)."""
    import download_catalog as dc  # noqa: E402

    entries = scp.collect_entries()
    prepared = dc._prepare_plugin_entries(entries)
    # all entries survive the verified gate
    assert len(prepared) == len(entries)
    for e in prepared:
        inst = e["install"]
        for f in dc.PLUGIN_REQUIRED_INSTALL_FIELDS:
            assert inst.get(f), f"missing required install field {f} on {e['id']}"


# ---------------------------------------------------------------------------
# Merge-preserve idempotency
# ---------------------------------------------------------------------------

def test_merge_preserves_foreign_and_replaces_own():
    foreign = [
        {"id": "anthropic-foo", "source": "claude-plugins-official"},
        {"id": "dev-bar", "source": "claude-plugins-dev"},
    ]
    stale_own = [{"id": "cospowers-old", "source": "csc-plugins"}]
    existing = foreign + stale_own
    fresh = [
        {"id": "cospowers-requirements", "source": "csc-plugins"},
        {"id": "cospowers-tdd-development", "source": "csc-plugins"},
    ]
    merged = scp.merge_into_index(existing, fresh)
    ids = [e["id"] for e in merged]
    # stale own entry dropped, fresh added, foreign preserved, sorted by id
    assert "cospowers-old" not in ids
    assert "anthropic-foo" in ids and "dev-bar" in ids
    assert "cospowers-requirements" in ids and "cospowers-tdd-development" in ids
    assert ids == sorted(ids)


def test_merge_is_idempotent_on_rerun():
    existing = [{"id": "anthropic-foo", "source": "claude-plugins-official"}]
    fresh = [{"id": "cospowers-requirements", "source": "csc-plugins"}]
    once = scp.merge_into_index(existing, fresh)
    twice = scp.merge_into_index(once, fresh)
    assert once == twice
