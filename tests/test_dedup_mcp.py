"""Tests for §4 — MCP cross-source dedup + rules cross-repo dedup.

Covers:

- mcp_identity_key() strict matching rules
- deduplicate() type-aware Pass 1 collapse for mcp entries
- merge_index sidecar loading (mcp_registry_index.json, windsurfrules_index.json)
- rules cross-repo dedup behavior (no identity_key — id-based only)
"""

import json
import os
import sys
import tempfile
import unittest
import unittest.mock

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import merge_index  # noqa: E402
from utils import (  # noqa: E402
    deduplicate,
    mcp_identity_key,
    source_priority,
)


def _mcp_entry(
    id,
    source_url,
    name="Test MCP",
    extra: dict | None = None,
):
    e = {
        "id": id,
        "name": name,
        "type": "mcp",
        "description": "test mcp entry",
        "source_url": source_url,
        "stars": 0,
        "category": "tooling",
        "tags": [],
        "tech_stack": [],
        "install": {"method": "manual"},
        "source": "test",
        "last_synced": "2026-05-04",
    }
    if extra:
        e.update(extra)
    return e


def _rule_entry(id, source_url, name="Test Rule"):
    return {
        "id": id,
        "name": name,
        "type": "rule",
        "description": "test rule",
        "source_url": source_url,
        "stars": None,
        "category": "tooling",
        "tags": [],
        "tech_stack": [],
        "install": {"method": "download_file"},
        "source": "test",
        "last_synced": "2026-05-04",
    }


# ---------------------------------------------------------------------------
# mcp_identity_key — strict matching rules
# ---------------------------------------------------------------------------


class TestMcpIdentityKey(unittest.TestCase):
    def test_registry_io_github_to_github_key(self):
        # Registry io.github.<owner>/<repo> identity is repo-root scoped.
        e = _mcp_entry(
            "foo-bar",
            "https://registry.modelcontextprotocol.io/v0/servers/io.github.foo%2Fbar",
        )
        self.assertEqual(mcp_identity_key(e), ("github", "foo/bar", ""))

    def test_registry_reverse_dns_keeps_independent_registry_key(self):
        e = _mcp_entry(
            "ms-azure",
            "https://registry.modelcontextprotocol.io/v0/servers/com.microsoft%2Fazure",
        )
        self.assertEqual(
            mcp_identity_key(e),
            ("registry", "com.microsoft/azure", ""),
        )

    def test_github_url_to_github_key(self):
        e = _mcp_entry("ms-pw", "https://github.com/microsoft/playwright-mcp")
        self.assertEqual(
            mcp_identity_key(e),
            ("github", "microsoft/playwright-mcp", ""),
        )

    def test_monorepo_subpaths_get_distinct_keys(self):
        """Sibling sub-paths in the same monorepo MUST get distinct keys so
        Pass 1 doesn't collapse them. Without sub-path, fetch / git would
        collide on ('github', 'modelcontextprotocol/servers').
        """
        fetch = _mcp_entry(
            "mcp-fetch",
            "https://github.com/modelcontextprotocol/servers/tree/main/src/fetch",
        )
        git = _mcp_entry(
            "mcp-git",
            "https://github.com/modelcontextprotocol/servers/tree/main/src/git",
        )
        k_fetch = mcp_identity_key(fetch)
        k_git = mcp_identity_key(git)
        self.assertEqual(
            k_fetch, ("github", "modelcontextprotocol/servers", "src/fetch")
        )
        self.assertEqual(
            k_git, ("github", "modelcontextprotocol/servers", "src/git")
        )
        self.assertNotEqual(k_fetch, k_git)

    def test_registry_io_github_collapses_with_monorepo_root_only(self):
        """Registry io.github.<owner>/<repo> maps to the repo ROOT key
        (sub_path=''). It MUST NOT share a key with any specific monorepo
        sub-path entry.
        """
        registry = _mcp_entry(
            "mcp-servers-registry",
            "https://registry.modelcontextprotocol.io/v0/servers/io.github.modelcontextprotocol%2Fservers",
        )
        fetch = _mcp_entry(
            "mcp-fetch",
            "https://github.com/modelcontextprotocol/servers/tree/main/src/fetch",
        )
        self.assertNotEqual(mcp_identity_key(registry), mcp_identity_key(fetch))
        # Registry resolves to the repo root.
        self.assertEqual(
            mcp_identity_key(registry),
            ("github", "modelcontextprotocol/servers", ""),
        )

    def test_non_mcp_entry_returns_none(self):
        e = _mcp_entry("x", "https://github.com/foo/bar")
        e["type"] = "skill"
        self.assertIsNone(mcp_identity_key(e))

    def test_empty_source_url_returns_none(self):
        e = _mcp_entry("x", "")
        self.assertIsNone(mcp_identity_key(e))

    def test_registry_url_priority_900(self):
        # Sanity-check the source_priority extension for §4.3.
        url = (
            "https://registry.modelcontextprotocol.io/v0/servers/io.github.foo%2Fbar"
        )
        self.assertEqual(source_priority(url), 900)


