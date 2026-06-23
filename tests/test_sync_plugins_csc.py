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
    # evaluators (directory type — like skills, different dir)
    "cospowers-requirements-plugin/evaluators/aireq-evaluator/SKILL.md",
    "cospowers-requirements-plugin/evaluators/aireq-evaluator/README.zh.md",
    # rules: NESTED under groups, with non-ASCII filenames (path-faithful)
    "cospowers-requirements-plugin/rules/dfx/安全.md",
    "cospowers-requirements-plugin/rules/requirement-checklists/baseline-checklist.md",
    # templates: flat single files
    "cospowers-requirements-plugin/templates/user-requirement-template.md",
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
        # Slash-containing branch → resolved to a SHA first via git/ref/heads/<b>.
        if url.startswith("https://api.github.com/repos/yhangf/csc-plugins/git/ref/heads/"):
            return {"ref": "refs/heads/x", "object": {"sha": "d" * 40, "type": "commit"}}
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


def test_compute_bundle_captures_evaluators_as_directory_paths():
    """evaluators/<name>/SKILL.md → position-aligned namespaces + verbatim paths
    (directory type, same shape as skills)."""
    b = scp.compute_bundle(
        FAKE_TREE, "cospowers-requirements-plugin", "cospowers-requirements"
    )
    assert b["evaluators_count"] == 1
    assert b["evaluators_namespaces"] == ["cospowers-requirements:aireq-evaluator"]
    assert b["evaluator_paths"] == [
        "cospowers-requirements-plugin/evaluators/aireq-evaluator/SKILL.md"
    ]
    # README.zh.md siblings must NOT spawn an extra evaluator.
    assert len(b["evaluator_paths"]) == b["evaluators_count"] == 1


def test_compute_bundle_captures_nested_rules_path_faithful():
    """rules/<group>/<file>.md are NESTED and may carry non-ASCII filenames.
    Paths must be VERBATIM (path-faithful) and namespaces keep the <group>/<file>
    shape so the synthesized id round-trips."""
    b = scp.compute_bundle(
        FAKE_TREE, "cospowers-requirements-plugin", "cospowers-requirements"
    )
    assert b["rules_count"] == 2
    # sorted by name; non-ASCII first under dfx/, then requirement-checklists/
    assert b["rule_paths"] == [
        "cospowers-requirements-plugin/rules/dfx/安全.md",
        "cospowers-requirements-plugin/rules/requirement-checklists/baseline-checklist.md",
    ]
    assert b["rules_namespaces"] == [
        "cospowers-requirements:dfx/安全",
        "cospowers-requirements:requirement-checklists/baseline-checklist",
    ]
    # position alignment: namespaces[i] ↔ rule_paths[i]
    assert len(b["rules_namespaces"]) == len(b["rule_paths"]) == b["rules_count"]


def test_compute_bundle_captures_templates_flat():
    b = scp.compute_bundle(
        FAKE_TREE, "cospowers-requirements-plugin", "cospowers-requirements"
    )
    assert b["templates_count"] == 1
    assert b["templates_namespaces"] == [
        "cospowers-requirements:user-requirement-template"
    ]
    assert b["template_paths"] == [
        "cospowers-requirements-plugin/templates/user-requirement-template.md"
    ]


def test_compute_bundle_captures_commands_and_agents_paths():
    """commands/agents now also carry position-aligned *_paths (not just counts)."""
    b = scp.compute_bundle(
        FAKE_TREE, "cospowers-tdd-development-plugin", "cospowers-tdd-development"
    )
    assert b["commands_count"] == 1
    assert b["command_paths"] == ["cospowers-tdd-development-plugin/commands/run.md"]
    assert b["commands_namespaces"] == ["cospowers-tdd-development:run"]
    assert b["agents_count"] == 1
    assert b["agent_paths"] == [
        "cospowers-tdd-development-plugin/agents/code-reviewer.md"
    ]
    assert b["agents_namespaces"] == ["cospowers-tdd-development:code-reviewer"]


def test_compute_bundle_source_coordinates_present_for_all_kinds():
    """source_repo/source_ref/plugin_root must be present so merge_index can
    synthesize a working git_clone install for EVERY kind."""
    b = scp.compute_bundle(
        FAKE_TREE, "cospowers-requirements-plugin", "cospowers-requirements"
    )
    assert b["source_repo"] == scp.CSC_REPO
    assert b["source_ref"] == scp.CSC_BRANCH
    assert b["plugin_root"] == "cospowers-requirements-plugin"


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
    # marketplace_repo points at OUR published repo, not the yhangf source
    assert inst["marketplace_repo"] == "costrict-plugins-repo/cospowers-requirements"
    assert inst["marketplace"] == "costrict-plugins-repo/cospowers-requirements"
    assert inst["marketplace_name"] == "ai-workers-requirements"
    assert inst["marketplace_verified"] is True
    # build/content source stays on yhangf (not user-facing)
    assert req["source_url"] == (
        "https://github.com/yhangf/csc-plugins/tree/main/cospowers-requirements-plugin"
    )
    # provenance tags
    assert "cospowers" in req["tags"] and "ai-workers" in req["tags"]
    # full-content mirror flag (marketplace build.py skips pruning)
    assert req["prune_content"] is False


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


