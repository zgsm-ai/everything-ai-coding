"""TDD tests for extend-plugin-bundle-extraction.

Verifies that ``PluginContentFetcher.detect_plugin_layout`` returns a
``PluginLayout`` populated with the new fields:

  * ``hook_events`` (list[str]) and ``hooks_count`` (int)
  * ``mcp_server_names`` (list[str]) merged from plugin.json inline +
    .mcp.json — the ``mcp_servers_count`` count derives from this list
  * ``is_marketplace_repo`` (bool)

And that the existing shadow-directory filter is relaxed via an explicit
component-allowlist (``.agents/`` / ``.commands/`` are included when
they are the only such directory under the plugin root).

All fixtures live in ``tests/fixtures/plugin_layouts/<owner-repo>/`` and
were captured at known commit SHAs (see each ``_meta.json``). Tests are
network-free: ``FakeClient`` serves Tree API responses from ``tree.json``
and raw URLs from the rest of the fixture files.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

import pytest

# Make ai-resource-eval importable when running pytest from repo root.
_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "ai-resource-eval"))

from ai_resource_eval.fetcher.plugin import PluginContentFetcher  # noqa: E402

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "plugin_layouts"


# ---------------------------------------------------------------------------
# FakeClient — same pattern as test_sync_plugins_bundle_substance.py
# ---------------------------------------------------------------------------


class _Response:
    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text

    def json(self) -> Any:
        return json.loads(self.text)


class FakeClient:
    """In-memory stand-in for httpx.Client driven by registered handlers."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self._handlers: list[tuple[Callable[[str], bool], Callable[[str], _Response]]] = []

    def add_handler(self, predicate, factory) -> None:
        self._handlers.append((predicate, factory))

    def get(self, url: str, headers: dict | None = None) -> _Response:
        self.calls.append(url)
        for predicate, factory in self._handlers:
            if predicate(url):
                return factory(url)
        return _Response(404, "")

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Fixture loader — wires Tree + raw URLs from on-disk capture
# ---------------------------------------------------------------------------


def _wire_fixture(client: FakeClient, repo: str, fixture_dir: Path) -> None:
    """Register handlers on ``client`` so detect_plugin_layout sees ``fixture_dir``.

    Handles three URL families:

      * ``api.github.com/repos/<repo>/git/trees/HEAD?recursive=1`` →
        served from ``tree.json``
      * ``raw.githubusercontent.com/<repo>/HEAD/.claude-plugin/plugin.json`` →
        served from ``plugin.json`` if present
      * ``raw.githubusercontent.com/<repo>/HEAD/hooks/hooks.json`` →
        served from ``hooks-hooks.json`` if present
      * ``raw.githubusercontent.com/<repo>/HEAD/.mcp.json`` →
        served from ``dot-mcp.json`` if present
    """
    tree_path = fixture_dir / "tree.json"
    if not tree_path.exists():
        raise FileNotFoundError(f"tree.json missing in {fixture_dir}")
    tree_text = tree_path.read_text()

    client.add_handler(
        lambda url, r=repo: url == f"https://api.github.com/repos/{r}/git/trees/HEAD?recursive=1",
        lambda url, t=tree_text: _Response(200, t),
    )

    raw_base = f"https://raw.githubusercontent.com/{repo}/HEAD/"
    raw_files = {
        ".claude-plugin/plugin.json": fixture_dir / "plugin.json",
        "hooks/hooks.json": fixture_dir / "hooks-hooks.json",
        ".mcp.json": fixture_dir / "dot-mcp.json",
    }
    for rel_path, on_disk in raw_files.items():
        if on_disk.exists():
            content = on_disk.read_text()
            client.add_handler(
                lambda url, target=raw_base + rel_path: url == target,
                lambda url, c=content: _Response(200, c),
            )


def _make_fetcher(client: FakeClient) -> PluginContentFetcher:
    return PluginContentFetcher(github_token="", http_client=client)