# ---------------------------------------------------------------------------
# deduplicate() — mcp 4 scenarios
# ---------------------------------------------------------------------------


class TestMcpCrossSourceDedup(unittest.TestCase):
    def test_registry_only_kept(self):
        """§4.5 scenario 1: only a registry entry, no GitHub sibling → kept."""
        registry_entry = _mcp_entry(
            "foo-bar-registry",
            "https://registry.modelcontextprotocol.io/v0/servers/io.github.foo%2Fbar",
            extra={
                "mcp_registry_status": "active",
                "mcp_registry_published_at": "2026-04-01T00:00:00Z",
                "mcp_remotes": [{"type": "sse", "url": "https://example.com/sse"}],
            },
        )
        result = deduplicate([registry_entry])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "foo-bar-registry")
        # registry-supplied fields preserved as-is
        self.assertEqual(result[0]["mcp_registry_status"], "active")

    def test_wong2_only_kept(self):
        """§4.5 scenario 2: only a GitHub URL entry, no registry sibling → kept."""
        gh_entry = _mcp_entry("foo-bar-gh", "https://github.com/foo/bar")
        result = deduplicate([gh_entry])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "foo-bar-gh")

    def test_dual_source_collapses_keeping_github_url(self):
        """§4.5 scenario 3: github + registry same identity →

        Per spec catalog-entry-lifecycle, the GitHub URL entry survives and
        the registry-supplied fields (mcp_registry_status / _published_at /
        mcp_remotes) are merged onto it. The source / source_url stay GitHub.
        """
        gh_entry = _mcp_entry(
            "foo-bar-gh",
            "https://github.com/foo/bar",
            extra={"source": "wong2"},
        )
        registry_entry = _mcp_entry(
            "foo-bar-registry",
            "https://registry.modelcontextprotocol.io/v0/servers/io.github.foo%2Fbar",
            extra={
                "source": "registry.modelcontextprotocol.io",
                "mcp_registry_status": "active",
                "mcp_registry_published_at": "2026-04-01T00:00:00Z",
                "mcp_remotes": [{"type": "sse", "url": "https://example.com/sse"}],
            },
        )

        result = deduplicate([gh_entry, registry_entry])

        self.assertEqual(len(result), 1)
        kept = result[0]
        # Spec: GitHub URL entry wins identity collapse
        self.assertEqual(kept["id"], "foo-bar-gh")
        self.assertEqual(kept["source_url"], "https://github.com/foo/bar")
        self.assertEqual(kept["source"], "wong2")
        # Spec: registry-supplied fields are merged onto winner
        self.assertEqual(kept["mcp_registry_status"], "active")
        self.assertEqual(kept["mcp_registry_published_at"], "2026-04-01T00:00:00Z")
        self.assertEqual(
            kept["mcp_remotes"],
            [{"type": "sse", "url": "https://example.com/sse"}],
        )

    def test_dual_source_collapses_when_registry_seen_first(self):
        """Order independence: registry first, GitHub second still collapses
        to GitHub winner.
        """
        registry_entry = _mcp_entry(
            "foo-bar-registry",
            "https://registry.modelcontextprotocol.io/v0/servers/io.github.foo%2Fbar",
            extra={
                "source": "registry.modelcontextprotocol.io",
                "mcp_registry_status": "active",
            },
        )
        gh_entry = _mcp_entry(
            "foo-bar-gh",
            "https://github.com/foo/bar",
            extra={"source": "wong2"},
        )
        result = deduplicate([registry_entry, gh_entry])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "foo-bar-gh")
        self.assertEqual(result[0]["mcp_registry_status"], "active")

    def test_owner_only_fuzzy_does_not_collapse(self):
        """§4.5 scenario 4: same owner, different product →

        ``com.microsoft/azure`` (registry reverse-DNS) and
        ``microsoft/playwright-mcp`` (GitHub URL) MUST NOT collapse; their
        identity keys differ (('registry', 'com.microsoft/azure', '') vs
        ('github', 'microsoft/playwright-mcp', '')).
        """
        reg = _mcp_entry(
            "ms-azure",
            "https://registry.modelcontextprotocol.io/v0/servers/com.microsoft%2Fazure",
        )
        gh = _mcp_entry(
            "ms-pw",
            "https://github.com/microsoft/playwright-mcp",
        )
        result = deduplicate([reg, gh])
        self.assertEqual(len(result), 2)
        ids = {r["id"] for r in result}
        self.assertEqual(ids, {"ms-azure", "ms-pw"})

    def test_monorepo_subpath_entries_not_collapsed_by_registry_root(self):
        """Monorepo sub-path entries + registry root entry → all kept.

        3 distinct sub-path mcp entries under modelcontextprotocol/servers
        plus a registry entry pointing at the repo root. Sub-path entries
        have non-empty sub_path so they don't collide with each other; the
        registry root's key (sub_path='') only collides with a hypothetical
        repo-root GitHub URL — none of which exist here, so all 4 survive.
        """
        fetch = _mcp_entry(
            "mcp-fetch",
            "https://github.com/modelcontextprotocol/servers/tree/main/src/fetch",
        )
        git = _mcp_entry(
            "mcp-git",
            "https://github.com/modelcontextprotocol/servers/tree/main/src/git",
        )
        memory = _mcp_entry(
            "mcp-memory",
            "https://github.com/modelcontextprotocol/servers/tree/main/src/memory",
        )
        registry_root = _mcp_entry(
            "mcp-servers-registry",
            "https://registry.modelcontextprotocol.io/v0/servers/io.github.modelcontextprotocol%2Fservers",
        )
        result = deduplicate([fetch, git, memory, registry_root])
        self.assertEqual(len(result), 4)
        ids = {r["id"] for r in result}
        self.assertEqual(
            ids,
            {"mcp-fetch", "mcp-git", "mcp-memory", "mcp-servers-registry"},
        )