def test_merge_sort_false_preserves_order_and_appends():
    # sort=False keeps existing order and appends fresh at the end (small diff
    # for the 33MB top-level index). Still idempotent across re-runs.
    existing = [
        {"id": "z-foo", "source": "claude-plugins-official"},
        {"id": "a-bar", "source": "claude-plugins-dev"},
        {"id": "cospowers-old", "source": "csc-plugins"},
    ]
    fresh = [{"id": "cospowers-requirements", "source": "csc-plugins"}]
    merged = scp.merge_into_index(existing, fresh, sort=False)
    assert [e["id"] for e in merged] == ["z-foo", "a-bar", "cospowers-requirements"]
    assert merged == scp.merge_into_index(merged, fresh, sort=False)


# ---------------------------------------------------------------------------
# Branch parameterization (--branch / $CSC_BRANCH)
# ---------------------------------------------------------------------------

def test_default_branch_is_main():
    # Guard the default so an un-parameterized run keeps the historical behaviour.
    assert scp.CSC_BRANCH == "main"


def test_compute_bundle_uses_given_branch():
    b = scp.compute_bundle(
        FAKE_TREE, "cospowers-requirements-plugin", "cospowers-requirements",
        "feat/new-prompt",
    )
    assert b["source_ref"] == "feat/new-prompt"
    assert b["source_repo"] == scp.CSC_REPO  # repo unchanged, only the ref moves


def test_collect_entries_threads_branch_to_source_url_and_ref(fake_http):
    # A non-default ref must flow into BOTH source_url (so marketplace build.py
    # clones it) and bundle.source_ref (the authoritative ref build.py prefers).
    entries = scp.collect_entries("feat/new-prompt")
    req = {e["id"]: e for e in entries}["cospowers-requirements"]
    assert req["source_url"] == (
        "https://github.com/yhangf/csc-plugins"
        "/tree/feat/new-prompt/cospowers-requirements-plugin"
    )
    assert req["bundle"]["source_ref"] == "feat/new-prompt"


def test_collect_entries_default_is_main(fake_http):
    # AC2/AC5 regression: no branch arg → identical to the pre-change main path.
    req = {e["id"]: e for e in scp.collect_entries()}["cospowers-requirements"]
    assert req["source_url"] == (
        "https://github.com/yhangf/csc-plugins/tree/main/cospowers-requirements-plugin"
    )
    assert req["bundle"]["source_ref"] == "main"


def test_slash_branch_resolved_to_sha_for_reads(monkeypatch, fake_http):
    # A slash-containing branch must be resolved to a SHA (git/trees + raw take a
    # single path segment), and that SHA must be what content reads use — while
    # source_url / source_ref keep the human-readable branch.
    read_refs: list[str] = []
    orig = scp.fetch_tree_paths

    def spy_tree(repo, ref):
        read_refs.append(ref)
        return orig(repo, ref)

    monkeypatch.setattr(scp, "fetch_tree_paths", spy_tree)
    entries = scp.collect_entries("feat/new-prompt")
    assert read_refs == ["d" * 40]  # tree fetched by resolved SHA, not "feat/new-prompt"
    req = {e["id"]: e for e in entries}["cospowers-requirements"]
    assert "/tree/feat/new-prompt/" in req["source_url"]  # display ref kept
    assert req["bundle"]["source_ref"] == "feat/new-prompt"


def test_unresolvable_slash_branch_aborts(monkeypatch):
    # If a slash branch can't be resolved to a SHA, abort with no entries rather
    # than silently reading the wrong/default tree.
    monkeypatch.setattr(scp, "_http_get_json", lambda url, timeout=30: None)
    assert scp.collect_entries("feat/does-not-exist") == []


def test_non_slash_branch_skips_resolution(monkeypatch, fake_http):
    # main / dev (no slash) must NOT hit the ref-resolution endpoint — zero extra
    # call, byte-identical to the historical direct read.
    hits: list[str] = []
    real = scp._http_get_json

    def spy(url, timeout=30):
        if "/git/ref/heads/" in url:
            hits.append(url)
        return real(url, timeout)

    monkeypatch.setattr(scp, "_http_get_json", spy)
    scp.collect_entries("main")
    assert hits == []


def test_main_branch_flag_overrides(monkeypatch, tmp_path, fake_http):
    # End-to-end: `--branch` reaches collect_entries and lands in the written index.
    out = tmp_path / "plugins-index.json"
    rc = scp.main(["--output", str(out), "--branch", "feat/x"])
    assert rc == 0
    import json
    written = json.loads(out.read_text(encoding="utf-8"))
    csc = [e for e in written if e.get("source") == "csc-plugins"]
    assert csc and all("/tree/feat/x/" in e["source_url"] for e in csc)
    assert all(e["bundle"]["source_ref"] == "feat/x" for e in csc)
