"""Integration tests for Batch D — sync stage bundle field population.

These tests verify that ``scripts/sync_plugins_official.py`` and
``scripts/sync_plugins_dev.py`` correctly invoke
``PluginContentFetcher.detect_plugin_layout`` to fill each plugin entry's
``bundle.skills_count`` / ``agents_count`` / ``commands_count`` /
``skills_namespaces`` with REAL values derived from the upstream repo's
file tree (rather than zero placeholders).

Coverage:

  * Layout detector wiring → entries gain non-zero bundle fields and
    realistic ``skills_namespaces``.
  * Tree cache reuse → one Tree API call per ``(repo, ref)`` regardless
    of how many plugins the marketplace lists.
  * Failure path — Tree API error / non-plugin shell → entry bundle
    stays at the zero placeholder ``{0,0,0,[]}`` and sync continues.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Iterable

import pytest

# Make scripts/ importable.
sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "scripts"),
)

import sync_plugins_dev as spd  # noqa: E402
import sync_plugins_official as spo  # noqa: E402

from ai_resource_eval.fetcher.plugin import PluginContentFetcher  # noqa: E402


# ---------------------------------------------------------------------------
# FakeClient — same shape as ai-resource-eval/tests/test_plugin_content_fetcher
# ---------------------------------------------------------------------------


class _Response:
    def __init__(
        self,
        status_code: int,
        text: str = "",
        json_payload: Any = None,
    ) -> None:
        self.status_code = status_code
        self.text = text
        self._json = json_payload

    def json(self) -> Any:
        if self._json is not None:
            return self._json
        return json.loads(self.text)


class FakeClient:
    """Stand-in for httpx.Client. Records every URL fetched."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self._handlers: list[tuple[Any, Any]] = []

    def add_handler(self, predicate, response_factory) -> None:
        self._handlers.append((predicate, response_factory))

    def get(self, url: str, headers: dict | None = None) -> _Response:
        self.calls.append(url)
        for predicate, factory in self._handlers:
            if predicate(url):
                return factory(url)
        return _Response(404, "")

    def close(self) -> None:
        pass


def _tree_blobs(paths: Iterable[str]) -> dict:
    return {
        "tree": [{"path": p, "type": "blob"} for p in paths],
        "truncated": False,
    }


def _tree_url(repo: str, ref: str = "HEAD") -> str:
    return f"https://api.github.com/repos/{repo}/git/trees/{ref}?recursive=1"


# ---------------------------------------------------------------------------
# Helpers shared with existing sync tests
# ---------------------------------------------------------------------------


def _marketplace_payload(plugins: list[dict]) -> dict:
    return {"name": "test-marketplace", "plugins": plugins}


def _install_official_fake_http(
    monkeypatch: pytest.MonkeyPatch,
    *,
    marketplaces: dict[str, dict | None],
):
    """Install fake ``_http_get`` / ``_http_get_json`` for the official sync.

    Mirrors the pattern from ``test_sync_plugins_official.py``.
    """

    def fake_http_get(url: str, timeout: int = 30):
        for repo_slug, payload in marketplaces.items():
            if f"/{repo_slug}/" in url and url.endswith("marketplace.json"):
                if payload is None:
                    return None
                return json.dumps(payload).encode("utf-8")
        return None

    def fake_http_get_json(url: str, timeout: int = 30):
        # No per-plugin manifest probes are needed for these tests; the
        # synthetic-manifest fallback inside _entry_from_plugin handles
        # manifest_completeness from the marketplace entry itself.
        return None

    monkeypatch.setattr(spo, "_http_get", fake_http_get)
    monkeypatch.setattr(spo, "_http_get_json", fake_http_get_json)


# ---------------------------------------------------------------------------
# Tests for sync_plugins_official.py
# ---------------------------------------------------------------------------