# ---------------------------------------------------------------------------
# deduplicate() — rules 3 cross-repo scenarios
# ---------------------------------------------------------------------------


class TestRulesCrossRepoDedup(unittest.TestCase):
    def test_same_slug_cross_repo_collapses_to_one(self):
        """SchneiderSam vs balqaasem same slug — collapsed; SchneiderSam wins.

        Per baseline §2, balqaasem is a fork mirror of SchneiderSam with 0
        unique entries. Keeping both copies inflates rules count without
        adding signal. The new ``rule_identity_key`` collapses them and the
        canonical-repo bump in deduplicate() picks SchneiderSam as winner.
        """
        a = _rule_entry(
            "react-windsurfrules-schneidersam",
            "https://github.com/SchneiderSam/awesome-windsurfrules/blob/main/rules/react-windsurfrules-prompt-file/.windsurfrules",
        )
        b = _rule_entry(
            "react-windsurfrules-balqaasem",
            "https://github.com/balqaasem/awesome-windsurfrules/blob/main/rules/react-windsurfrules-prompt-file/.windsurfrules",
        )
        result = deduplicate([a, b])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "react-windsurfrules-schneidersam")

    def test_same_slug_cross_repo_collapses_when_balqaasem_first(self):
        """Order independence: balqaasem first, SchneiderSam still wins."""
        a = _rule_entry(
            "react-windsurfrules-balqaasem",
            "https://github.com/balqaasem/awesome-windsurfrules/blob/main/rules/react-windsurfrules-prompt-file/.windsurfrules",
        )
        b = _rule_entry(
            "react-windsurfrules-schneidersam",
            "https://github.com/SchneiderSam/awesome-windsurfrules/blob/main/rules/react-windsurfrules-prompt-file/.windsurfrules",
        )
        result = deduplicate([a, b])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "react-windsurfrules-schneidersam")

    def test_same_repo_same_id_collapsed(self):
        """Identical id from same repo → only first kept (legacy id dedup)."""
        a = _rule_entry(
            "vue-windsurfrules-schneidersam",
            "https://github.com/SchneiderSam/awesome-windsurfrules/blob/main/rules/vue/.windsurfrules",
            name="First",
        )
        b = _rule_entry(
            "vue-windsurfrules-schneidersam",
            "https://github.com/SchneiderSam/awesome-windsurfrules/blob/main/rules/vue/.windsurfrules",
            name="Second",
        )
        result = deduplicate([a, b])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "First")

    def test_different_slug_different_repo_both_kept(self):
        """Different slugs across repos → both kept."""
        a = _rule_entry(
            "react-windsurfrules-schneidersam",
            "https://github.com/SchneiderSam/awesome-windsurfrules/blob/main/rules/react/.windsurfrules",
        )
        b = _rule_entry(
            "vue-windsurfrules-balqaasem",
            "https://github.com/balqaasem/awesome-windsurfrules/blob/main/rules/vue/.windsurfrules",
        )
        result = deduplicate([a, b])
        self.assertEqual(len(result), 2)

    def test_other_rule_sources_unaffected(self):
        """Rules from non-windsurfrules sources are NOT routed through
        rule_identity_key — they keep legacy id-based dedup behavior.
        """
        cursor_rule = _rule_entry(
            "react-cursorrules",
            "https://github.com/PatrickJS/awesome-cursorrules/blob/main/rules/react-typescript/.cursorrules",
        )
        optimized_rule = _rule_entry(
            "react-rules-2.1-optimized",
            "https://github.com/some-org/rules-2.1-optimized/blob/main/rules/react.md",
        )
        result = deduplicate([cursor_rule, optimized_rule])
        self.assertEqual(len(result), 2)
        ids = {r["id"] for r in result}
        self.assertEqual(
            ids, {"react-cursorrules", "react-rules-2.1-optimized"}
        )


