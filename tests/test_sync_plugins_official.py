"""Tests for ``scripts/sync_plugins_official.py``.

The tests mock the HTTP layer (``_http_get`` / ``_http_get_json``) via
``monkeypatch`` so that no real network requests are made. Each test feeds
inline marketplace.json fixtures and asserts on the parsed catalog entries
or on script exit codes.

Coverage:

- Basic marketplace.json parsing → 2 entries with correct id/name/source.
- ``compute_manifest_completeness`` strata: full (1.0), missing version
  (0.7), missing description (0.7), no manifest (0.3).
- Failure isolation: one source raising an exception does not prevent
  the other source from being written.
- Zero-plugins overall causes ``main()`` to return non-zero.
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

import sync_plugins_official as spo  # noqa: E402


# Stub out the marketplace manifest fetch — the sync's `_entry_from_plugin`
# calls marketplace_verifier.verify_marketplace which would otherwise hit
# raw.githubusercontent.com. Tests focus on marketplace.json parsing /
# entry construction, not the verifier's HTTP layer (covered by
# test_marketplace_verifier.py).
@pytest.fixture(autouse=True)
def _stub_marketplace_verifier(monkeypatch):
    monkeypatch.setattr(
        spo.marketplace_verifier,
        "verify_marketplace",
        lambda repo, plugin_name, cache: (None, False),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _marketplace_payload(plugins: list[dict]) -> dict:
    return {"name": "test-marketplace", "plugins": plugins}


def _install_fake_http(
    monkeypatch: pytest.MonkeyPatch,
    *,
    marketplaces: dict[str, dict | Exception | None],
    manifests: dict[str, dict] | None = None,
):
    """Install fake ``_http_get`` and ``_http_get_json``.

    ``marketplaces`` keys are repo slugs (e.g. ``"anthropics/claude-plugins-official"``)
    and values are:
      - dict → JSON body returned for that marketplace.json
      - None → HTTP failure (None body)
      - Exception → raised when that URL is fetched

    ``manifests`` is a dict of full URL → manifest dict for plugin.json
    fetches done by ``_http_get_json``.
    """
    manifests = manifests or {}

    def fake_http_get(url: str, timeout: int = 30):
        for repo_slug, payload in marketplaces.items():
            if f"/{repo_slug}/" in url and url.endswith("marketplace.json"):
                if isinstance(payload, Exception):
                    raise payload
                if payload is None:
                    return None
                return json.dumps(payload).encode("utf-8")
        return None

    def fake_http_get_json(url: str, timeout: int = 30):
        # plugin.json fetches go through here directly.
        if url in manifests:
            return manifests[url]
        # Marketplace flow uses _http_get + json.loads, so this branch is
        # only hit by per-plugin manifest probes; default to None (404-ish).
        return None

    monkeypatch.setattr(spo, "_http_get", fake_http_get)
    monkeypatch.setattr(spo, "_http_get_json", fake_http_get_json)


# ---------------------------------------------------------------------------
# Marketplace parsing
# ---------------------------------------------------------------------------


def test_parse_marketplace_json_basic(monkeypatch, tmp_path):
    """Two plugins from the official source produce 2 catalog entries."""
    marketplace = _marketplace_payload(
        [
            {
                "name": "alpha",
                "version": "1.0.0",
                "description": "Alpha plugin",
                "author": "Anthropic",
                "source": "./plugins/alpha",
            },
            {
                "name": "beta",
                "version": "0.2.0",
                "description": "Beta plugin",
                "author": {"name": "Anthropic"},
                "source": "github:someone/beta",
            },
        ]
    )
    _install_fake_http(
        monkeypatch,
        marketplaces={
            "anthropics/claude-plugins-official": marketplace,
            # Second source returns empty, but with a valid shape so it
            # doesn't trip the "zero plugins" guard.
            "obra/superpowers-marketplace": _marketplace_payload([]),
            "affaan-m/ECC": _marketplace_payload([]),
        },
    )

    output_path = tmp_path / "plugins" / "index.json"
    rc = spo.main(["--output", str(output_path)])
    assert rc == 0

    with open(output_path, encoding="utf-8") as f:
        entries = json.load(f)

    assert len(entries) == 2
    by_id = {e["id"]: e for e in entries}

    alpha = by_id["anthropic-alpha"]
    assert alpha["name"] == "alpha"
    assert alpha["type"] == "plugin"
    assert alpha["source"] == "claude-plugins-official"
    assert alpha["source_priority"] == 1000
    assert alpha["platforms"] == ["claude-code"]
    assert alpha["install"]["method"] == "plugin_marketplace"
    assert alpha["install"]["marketplace"] == "anthropics/claude-plugins-official"
    assert alpha["install"]["plugin_name"] == "alpha"
    # source for "./plugins/alpha" → tree URL on the marketplace repo.
    assert "anthropics/claude-plugins-official/tree/main/plugins/alpha" in alpha[
        "source_url"
    ]

    beta = by_id["anthropic-beta"]
    assert beta["name"] == "beta"
    # github:someone/beta should resolve to https://github.com/someone/beta
    assert beta["source_url"] == "https://github.com/someone/beta"


def test_parse_everything_claude_code_source(monkeypatch, tmp_path):
    """The ECC marketplace source syncs all its plugins, including the "ecc"
    plugin itself.

    Historically "ecc" was collapsed via the plugin_sources.json plugins
    blacklist, on the assumption that affaan-m/ECC also exposed standalone
    sub-plugins carrying the canonical content. In reality the upstream
    marketplace ships only the single "ecc" plugin (source "./"), so the
    unconditional collapse dropped the sole plugin and the 216K-star source
    contributed zero entries. The blacklist entry was removed; "ecc" must now
    appear alongside any standalone sub-plugins."""
    marketplace = _marketplace_payload(
        [
            {
                "name": "ecc",
                "version": "2.0.0-rc.1",
                "description": "Harness-native ECC operator layer",
                "author": {"name": "Affaan Mustafa"},
                "source": "./",
                "category": "workflow",
                "tags": ["agents", "skills", "hooks"],
            },
            {
                "name": "operator",
                "version": "1.0.0",
                "description": "Standalone ECC operator plugin",
                "author": {"name": "Affaan Mustafa"},
                "source": "./plugins/operator",
                "category": "workflow",
                "tags": ["agents"],
            },
        ]
    )
    _install_fake_http(
        monkeypatch,
        marketplaces={
            "anthropics/claude-plugins-official": _marketplace_payload([]),
            "obra/superpowers-marketplace": _marketplace_payload([]),
            "affaan-m/ECC": marketplace,
        },
    )

    output_path = tmp_path / "plugins" / "index.json"
    rc = spo.main(["--output", str(output_path)])
    assert rc == 0

    with open(output_path, encoding="utf-8") as f:
        entries = json.load(f)

    # Both plugins survive now that the over-aggressive "ecc" collapse is gone.
    assert [e["name"] for e in entries] == ["ecc", "operator"]
    by_name = {e["name"]: e for e in entries}

    ecc = by_name["ecc"]
    assert ecc["id"] == "ecc-ecc"
    assert ecc["source"] == "everything-claude-code"
    assert ecc["source_priority"] == 900
    assert ecc["install"]["plugin_name"] == "ecc"

    operator = by_name["operator"]
    assert operator["id"] == "ecc-operator"
    assert operator["source"] == "everything-claude-code"
    assert operator["source_priority"] == 900
    assert operator["install"]["plugin_name"] == "operator"
    assert operator["install"]["marketplace_repo"] == "affaan-m/ECC"


# ---------------------------------------------------------------------------
# manifest_completeness strata
# ---------------------------------------------------------------------------


def test_manifest_completeness_full():
    """All four required fields present → 1.0."""
    score = spo.compute_manifest_completeness(
        {
            "name": "alpha",
            "version": "1.0.0",
            "description": "An alpha plugin",
            "author": "Anthropic",
        }
    )
    assert score == 1.0


def test_manifest_completeness_missing_version():
    """Missing version (rest present) → 0.7."""
    score = spo.compute_manifest_completeness(
        {
            "name": "alpha",
            "description": "An alpha plugin",
            "author": "Anthropic",
        }
    )
    assert score == 0.7


def test_manifest_completeness_missing_description():
    """Missing description (rest present) → 0.7."""
    score = spo.compute_manifest_completeness(
        {
            "name": "alpha",
            "version": "1.0.0",
            "author": "Anthropic",
        }
    )
    assert score == 0.7


def test_manifest_completeness_no_manifest(monkeypatch, tmp_path):
    """External github: source with only a name in the marketplace entry
    AND no fetchable plugin.json → manifest_completeness == 0.3.

    The script's ``_plugin_manifest_candidate_urls`` deliberately returns
    ``[]`` for ``github:owner/repo`` sources (it doesn't follow cross-repo
    URLs in this task), so no manifest is ever fetched. With only a name
    in the marketplace entry, the synthetic-manifest fallback also doesn't
    kick in (``description``, ``version``, ``author`` all empty), so the
    score collapses to the no-manifest floor.
    """
    marketplace = _marketplace_payload(
        [
            {
                "name": "lonely",
                "source": "github:someone/lonely",
            }
        ]
    )
    _install_fake_http(
        monkeypatch,
        marketplaces={
            "anthropics/claude-plugins-official": marketplace,
            "obra/superpowers-marketplace": _marketplace_payload([]),
            "affaan-m/ECC": _marketplace_payload([]),
        },
    )
    output_path = tmp_path / "plugins" / "index.json"
    rc = spo.main(["--output", str(output_path)])
    assert rc == 0

    with open(output_path, encoding="utf-8") as f:
        entries = json.load(f)
    assert len(entries) == 1
    assert entries[0]["manifest_completeness"] == 0.3


# ---------------------------------------------------------------------------
# Failure isolation
# ---------------------------------------------------------------------------


def test_failure_isolation(monkeypatch, tmp_path):
    """One source raising an exception must not poison the other source.

    claude-plugins-official succeeds (1 plugin); superpowers-marketplace
    raises during fetch. The script should still produce 1 entry and
    exit with status 0.
    """
    marketplace = _marketplace_payload(
        [
            {
                "name": "solo",
                "version": "1.0.0",
                "description": "The lone survivor",
                "author": "Anthropic",
                "source": "./plugins/solo",
            }
        ]
    )
    _install_fake_http(
        monkeypatch,
        marketplaces={
            "anthropics/claude-plugins-official": marketplace,
            "obra/superpowers-marketplace": RuntimeError("boom"),
            "affaan-m/ECC": _marketplace_payload([]),
        },
    )

    output_path = tmp_path / "plugins" / "index.json"
    rc = spo.main(["--output", str(output_path)])
    assert rc == 0

    with open(output_path, encoding="utf-8") as f:
        entries = json.load(f)
    assert len(entries) == 1
    assert entries[0]["name"] == "solo"
    assert entries[0]["source"] == "claude-plugins-official"


# ---------------------------------------------------------------------------
# Zero plugins → non-zero exit
# ---------------------------------------------------------------------------


def test_zero_plugins_exits_nonzero(monkeypatch, tmp_path):
    """If both sources fail (or return empty + fail), main() must return non-zero."""
    _install_fake_http(
        monkeypatch,
        marketplaces={
            # First source: HTTP failure
            "anthropics/claude-plugins-official": None,
            # Second source: raises
            "obra/superpowers-marketplace": RuntimeError("boom"),
            "affaan-m/ECC": None,
        },
    )

    output_path = tmp_path / "plugins" / "index.json"
    rc = spo.main(["--output", str(output_path)])
    assert rc != 0
    # On zero-plugins the script logs and bails before save_index → no file.
    assert not output_path.exists()


# ---------------------------------------------------------------------------
# command_paths / agent_paths bundle emission (so official plugins' commands &
# agents flow into the work tree via the catalog path, not just cospowers)
# ---------------------------------------------------------------------------


class _FakeLayout:
    """Minimal stand-in for PluginLayout (the fields _build_bundle_from_layout
    reads). Mirrors what detect_plugin_layout returns for a real plugin."""

    def __init__(
        self,
        plugin_root,
        skill_paths=None,
        command_paths=None,
        agent_paths=None,
        skills_namespaces=None,
        plugin_json_path="",
        is_marketplace_repo=False,
    ):
        self.is_plugin = True
        self.fetch_error = None
        self.plugin_root = plugin_root
        self.skill_paths = skill_paths or []
        self.command_paths = command_paths or []
        self.agent_paths = agent_paths or []
        self.skills_namespaces = skills_namespaces or []
        self.plugin_json_path = plugin_json_path
        self.hooks_count = 0
        self.hook_events = []
        self.mcp_server_names = []
        self.mcp_server_configs = {}
        self.is_marketplace_repo = is_marketplace_repo


class _FakeFetcher:
    def __init__(self, layout):
        self._layout = layout

    def detect_plugin_layout(self, repo, plugin_root, ref="HEAD"):
        return self._layout


def test_component_namespaces_helper_aligns_and_strips_md():
    paths = [
        "plugins/foo/commands/run.md",
        "plugins/foo/.commands/deep/nested.md",  # dot-dir variant + nested
    ]
    ns = spo._component_namespaces(paths, "plugins/foo", "foo")
    assert ns == ["foo:run", "foo:deep/nested"]
    assert len(ns) == len(paths)  # position-aligned


def test_namespace_prefix_prefers_skills_namespace_then_fallback():
    with_skills = _FakeLayout("plugins/foo", skills_namespaces=["realname:bar"])
    assert spo._namespace_prefix_from_layout(with_skills, "marketplace-name") == "realname"
    no_skills = _FakeLayout("plugins/baz", skills_namespaces=[])
    assert spo._namespace_prefix_from_layout(no_skills, "baz") == "baz"


def test_build_bundle_from_layout_emits_command_and_agent_paths():
    """The bundle MUST carry command_paths/agent_paths + aligned namespaces +
    the source coordinates (source_repo/source_ref/plugin_root) merge_index needs
    — field names/shape identical to the merge_index consumption contract."""
    layout = _FakeLayout(
        plugin_root="plugins/foo",
        skill_paths=["plugins/foo/skills/bar/SKILL.md"],
        skills_namespaces=["foo:bar"],
        command_paths=["plugins/foo/commands/run.md"],
        agent_paths=["plugins/foo/agents/reviewer.md"],
    )
    bundle = spo._build_bundle_from_layout(
        _FakeFetcher(layout),
        repo="anthropics/claude-plugins-official",
        plugin_root="plugins/foo",
        manifest=None,
        plugin_name="foo",
        ref="HEAD",
    )
    # path arrays present + verbatim repo-relative
    assert bundle["command_paths"] == ["plugins/foo/commands/run.md"]
    assert bundle["agent_paths"] == ["plugins/foo/agents/reviewer.md"]
    # namespaces position-aligned with paths, prefixed by the skills prefix
    assert bundle["commands_namespaces"] == ["foo:run"]
    assert bundle["agents_namespaces"] == ["foo:reviewer"]
    assert len(bundle["commands_namespaces"]) == len(bundle["command_paths"])
    assert len(bundle["agents_namespaces"]) == len(bundle["agent_paths"])
    # merge-required coordinates
    assert bundle["source_repo"] == "anthropics/claude-plugins-official"
    assert bundle["source_ref"] == "HEAD"
    assert bundle["plugin_root"] == "plugins/foo"
    # skill logic untouched
    assert bundle["skill_paths"] == ["plugins/foo/skills/bar/SKILL.md"]
    assert bundle["skills_namespaces"] == ["foo:bar"]


def test_build_bundle_from_layout_no_commands_agents_emits_empty_lists():
    """A plugin with neither commands nor agents still emits the (empty) fields
    so downstream consumers never KeyError."""
    layout = _FakeLayout(
        plugin_root="plugins/skillonly",
        skill_paths=["plugins/skillonly/skills/x/SKILL.md"],
        skills_namespaces=["skillonly:x"],
    )
    bundle = spo._build_bundle_from_layout(
        _FakeFetcher(layout),
        repo="anthropics/claude-plugins-official",
        plugin_root="plugins/skillonly",
        manifest=None,
        plugin_name="skillonly",
        ref="HEAD",
    )
    assert bundle["command_paths"] == []
    assert bundle["agent_paths"] == []
    assert bundle["commands_namespaces"] == []
    assert bundle["agents_namespaces"] == []


def test_official_command_agent_bundle_synthesizes_children_via_merge():
    """End-to-end: an official-plugin bundle (as _build_bundle_from_layout emits)
    drives merge_index to synthesize a type=command and a type=subagent child,
    each with a plugin-root-relative source_path (parity with cospowers)."""
    import merge_index  # noqa: E402

    layout = _FakeLayout(
        plugin_root="plugins/foo",
        command_paths=["plugins/foo/commands/run.md"],
        agent_paths=["plugins/foo/agents/reviewer.md"],
        skills_namespaces=["foo:ignored"],  # only used for prefix
    )
    bundle = spo._build_bundle_from_layout(
        _FakeFetcher(layout),
        repo="anthropics/claude-plugins-official",
        plugin_root="plugins/foo",
        manifest=None,
        plugin_name="foo",
        ref="HEAD",
    )
    plugin = {
        "id": "anthropic-foo", "name": "foo", "type": "plugin",
        "description": "d",
        "source_url": "https://github.com/anthropics/claude-plugins-official",
        "stars": 1, "category": "tooling", "tags": [], "tech_stack": [],
        "install": {"method": "plugin_marketplace"},
        "source": "claude-plugins-official", "last_synced": "2026-06-17",
        "final_score": 80, "bundle": bundle,
    }
    entries = [plugin]
    merge_index._apply_bundled_in_annotations(entries)

    cmd = next(e for e in entries if e.get("source") == "plugin-bundled-command")
    assert cmd["type"] == "command"
    assert cmd["bundled_in"] == "anthropic-foo"
    assert cmd["source_path"] == "commands/run.md"  # plugin-root relative
    assert cmd["install"]["path"] == "plugins/foo/commands/run.md"  # full repo-rel

    agent = next(e for e in entries if e.get("source") == "plugin-bundled-subagent")
    assert agent["type"] == "subagent"
    assert agent["source_path"] == "agents/reviewer.md"
    assert agent["install"]["files"] == ["plugins/foo/agents/reviewer.md"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
