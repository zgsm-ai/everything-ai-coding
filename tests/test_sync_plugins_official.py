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
    """The ECC marketplace source produces an installable ecc plugin entry."""
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

    assert len(entries) == 1
    ecc = entries[0]
    assert ecc["id"] == "ecc-ecc"
    assert ecc["name"] == "ecc"
    assert ecc["source"] == "everything-claude-code"
    assert ecc["source_priority"] == 900
    assert ecc["source_url"] == "https://github.com/affaan-m/ECC/tree/main/"
    assert ecc["install"]["plugin_name"] == "ecc"
    assert ecc["install"]["marketplace_repo"] == "affaan-m/ECC"


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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