def _wire_official_marketplace_tree(client: FakeClient, repo: str) -> None:
    """Register a Tree API response simulating two plugins under the same monorepo.

    ``plugins/foo`` ships one SKILL plus one command; ``plugins/baz`` ships
    one agent. ``plugins/legacy`` is a README-only shell (no plugin.json).
    """
    paths = [
        # plugin foo: 1 SKILL + 1 command
        "plugins/foo/.claude-plugin/plugin.json",
        "plugins/foo/skills/bar/SKILL.md",
        "plugins/foo/commands/run.md",
        # plugin baz: 1 agent (no skills)
        "plugins/baz/.claude-plugin/plugin.json",
        "plugins/baz/agents/x.md",
        # legacy: README-only shell — no plugin.json marker
        "plugins/legacy/README.md",
    ]
    client.add_handler(
        lambda url: url == _tree_url(repo),
        lambda url: _Response(200, json_payload=_tree_blobs(paths)),
    )


def test_official_sync_fills_bundle_from_layout(monkeypatch, tmp_path):
    """Layout detector populates real skill/agent/command counts and namespaces."""
    marketplace = _marketplace_payload(
        [
            {
                "name": "foo",
                "version": "1.0.0",
                "description": "Foo plugin",
                "author": "Anthropic",
                "source": "./plugins/foo",
            },
            {
                "name": "baz",
                "version": "0.1.0",
                "description": "Baz plugin",
                "author": "Anthropic",
                "source": "./plugins/baz",
            },
            {
                "name": "legacy",
                "version": "0.0.1",
                "description": "Legacy README-only shell",
                "author": "Anthropic",
                "source": "./plugins/legacy",
            },
        ]
    )
    _install_official_fake_http(
        monkeypatch,
        marketplaces={
            "anthropics/claude-plugins-official": marketplace,
            # Empty second source — must still allow main() to write file.
            "obra/superpowers-marketplace": _marketplace_payload([]),
        },
    )

    fake_client = FakeClient()
    _wire_official_marketplace_tree(fake_client, "anthropics/claude-plugins-official")

    # Inject a fetcher built on the FakeClient. We do this by patching the
    # PluginContentFetcher symbol that sync_plugins_official imports so the
    # constructor (called inside main()) returns a fetcher with our fake
    # transport.
    def _factory():
        return PluginContentFetcher(
            github_token="fake-token",
            http_client=fake_client,
        )

    monkeypatch.setattr(spo, "PluginContentFetcher", _factory)
    # Disable repo metadata fetch — it would otherwise hit the real API.
    monkeypatch.setattr(spo, "_fetch_repo_meta", lambda url: {})

    output_path = tmp_path / "plugins" / "index.json"
    rc = spo.main(["--output", str(output_path)])
    assert rc == 0

    with open(output_path, encoding="utf-8") as f:
        entries = json.load(f)

    by_id = {e["id"]: e for e in entries}

    foo = by_id["anthropic-foo"]
    assert foo["bundle"]["skills_count"] == 1
    assert foo["bundle"]["commands_count"] == 1
    assert foo["bundle"]["agents_count"] == 0
    assert foo["bundle"]["skills_namespaces"] == ["foo:bar"]

    baz = by_id["anthropic-baz"]
    assert baz["bundle"]["skills_count"] == 0
    assert baz["bundle"]["agents_count"] == 1
    assert baz["bundle"]["commands_count"] == 0
    assert baz["bundle"]["skills_namespaces"] == []

    # Legacy shell — no plugin.json marker → bundle stays at zeros.
    legacy = by_id["anthropic-legacy"]
    assert legacy["bundle"]["skills_count"] == 0
    assert legacy["bundle"]["agents_count"] == 0
    assert legacy["bundle"]["commands_count"] == 0
    assert legacy["bundle"]["skills_namespaces"] == []