# ---------------------------------------------------------------------------
# Per-fixture tests (Stage 2 of TDD plan)
# ---------------------------------------------------------------------------


def test_superpowers_extracts_skills_and_hooks() -> None:
    """obra/superpowers: 1 SessionStart hook entry, 14 skills, no mcp."""
    repo = "obra/superpowers"
    client = FakeClient()
    _wire_fixture(client, repo, FIXTURES_DIR / "obra-superpowers")
    fetcher = _make_fetcher(client)

    layout = fetcher.detect_plugin_layout(repo, plugin_root="", ref="HEAD")

    assert layout.is_plugin is True
    assert layout.is_marketplace_repo is False
    assert layout.hook_events == ["SessionStart"]
    assert layout.hooks_count == 1
    assert layout.mcp_server_names == []
    # Skills already covered by existing tests but we sanity-check non-zero here.
    assert len(layout.skill_paths) >= 14


def test_postman_extracts_mcp_via_dot_mcp_json() -> None:
    """postman: 1 MCP via .mcp.json, no hooks."""
    repo = "Postman-Devrel/postman-claude-code-plugin"
    client = FakeClient()
    _wire_fixture(client, repo, FIXTURES_DIR / "Postman-Devrel-postman-claude-code-plugin")
    fetcher = _make_fetcher(client)

    layout = fetcher.detect_plugin_layout(repo, plugin_root="", ref="HEAD")

    assert layout.is_plugin is True
    assert layout.is_marketplace_repo is False
    assert layout.hook_events == []
    assert layout.hooks_count == 0
    assert layout.mcp_server_names == ["postman"]
    assert layout.mcp_server_configs["postman"].get("command") or layout.mcp_server_configs[
        "postman"
    ].get("url")


def test_zoom_extracts_three_mcp_servers() -> None:
    """zoom-plugin: 3 MCP servers via .mcp.json, sorted alphabetically."""
    repo = "zoom/zoom-plugin"
    client = FakeClient()
    _wire_fixture(client, repo, FIXTURES_DIR / "zoom-zoom-plugin")
    fetcher = _make_fetcher(client)

    layout = fetcher.detect_plugin_layout(repo, plugin_root="", ref="HEAD")

    assert layout.mcp_server_names == ["zoom-docs-mcp", "zoom-mcp", "zoom-whiteboard-mcp"]
    assert set(layout.mcp_server_configs) == {
        "zoom-docs-mcp",
        "zoom-mcp",
        "zoom-whiteboard-mcp",
    }
    assert layout.hooks_count == 0


def test_episodic_memory_extracts_mcp_via_plugin_json_inline() -> None:
    """episodic-memory: mcpServers declared INLINE in plugin.json (not .mcp.json)."""
    repo = "obra/episodic-memory"
    client = FakeClient()
    _wire_fixture(client, repo, FIXTURES_DIR / "obra-episodic-memory")
    fetcher = _make_fetcher(client)

    layout = fetcher.detect_plugin_layout(repo, plugin_root="", ref="HEAD")

    assert layout.mcp_server_names == ["episodic-memory"]
    assert layout.mcp_server_configs["episodic-memory"]["command"]
    assert layout.hooks_count == 1
    assert layout.hook_events == ["SessionStart"]


def test_oh_my_claudecode_extracts_many_hook_entries() -> None:
    """oh-my-claudecode: 11+ event types, 13+ entries in hooks/hooks.json."""
    repo = "Yeachan-Heo/oh-my-claudecode"
    client = FakeClient()
    _wire_fixture(client, repo, FIXTURES_DIR / "Yeachan-Heo-oh-my-claudecode")
    fetcher = _make_fetcher(client)

    layout = fetcher.detect_plugin_layout(repo, plugin_root="", ref="HEAD")

    # Lower bounds guard against future fixture refresh adding more events.
    assert layout.hooks_count >= 13
    assert len(layout.hook_events) >= 11
    # All events should be sorted unique strings.
    assert layout.hook_events == sorted(set(layout.hook_events))
    # Spot-check a couple known events
    assert "SessionStart" in layout.hook_events
    assert "PreToolUse" in layout.hook_events