# ---------------------------------------------------------------------------
# merge_index sidecar loading
# ---------------------------------------------------------------------------


class TestMergeIndexSidecarLoading(unittest.TestCase):
    """Validate §4.1 + §4.2 — merge_index loads new sidecars."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        for t in merge_index.TYPES:
            os.makedirs(os.path.join(self.tmpdir, t), exist_ok=True)
        self._orig_catalog_dir = merge_index.CATALOG_DIR
        merge_index.CATALOG_DIR = self.tmpdir

    def tearDown(self):
        merge_index.CATALOG_DIR = self._orig_catalog_dir

    def _write(self, type_name, entries, filename="index.json"):
        path = os.path.join(self.tmpdir, type_name, filename)
        with open(path, "w") as f:
            json.dump(entries, f)

    def _read_output(self):
        path = os.path.join(self.tmpdir, "index.json")
        with open(path) as f:
            return json.load(f)

    def _run_merge(self):
        with unittest.mock.patch("merge_index.enrich_entries") as me, \
             unittest.mock.patch("merge_index.apply_governance") as mg:
            me.side_effect = lambda x: x
            mg.side_effect = lambda x: x
            # Disable the plugin.json gate: this suite exercises dedup, not the
            # manifest gate, and must never reach out to the GitHub Tree API
            # even when a GITHUB_TOKEN happens to be present in CI.
            merge_index.merge(verify_plugin_manifest=False)

    def test_mcp_registry_sidecar_loaded(self):
        """Lone registry entry shows up in catalog/index.json."""
        registry_entry = _mcp_entry(
            "lone-registry",
            "https://registry.modelcontextprotocol.io/v0/servers/io.github.solo%2Fmcp",
            extra={"mcp_registry_status": "active"},
        )
        self._write("mcp", [], filename="index.json")
        self._write("mcp", [registry_entry], filename="mcp_registry_index.json")
        self._run_merge()
        out = self._read_output()
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["id"], "lone-registry")
        self.assertEqual(out[0]["mcp_registry_status"], "active")

    def test_mcp_registry_collapses_with_main_index_github_entry(self):
        """When main mcp/index.json has GitHub URL + registry sidecar has match,
        they collapse; GitHub URL wins, registry fields merged in.
        """
        gh_entry = _mcp_entry(
            "foo-bar-gh",
            "https://github.com/foo/bar",
            extra={"source": "wong2"},
        )
        registry_entry = _mcp_entry(
            "foo-bar-registry",
            "https://registry.modelcontextprotocol.io/v0/servers/io.github.foo%2Fbar",
            extra={
                "source": "registry.modelcontextprotocol.io",
                "mcp_registry_status": "active",
                "mcp_registry_published_at": "2026-04-01T00:00:00Z",
            },
        )
        self._write("mcp", [gh_entry], filename="index.json")
        self._write("mcp", [registry_entry], filename="mcp_registry_index.json")
        self._run_merge()
        out = self._read_output()
        self.assertEqual(len(out), 1)
        kept = out[0]
        self.assertEqual(kept["id"], "foo-bar-gh")
        self.assertEqual(kept["source_url"], "https://github.com/foo/bar")
        self.assertEqual(kept["mcp_registry_status"], "active")
        self.assertEqual(kept["mcp_registry_published_at"], "2026-04-01T00:00:00Z")

    def test_mcp_registry_sidecar_absent_does_not_crash(self):
        """No sidecar file → merge runs cleanly with INFO log."""
        gh_entry = _mcp_entry("only-gh", "https://github.com/only/gh")
        self._write("mcp", [gh_entry], filename="index.json")
        # No mcp_registry_index.json written.
        self._run_merge()
        out = self._read_output()
        self.assertEqual(len(out), 1)

    def test_windsurfrules_sidecar_loaded(self):
        """windsurfrules_index.json entries surface in catalog/index.json."""
        wr_entry = _rule_entry(
            "react-windsurfrules-schneidersam",
            "https://github.com/SchneiderSam/awesome-windsurfrules/blob/main/rules/react/.windsurfrules",
        )
        self._write("rules", [], filename="index.json")
        self._write("rules", [wr_entry], filename="windsurfrules_index.json")
        self._run_merge()
        out = self._read_output()
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["id"], "react-windsurfrules-schneidersam")

    def test_windsurfrules_sidecar_absent_does_not_crash(self):
        """No windsurfrules sidecar → merge runs cleanly."""
        rule = _rule_entry("only-rule", "https://github.com/foo/rules-repo")
        self._write("rules", [rule], filename="index.json")
        self._run_merge()
        out = self._read_output()
        self.assertEqual(len(out), 1)


if __name__ == "__main__":
    unittest.main()