def test_official_sync_tree_cache_one_call_per_marketplace(monkeypatch, tmp_path):
    """Tree API for the marketplace repo is called exactly once across plugins."""
    marketplace = _marketplace_payload(
        [
            {
                "name": "foo",
                "version": "1.0.0",
                "description": "Foo",
                "author": "Anthropic",
                "source": "./plugins/foo",
            },
            {
                "name": "baz",
                "version": "1.0.0",
                "description": "Baz",
                "author": "Anthropic",
                "source": "./plugins/baz",
            },
        ]
    )
    _install_official_fake_http(
        monkeypatch,
        marketplaces={
            "anthropics/claude-plugins-official": marketplace,
            "obra/superpowers-marketplace": _marketplace_payload([]),
        },
    )

    fake_client = FakeClient()
    _wire_official_marketplace_tree(fake_client, "anthropics/claude-plugins-official")

    def _factory():
        return PluginContentFetcher(
            github_token="fake-token",
            http_client=fake_client,
        )

    monkeypatch.setattr(spo, "PluginContentFetcher", _factory)
    monkeypatch.setattr(spo, "_fetch_repo_meta", lambda url: {})

    output_path = tmp_path / "plugins" / "index.json"
    rc = spo.main(["--output", str(output_path)])
    assert rc == 0

    tree_calls = [
        u
        for u in fake_client.calls
        if u == _tree_url("anthropics/claude-plugins-official")
    ]
    assert len(tree_calls) == 1, (
        "Tree API should be called exactly once for the marketplace monorepo "
        f"(processed 2 plugins). Got {len(tree_calls)} calls: {tree_calls}"
    )


def test_official_sync_failure_path_uses_zero_bundle(monkeypatch, tmp_path):
    """Tree API failure → entry retains the {0,0,0,[]} placeholder."""
    marketplace = _marketplace_payload(
        [
            {
                "name": "foo",
                "version": "1.0.0",
                "description": "Foo",
                "author": "Anthropic",
                "source": "./plugins/foo",
            }
        ]
    )
    _install_official_fake_http(
        monkeypatch,
        marketplaces={
            "anthropics/claude-plugins-official": marketplace,
            "obra/superpowers-marketplace": _marketplace_payload([]),
        },
    )

    fake_client = FakeClient()
    # Tree handler returns 500 → fetcher logs warning, walks empty tree,
    # detect_plugin_layout returns is_plugin=False.
    fake_client.add_handler(
        lambda url: url == _tree_url("anthropics/claude-plugins-official"),
        lambda url: _Response(500, "boom"),
    )

    def _factory():
        return PluginContentFetcher(
            github_token="fake-token",
            http_client=fake_client,
        )

    monkeypatch.setattr(spo, "PluginContentFetcher", _factory)
    monkeypatch.setattr(spo, "_fetch_repo_meta", lambda url: {})

    output_path = tmp_path / "plugins" / "index.json"
    rc = spo.main(["--output", str(output_path)])
    assert rc == 0

    with open(output_path, encoding="utf-8") as f:
        entries = json.load(f)
    assert len(entries) == 1
    foo = entries[0]
    # Tree API failed → no manifest fetched → zero bundle.
    assert foo["bundle"] == {
        "skills_count": 0,
        "commands_count": 0,
        "agents_count": 0,
        "mcp_servers_count": 0,
        "skills_namespaces": [],
        "hooks_count": 0,
        "hook_events": [],
        "mcp_server_names": [],
        "mcp_server_configs": {},
        "is_marketplace_repo": False,
    }


# ---------------------------------------------------------------------------
# Tests for sync_plugins_dev.py
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _relax_min_stars_for_tests(monkeypatch):
    """Production threshold MIN_STARS=5000 would filter out all fixture data."""
    monkeypatch.setattr(spd, "MIN_STARS", 5)


def _make_dev_plugin(
    name: str,
    *,
    git_url: str,
    namespace: str = "community",
    stars: int = 100,
    skills: list[str] | None = None,
) -> dict:
    return {
        "id": f"{namespace}::{name}",
        "name": name,
        "namespace": namespace,
        "description": "A test plugin",
        "version": "1.0.0",
        "author": "tester",
        "stars": stars,
        "gitUrl": git_url,
        "keywords": [],
        "category": "developer-tools",
        "skills": skills or [],
    }


def _api_response(plugins: list[dict], *, limit: int = 100) -> dict:
    return {
        "plugins": plugins,
        "total": len(plugins),
        "limit": limit,
        "offset": 0,
    }