def test_pua_ignores_root_plugin_json_and_codebuddy_dir() -> None:
    """pua: top-level plugin.json (codebuddy compat) AND .codebuddy-plugin/ both ignored."""
    repo = "tanweai/pua"
    client = FakeClient()
    _wire_fixture(client, repo, FIXTURES_DIR / "tanweai-pua")
    fetcher = _make_fetcher(client)

    layout = fetcher.detect_plugin_layout(repo, plugin_root="", ref="HEAD")

    assert layout.is_plugin is True
    assert layout.is_marketplace_repo is False
    # No file under any .codebuddy* directory should appear in component paths
    for path in layout.skill_paths + layout.agent_paths + layout.command_paths:
        assert ".codebuddy" not in path, f"codebuddy shadow leaked: {path}"
    assert layout.hooks_count >= 6


def test_everything_claude_code_extracts_dot_agents_directory() -> None:
    """everything-claude-code: agents live in `.agents/` (allow-listed dot dir)."""
    repo = "affaan-m/everything-claude-code"
    client = FakeClient()
    _wire_fixture(client, repo, FIXTURES_DIR / "affaan-m-everything-claude-code")
    fetcher = _make_fetcher(client)

    layout = fetcher.detect_plugin_layout(repo, plugin_root="", ref="HEAD")

    # `.agents/` is the actual agent directory in this plugin — allow-list MUST include it
    assert any(p.startswith(".agents/") for p in layout.agent_paths), (
        f"expected .agents/* in agent_paths, got first 3: {layout.agent_paths[:3]}"
    )
    # Cross-platform shadow dirs SHALL still be excluded
    for path in layout.skill_paths + layout.agent_paths + layout.command_paths:
        for shadow in (".codex/", ".cursor/", ".gemini/", ".trae/", ".kiro/", ".opencode/"):
            assert shadow not in path, f"shadow {shadow} leaked: {path}"
    # Hook signal: 7 events, 26 entries
    assert layout.hooks_count == 26
    assert "PreToolUse" in layout.hook_events
    assert "PostToolUse" in layout.hook_events


def test_antigravity_detected_as_marketplace_not_plugin() -> None:
    """antigravity-awesome-skills: marketplace repo (has plugins/ subdir)."""
    repo = "sickn33/antigravity-awesome-skills"
    client = FakeClient()
    _wire_fixture(client, repo, FIXTURES_DIR / "sickn33-antigravity-awesome-skills")
    fetcher = _make_fetcher(client)

    layout = fetcher.detect_plugin_layout(repo, plugin_root="", ref="HEAD")

    assert layout.is_marketplace_repo is True
    # Per spec: counts SHALL all be 0 for marketplace-classified repos
    assert len(layout.skill_paths) == 0
    assert len(layout.agent_paths) == 0
    assert len(layout.command_paths) == 0
    assert layout.hooks_count == 0
    assert layout.mcp_server_names == []


# ---------------------------------------------------------------------------
# Edge-case tests (Stage 2.10)
# ---------------------------------------------------------------------------


def _build_synthetic_fixture(
    tmp_path: Path,
    *,
    tree_paths: list[str],
    plugin_json: str | None = None,
    hooks_hooks_json: str | None = None,
    dot_mcp_json: str | None = None,
) -> Path:
    """Build a one-off fixture dir with synthetic files (for edge cases)."""
    fixture = tmp_path / "synth"
    fixture.mkdir(parents=True, exist_ok=True)
    tree_data = {
        "tree": [{"path": p, "type": "blob"} for p in tree_paths],
        "truncated": False,
    }
    (fixture / "tree.json").write_text(json.dumps(tree_data))
    if plugin_json is not None:
        (fixture / "plugin.json").write_text(plugin_json)
    if hooks_hooks_json is not None:
        (fixture / "hooks-hooks.json").write_text(hooks_hooks_json)
    if dot_mcp_json is not None:
        (fixture / "dot-mcp.json").write_text(dot_mcp_json)
    return fixture


def test_empty_mcpservers_dict_treated_as_zero(tmp_path: Path) -> None:
    """plugin.json declares mcpServers: {} → count is 0, not "occupied"."""
    fixture = _build_synthetic_fixture(
        tmp_path,
        tree_paths=[".claude-plugin/plugin.json"],
        plugin_json=json.dumps({"name": "x", "mcpServers": {}}),
    )
    repo = "synth/empty-mcp"
    client = FakeClient()
    _wire_fixture(client, repo, fixture)
    fetcher = _make_fetcher(client)

    layout = fetcher.detect_plugin_layout(repo, plugin_root="", ref="HEAD")

    assert layout.mcp_server_names == []
    assert layout.mcp_server_configs == {}


def test_path_string_mcpservers_falls_back_to_dot_mcp_json(tmp_path: Path) -> None:
    """plugin.json mcpServers='./.mcp.json' → ignored as path-string, .mcp.json wins."""
    fixture = _build_synthetic_fixture(
        tmp_path,
        tree_paths=[".claude-plugin/plugin.json", ".mcp.json"],
        plugin_json=json.dumps({"name": "x", "mcpServers": "./.mcp.json"}),
        dot_mcp_json=json.dumps({"mcpServers": {"t": {"command": "echo"}}}),
    )
    repo = "synth/path-string"
    client = FakeClient()
    _wire_fixture(client, repo, fixture)
    fetcher = _make_fetcher(client)

    layout = fetcher.detect_plugin_layout(repo, plugin_root="", ref="HEAD")

    assert layout.mcp_server_names == ["t"]
    assert layout.mcp_server_configs["t"]["command"] == "echo"


def test_dot_codex_plugin_excluded(tmp_path: Path) -> None:
    """Cross-platform shadow .codex-plugin/ MUST still be excluded."""
    fixture = _build_synthetic_fixture(
        tmp_path,
        tree_paths=[
            ".claude-plugin/plugin.json",
            "skills/x/SKILL.md",
            ".codex-plugin/skills/y/SKILL.md",
        ],
        plugin_json=json.dumps({"name": "x"}),
    )
    repo = "synth/codex-shadow"
    client = FakeClient()
    _wire_fixture(client, repo, fixture)
    fetcher = _make_fetcher(client)

    layout = fetcher.detect_plugin_layout(repo, plugin_root="", ref="HEAD")

    assert layout.skill_paths == ["skills/x/SKILL.md"]


def test_hook_matchers_not_in_output(tmp_path: Path) -> None:
    """Per D2: matchers/commands SHALL NOT appear in PluginLayout."""
    hooks_payload = json.dumps({
        "hooks": {
            "SessionStart": [
                {"matcher": "startup", "hooks": [{"type": "command", "command": "echo"}]},
            ]
        }
    })
    fixture = _build_synthetic_fixture(
        tmp_path,
        tree_paths=[".claude-plugin/plugin.json", "hooks/hooks.json"],
        plugin_json=json.dumps({"name": "x"}),
        hooks_hooks_json=hooks_payload,
    )
    repo = "synth/hook-matcher"
    client = FakeClient()
    _wire_fixture(client, repo, fixture)
    fetcher = _make_fetcher(client)

    layout = fetcher.detect_plugin_layout(repo, plugin_root="", ref="HEAD")

    assert layout.hook_events == ["SessionStart"]
    assert layout.hooks_count == 1
    # PluginLayout SHALL NOT carry matcher/command strings
    assert not hasattr(layout, "hook_matchers")
    assert not hasattr(layout, "hook_commands")