def _install_dev_paged_http(monkeypatch: pytest.MonkeyPatch, responses: list[dict]):
    pending = list(responses)

    def fake_get_json(url: str, timeout: int = 30):
        if not pending:
            return _api_response([], limit=100)
        return pending.pop(0)

    monkeypatch.setattr(spd, "_http_get_json", fake_get_json)
    monkeypatch.setattr(spd, "_write_page_cache", lambda *a, **kw: None)


def test_dev_sync_fills_bundle_from_layout(monkeypatch, tmp_path):
    """Dev sync: layout detector overrides API skills hint with real counts."""
    repo = "acme/shaped"
    plugin = _make_dev_plugin(
        "shaped",
        git_url=f"https://github.com/{repo}",
        namespace="acme",
        # API hint claims one stale skill name; real tree has two SKILL files
        # plus one command. The sync must trust the layout detector.
        skills=["stale-hint"],
    )
    _install_dev_paged_http(monkeypatch, [_api_response([plugin], limit=100)])

    fake_client = FakeClient()
    paths = [
        ".claude-plugin/plugin.json",
        "skills/alpha/SKILL.md",
        "skills/beta/SKILL.md",
        "commands/build.md",
    ]
    fake_client.add_handler(
        lambda url: url == _tree_url(repo),
        lambda url: _Response(200, json_payload=_tree_blobs(paths)),
    )
    # Repo-root plugin: the fetcher reads plugin.json to derive its name.
    fake_client.add_handler(
        lambda url: url
        == f"https://raw.githubusercontent.com/{repo}/HEAD/.claude-plugin/plugin.json",
        lambda url: _Response(200, json.dumps({"name": "shaped"})),
    )

    def _factory():
        return PluginContentFetcher(
            github_token="fake-token",
            http_client=fake_client,
        )

    monkeypatch.setattr(spd, "PluginContentFetcher", _factory)

    output_path = tmp_path / "plugins" / "index.json"
    rc = spd.main(["--output", str(output_path)])
    assert rc == 0

    with open(output_path, encoding="utf-8") as f:
        entries = json.load(f)
    assert len(entries) == 1
    entry = entries[0]
    bundle = entry["bundle"]
    assert bundle["skills_count"] == 2
    assert bundle["commands_count"] == 1
    assert bundle["agents_count"] == 0
    # Layout detector wins over the API hint.
    assert sorted(bundle["skills_namespaces"]) == [
        "shaped:alpha",
        "shaped:beta",
    ]
    assert "shaped:stale-hint" not in bundle["skills_namespaces"]


def test_dev_sync_falls_back_to_api_when_no_plugin_json(monkeypatch, tmp_path):
    """No plugin.json at the repo root → trust the API ``skills`` hint."""
    repo = "acme/legacy"
    plugin = _make_dev_plugin(
        "legacy",
        git_url=f"https://github.com/{repo}",
        namespace="acme",
        skills=["one", "two"],
    )
    _install_dev_paged_http(monkeypatch, [_api_response([plugin], limit=100)])

    fake_client = FakeClient()
    # README-only repo: no plugin.json marker.
    fake_client.add_handler(
        lambda url: url == _tree_url(repo),
        lambda url: _Response(200, json_payload=_tree_blobs(["README.md"])),
    )

    def _factory():
        return PluginContentFetcher(
            github_token="fake-token",
            http_client=fake_client,
        )

    monkeypatch.setattr(spd, "PluginContentFetcher", _factory)

    output_path = tmp_path / "plugins" / "index.json"
    rc = spd.main(["--output", str(output_path)])
    assert rc == 0

    with open(output_path, encoding="utf-8") as f:
        entries = json.load(f)
    assert len(entries) == 1
    bundle = entries[0]["bundle"]
    # is_plugin=False → fallback to API skills hint.
    assert bundle["skills_count"] == 2
    assert sorted(bundle["skills_namespaces"]) == ["legacy:one", "legacy:two"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