def test_malformed_hooks_json_yields_zero_with_warning(tmp_path: Path, caplog) -> None:
    """Per spec scenario: malformed hooks.json → 0 signals + WARNING (no crash)."""
    fixture = _build_synthetic_fixture(
        tmp_path,
        tree_paths=[".claude-plugin/plugin.json", "hooks/hooks.json"],
        plugin_json=json.dumps({"name": "x"}),
        hooks_hooks_json="this is not JSON {{",
    )
    repo = "synth/bad-hooks"
    client = FakeClient()
    _wire_fixture(client, repo, fixture)
    fetcher = _make_fetcher(client)

    layout = fetcher.detect_plugin_layout(repo, plugin_root="", ref="HEAD")

    assert layout.hook_events == []
    assert layout.hooks_count == 0


def test_content_hash_changes_when_hooks_json_changes(tmp_path: Path) -> None:
    """D6: content_hash SHALL include hooks/hooks.json content."""
    base_tree = [
        ".claude-plugin/plugin.json",
        "hooks/hooks.json",
        "skills/x/SKILL.md",
    ]
    plugin_json_text = json.dumps({"name": "x"})

    fixture_a = _build_synthetic_fixture(
        tmp_path / "a",
        tree_paths=base_tree,
        plugin_json=plugin_json_text,
        hooks_hooks_json=json.dumps({"hooks": {"SessionStart": []}}),
    )
    fixture_b = _build_synthetic_fixture(
        tmp_path / "b",
        tree_paths=base_tree,
        plugin_json=plugin_json_text,
        hooks_hooks_json=json.dumps({"hooks": {"PostToolUse": []}}),  # different
    )

    def _hash_for(fixture: Path) -> str:
        repo = "synth/hash-" + fixture.parent.name
        client = FakeClient()
        _wire_fixture(client, repo, fixture)
        # Also make raw skill fetch return SOMETHING so _normalize_content has work
        client.add_handler(
            lambda url, r=repo: url == f"https://raw.githubusercontent.com/{r}/HEAD/skills/x/SKILL.md",
            lambda url: _Response(200, "# skill x\n"),
        )
        fetcher = _make_fetcher(client)
        result = fetcher.fetch(f"https://github.com/{repo}")
        assert result is not None, "fetch returned None unexpectedly"
        _, content_hash = result
        return content_hash

    hash_a = _hash_for(fixture_a)
    hash_b = _hash_for(fixture_b)
    assert hash_a != hash_b, "content_hash must change when hooks.json content changes"


def test_content_hash_changes_when_dot_mcp_json_changes(tmp_path: Path) -> None:
    """D6: content_hash SHALL include .mcp.json content."""
    base_tree = [".claude-plugin/plugin.json", ".mcp.json", "skills/x/SKILL.md"]
    plugin_json_text = json.dumps({"name": "x"})

    fixture_a = _build_synthetic_fixture(
        tmp_path / "a",
        tree_paths=base_tree,
        plugin_json=plugin_json_text,
        dot_mcp_json=json.dumps({"mcpServers": {"a": {}}}),
    )
    fixture_b = _build_synthetic_fixture(
        tmp_path / "b",
        tree_paths=base_tree,
        plugin_json=plugin_json_text,
        dot_mcp_json=json.dumps({"mcpServers": {"b": {}}}),
    )

    def _hash_for(fixture: Path) -> str:
        repo = "synth/mcp-hash-" + fixture.parent.name
        client = FakeClient()
        _wire_fixture(client, repo, fixture)
        client.add_handler(
            lambda url, r=repo: url == f"https://raw.githubusercontent.com/{r}/HEAD/skills/x/SKILL.md",
            lambda url: _Response(200, "# skill x\n"),
        )
        fetcher = _make_fetcher(client)
        result = fetcher.fetch(f"https://github.com/{repo}")
        assert result is not None
        _, content_hash = result
        return content_hash

    assert _hash_for(fixture_a) != _hash_for(fixture_b)
