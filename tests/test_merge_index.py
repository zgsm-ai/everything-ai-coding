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


def _make_entry(
    id,
    name="Test",
    type="mcp",
    source_url="https://github.com/test/test",
    category="tooling",
    stars=10,
    description="A test entry",
    pushed_at="2026-03-01T00:00:00Z",
):
    return {
        "id": id,
        "name": name,
        "type": type,
        "description": description,
        "source_url": source_url,
        "stars": stars,
        "category": category,
        "tags": [],
        "tech_stack": [],
        "install": {"method": "manual"},
        "source": "test",
        "last_synced": "2026-03-30",
        "pushed_at": pushed_at,
    }


class TestMergeIndex(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        for t in merge_index.TYPES:
            os.makedirs(os.path.join(self.tmpdir, t), exist_ok=True)
        self._orig_catalog_dir = merge_index.CATALOG_DIR
        merge_index.CATALOG_DIR = self.tmpdir

    def tearDown(self):
        merge_index.CATALOG_DIR = self._orig_catalog_dir

    def _write_index(self, type_name, entries, filename="index.json"):
        path = os.path.join(self.tmpdir, type_name, filename)
        with open(path, "w") as f:
            json.dump(entries, f)

    def _read_output(self):
        path = os.path.join(self.tmpdir, "index.json")
        with open(path) as f:
            return json.load(f)

    def test_basic_merge(self):
        self._write_index(
            "mcp", [_make_entry("a", source_url="https://github.com/t/a")]
        )
        self._write_index(
            "skills",
            [_make_entry("b", type="skill", source_url="https://github.com/t/b")],
        )

        with unittest.mock.patch("merge_index.enrich_entries") as mock_enrich, \
             unittest.mock.patch("merge_index.apply_governance") as mock_gov:
            mock_enrich.side_effect = lambda x: x
            mock_gov.side_effect = lambda x: x
            merge_index.merge()
        result = self._read_output()

        self.assertEqual(len(result), 2)
        ids = {r["id"] for r in result}
        self.assertEqual(ids, {"a", "b"})

    def test_synthesized_plugin_children_are_written_to_type_indexes(self):
        plugin = _make_entry(
            "plugin-one",
            type="plugin",
            source_url="https://github.com/acme/plugin-one",
        )
        plugin["install"] = {
            "method": "plugin_marketplace",
            "marketplace_repo": "acme/plugin-one",
            "marketplace_verified": True,
        }
        plugin["bundle"] = {
            "skills_namespaces": ["plugin-one:ghost"],
            "skill_paths": ["skills/ghost/SKILL.md"],
            "source_repo": "acme/plugin-one",
            "source_ref": "HEAD",
            "mcp_server_names": ["plugin-mcp"],
            "mcp_server_configs": {
                "plugin-mcp": {"command": "npx", "args": ["plugin-mcp"]},
            },
        }
        self._write_index("plugins", [plugin])

        with unittest.mock.patch("merge_index.enrich_entries") as mock_enrich, \
             unittest.mock.patch("merge_index.apply_governance") as mock_gov:
            mock_enrich.side_effect = lambda x: x
            mock_gov.side_effect = lambda x: x
            merge_index.merge(verify_plugin_manifest=False)

        top = self._read_output()
        top_children = {
            e["id"] for e in top
            if e.get("source") in ("plugin-bundled-skill", "plugin-bundled-mcp")
        }
        self.assertEqual(
            top_children,
            {"plugin-one-ghost", "plugin-one-mcp-plugin-mcp"},
        )

        with open(os.path.join(self.tmpdir, "skills", "index.json")) as f:
            skills_index = json.load(f)
        with open(os.path.join(self.tmpdir, "mcp", "index.json")) as f:
            mcp_index = json.load(f)

        self.assertIn("plugin-one-ghost", {e["id"] for e in skills_index})
        self.assertIn("plugin-one-mcp-plugin-mcp", {e["id"] for e in mcp_index})
        output_plugin = next(e for e in top if e["id"] == "plugin-one")
        self.assertEqual(
            output_plugin["bundle"]["bundled_skill_ids"],
            ["plugin-one-ghost"],
        )
        self.assertEqual(
            output_plugin["bundle"]["bundled_mcp_ids"],
            ["plugin-one-mcp-plugin-mcp"],
        )

    def test_dedup_id_keeps_first(self):
        self._write_index(
            "mcp",
            [_make_entry("dup", name="First", source_url="https://github.com/t/first")],
        )
        self._write_index(
            "mcp",
            [
                _make_entry(
                    "dup", name="Second", source_url="https://github.com/t/second"
                )
            ],
            filename="curated.json",
        )

        with unittest.mock.patch("merge_index.enrich_entries") as mock_enrich, \
             unittest.mock.patch("merge_index.apply_governance") as mock_gov:
            mock_enrich.side_effect = lambda x: x
            mock_gov.side_effect = lambda x: x
            merge_index.merge()
        result = self._read_output()

        dup_entries = [r for r in result if r["id"] == "dup"]
        self.assertEqual(len(dup_entries), 1)
        self.assertEqual(dup_entries[0]["name"], "First")

    def test_unevaluated_entry_gets_defaults(self):
        """Entries without harness evaluation get score=0, decision=review."""
        entry = _make_entry("h1", source_url="https://github.com/t/h1")
        self._write_index("mcp", [entry])

        with unittest.mock.patch("merge_index.enrich_entries") as mock_enrich:
            mock_enrich.side_effect = lambda x: x
            merge_index.merge()
        result = self._read_output()

        self.assertEqual(result[0]["final_score"], 0)
        self.assertEqual(result[0]["decision"], "review")

    def test_merge_prefers_older_added_at_from_source_indexes(self):
        entry = _make_entry(
            "older-added", source_url="https://github.com/t/older-added"
        )
        entry["added_at"] = "2024-01-15"
        self._write_index("mcp", [entry])
        with open(os.path.join(self.tmpdir, "index.json"), "w") as f:
            json.dump(
                [
                    {
                        "id": "older-added",
                        "type": "mcp",
                        "source_url": "https://github.com/t/older-added",
                        "added_at": "2026-03-25",
                    }
                ],
                f,
            )

        with unittest.mock.patch("merge_index.enrich_entries") as mock_enrich, \
             unittest.mock.patch("merge_index.apply_governance") as mock_gov:
            mock_enrich.side_effect = lambda x: x
            mock_gov.side_effect = lambda x: x
            merge_index.merge()
        result = self._read_output()

        self.assertEqual(result[0]["added_at"], "2024-01-15")

    def test_sorted_by_final_score_then_health_desc(self):
        low_entry = _make_entry(
            "low",
            stars=0,
            pushed_at=None,
            source_url="https://github.com/t/low",
        )
        high_entry = _make_entry(
            "high",
            stars=5000,
            pushed_at="2026-03-29T00:00:00Z",
            source_url="https://github.com/t/high",
        )
        low_entry["description"] = "low"
        high_entry["description"] = "A" * 100
        high_entry["install"]["method"] = "mcp_config"
        self._write_index(
            "mcp",
            [low_entry, high_entry],
        )

        with unittest.mock.patch("merge_index.enrich_entries") as mock_enrich, \
             unittest.mock.patch("merge_index.apply_governance") as mock_gov:
            mock_enrich.side_effect = lambda x: x
            mock_gov.side_effect = lambda x: x
            merge_index.merge()
        result = self._read_output()

        self.assertEqual(result[0]["id"], "high")
        self.assertEqual(result[1]["id"], "low")

    def test_invalid_category_fixed(self):
        entry = _make_entry(
            "bad-cat",
            category="other",
            source_url="https://github.com/t/bad",
            name="docker-deploy",
            description="Deploy containers with Docker",
        )
        self._write_index("mcp", [entry])

        with unittest.mock.patch("merge_index.enrich_entries") as mock_enrich, \
             unittest.mock.patch("merge_index.apply_governance") as mock_gov:
            mock_enrich.side_effect = lambda x: x
            mock_gov.side_effect = lambda x: x
            merge_index.merge()
        result = self._read_output()

        self.assertNotEqual(result[0]["category"], "other")

    def test_empty_type_dir_no_crash(self):
        self._write_index(
            "mcp", [_make_entry("only", source_url="https://github.com/t/only")]
        )

        with unittest.mock.patch("merge_index.enrich_entries") as mock_enrich, \
             unittest.mock.patch("merge_index.apply_governance") as mock_gov:
            mock_enrich.side_effect = lambda x: x
            mock_gov.side_effect = lambda x: x
            merge_index.merge()
        result = self._read_output()

        self.assertEqual(len(result), 1)

    @unittest.mock.patch("merge_index.enrich_entries")
    def test_enrichment_called(self, mock_enrich):
        """enrich_entries is called during merge."""
        entry = _make_entry("e1", source_url="https://github.com/t/e1")
        self._write_index("mcp", [entry])

        mock_enrich.side_effect = lambda x: x
        with unittest.mock.patch("merge_index.apply_governance") as mock_gov:
            mock_gov.side_effect = lambda x: x
            merge_index.merge()

        mock_enrich.assert_called_once()

    @unittest.mock.patch.dict(os.environ, {}, clear=True)
    def test_enrichment_no_credentials_no_crash(self):
        """No credentials → enrichment skipped, no crash."""
        os.environ.pop("LLM_BASE_URL", None)
        os.environ.pop("LLM_API_KEY", None)
        os.environ.pop("GITHUB_TOKEN", None)
        entry = _make_entry("nocred", source_url="https://github.com/t/nocred")
        self._write_index("mcp", [entry])

        with unittest.mock.patch("merge_index.enrich_entries") as mock_enrich, \
             unittest.mock.patch("merge_index.apply_governance") as mock_gov:
            mock_enrich.side_effect = lambda x: x
            mock_gov.side_effect = lambda x: x
            merge_index.merge()
        result = self._read_output()

        self.assertEqual(len(result), 1)

    def test_harness_evaluated_entry_passthrough(self):
        """Entries with harness evaluation pass through governance unchanged."""
        entry = _make_entry("gov1", source_url="https://github.com/t/gov1")
        entry["evaluation"] = {
            "model_id": "deepseek-chat",
            "final_score": 85.0,
            "decision": "accept",
            "coding_relevance": 5,
        }
        self._write_index("mcp", [entry])

        with unittest.mock.patch("merge_index.enrich_entries") as mock_enrich:
            mock_enrich.side_effect = lambda x: x
            merge_index.merge()
        result = self._read_output()

        self.assertIn("evaluation", result[0])
        self.assertIn("final_score", result[0])
        self.assertIn("decision", result[0])
        self.assertEqual(result[0]["final_score"], 85.0)
        self.assertEqual(result[0]["decision"], "accept")
        self.assertGreater(result[0]["final_score"], 0)
        self.assertIn(result[0]["decision"], ("accept", "review", "reject"))

    def test_skills_sh_index_loaded_into_pool(self):
        """skills_sh_index.json is picked up alongside skills/index.json and merged."""
        # Anthropics direct entry in main skills index
        direct = _make_entry(
            "frontend-design-skill",
            type="skill",
            name="frontend-design",
            source_url="https://github.com/anthropics/skills/tree/main/skills/frontend-design",
        )
        # skills.sh entry (different id, anchor URL, carries install_count)
        sh_entry = _make_entry(
            "frontend-design-anthropics-skills",
            type="skill",
            name="frontend-design",
            source_url="https://github.com/anthropics/skills#skill=frontend-design",
        )
        sh_entry["install_count"] = 54321
        sh_entry["skills_sh_url"] = "https://skills.sh/anthropics/skills/frontend-design"
        sh_entry["skills_sh_scraped_at"] = "2026-01-30T04:51:07.907Z"

        self._write_index("skills", [direct])
        self._write_index("skills", [sh_entry], filename="skills_sh_index.json")

        with unittest.mock.patch("merge_index.enrich_entries") as mock_enrich, \
             unittest.mock.patch("merge_index.apply_governance") as mock_gov:
            mock_enrich.side_effect = lambda x: x
            mock_gov.side_effect = lambda x: x
            merge_index.merge()
        result = self._read_output()

        # The two entries collapse into one — direct anthropics wins, skills.sh fields merged in.
        assert len(result) == 1
        kept = result[0]
        assert kept["id"] == "frontend-design-skill"
        assert kept["install_count"] == 54321
        assert kept["skills_sh_url"] == "https://skills.sh/anthropics/skills/frontend-design"
        assert kept["skills_sh_scraped_at"] == "2026-01-30T04:51:07.907Z"

    def test_skills_sh_index_only_pickup(self):
        """A skills.sh entry with no main-index sibling lands in catalog/index.json."""
        sh_entry = _make_entry(
            "lone-skill-vercel-labs-agent-skills",
            type="skill",
            name="lone-skill",
            source_url="https://github.com/vercel-labs/agent-skills#skill=lone-skill",
        )
        sh_entry["install_count"] = 9999
        self._write_index("skills", [], filename="index.json")
        self._write_index("skills", [sh_entry], filename="skills_sh_index.json")

        with unittest.mock.patch("merge_index.enrich_entries") as mock_enrich, \
             unittest.mock.patch("merge_index.apply_governance") as mock_gov:
            mock_enrich.side_effect = lambda x: x
            mock_gov.side_effect = lambda x: x
            merge_index.merge()
        result = self._read_output()

        assert len(result) == 1
        assert result[0]["id"] == "lone-skill-vercel-labs-agent-skills"
        assert result[0]["install_count"] == 9999

    def test_dedup_integrity_stats_logged(self):
        """Merge logs per-type dedup stats."""
        self._write_index(
            "mcp",
            [
                _make_entry("m1", source_url="https://github.com/t/m1"),
                _make_entry("m2", source_url="https://github.com/t/m2"),
                _make_entry("m3", source_url="https://github.com/t/m3"),
            ],
        )

        with self.assertLogs("utils", level="INFO") as cm:
            with unittest.mock.patch("merge_index.enrich_entries") as mock_enrich, \
                 unittest.mock.patch("merge_index.apply_governance") as mock_gov:
                mock_enrich.side_effect = lambda x: x
                mock_gov.side_effect = lambda x: x
                merge_index.merge()

        log_text = "\n".join(cm.output)
        self.assertIn("Dedup", log_text)


class TestPluginMarketplaceValidator(unittest.TestCase):
    """Tests for the merge_index schema validator that drops plugin entries
    missing required marketplace fields (added by fix-plugin-marketplace-fields).
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        for t in merge_index.TYPES:
            os.makedirs(os.path.join(self.tmpdir, t), exist_ok=True)
        self._orig_catalog_dir = merge_index.CATALOG_DIR
        merge_index.CATALOG_DIR = self.tmpdir

    def tearDown(self):
        merge_index.CATALOG_DIR = self._orig_catalog_dir

    def _write_plugins(self, entries):
        path = os.path.join(self.tmpdir, "plugins", "index.json")
        with open(path, "w") as f:
            json.dump(entries, f)

    def _read_output(self):
        with open(os.path.join(self.tmpdir, "index.json")) as f:
            return json.load(f)

    @staticmethod
    def _plugin(id, plugin_name, *, repo, verified=True, name="missing"):
        e = _make_entry(id, type="plugin", source_url=f"https://github.com/{repo}")
        e["install"] = {
            "method": "plugin_marketplace",
            "plugin_name": plugin_name,
            "marketplace_repo": repo,
            "marketplace_name": name,
            "marketplace_verified": verified,
            "marketplace": repo,
        }
        return e

    def test_plugin_missing_marketplace_repo_dropped(self):
        good = self._plugin(
            "ok-plugin", "ralph-loop", repo="anthropics/claude-plugins-official",
        )
        bad = self._plugin(
            "bad-plugin", "broken", repo="anthropics/claude-plugins-official",
        )
        del bad["install"]["marketplace_repo"]

        self._write_plugins([good, bad])

        with self.assertLogs("utils", level="WARNING") as cm, \
             unittest.mock.patch("merge_index.enrich_entries") as mock_enrich, \
             unittest.mock.patch("merge_index.apply_governance") as mock_gov:
            mock_enrich.side_effect = lambda x: x
            mock_gov.side_effect = lambda x: x
            merge_index.merge(verify_plugin_manifest=False)
        result = self._read_output()

        plugins = [r for r in result if r.get("type") == "plugin"]
        ids = {r["id"] for r in plugins}
        self.assertEqual(ids, {"ok-plugin"})
        self.assertTrue(
            any("marketplace_repo" in line for line in cm.output),
            f"Expected WARNING mentioning marketplace_repo; got: {cm.output}",
        )

    def test_plugin_missing_marketplace_verified_dropped(self):
        good = self._plugin(
            "ok-plugin", "ralph-loop", repo="anthropics/claude-plugins-official",
        )
        bad = self._plugin(
            "bad-plugin", "broken", repo="anthropics/claude-plugins-official",
        )
        del bad["install"]["marketplace_verified"]

        self._write_plugins([good, bad])

        with self.assertLogs("utils", level="WARNING") as cm, \
             unittest.mock.patch("merge_index.enrich_entries") as mock_enrich, \
             unittest.mock.patch("merge_index.apply_governance") as mock_gov:
            mock_enrich.side_effect = lambda x: x
            mock_gov.side_effect = lambda x: x
            merge_index.merge(verify_plugin_manifest=False)
        result = self._read_output()

        plugins = [r for r in result if r.get("type") == "plugin"]
        ids = {r["id"] for r in plugins}
        self.assertEqual(ids, {"ok-plugin"})
        self.assertTrue(
            any("marketplace_verified" in line for line in cm.output),
            f"Expected WARNING mentioning marketplace_verified; got: {cm.output}",
        )

    def test_plugin_marketplace_name_null_preserved(self):
        """marketplace_name=None is allowed (manifest had no `name` field).
        marketplace_verified must still be present as a bool; here it's False."""
        e = self._plugin(
            "unverified-plugin", "x", repo="vercel/next.js",
            verified=False, name=None,
        )
        self._write_plugins([e])

        with unittest.mock.patch("merge_index.enrich_entries") as mock_enrich, \
             unittest.mock.patch("merge_index.apply_governance") as mock_gov:
            mock_enrich.side_effect = lambda x: x
            mock_gov.side_effect = lambda x: x
            merge_index.merge(verify_plugin_manifest=False)
        result = self._read_output()
        plugins = [r for r in result if r.get("type") == "plugin"]
        self.assertEqual(len(plugins), 1)
        self.assertIs(plugins[0]["install"]["marketplace_verified"], False)
        self.assertIsNone(plugins[0]["install"]["marketplace_name"])


class TestBundledInReverseMapping(unittest.TestCase):
    """Tests for plugin.bundle.bundled_skill_ids reverse mapping written by
    ``merge_index._apply_bundled_in_annotations``."""

    def test_apply_bundled_in_writes_reverse_mapping(self):
        """Plugin with 3 namespaces (2 matched + 1 orphan) gets a
        position-aligned ``bundled_skill_ids`` list of length 3 where the
        orphan slot is ``None``."""
        plugin = _make_entry(
            "superpowers-plugin",
            type="plugin",
            source_url="https://github.com/obra/superpowers",
        )
        plugin["bundle"] = {
            "skills_namespaces": [
                "superpowers:brainstorming",
                "superpowers:writing-plans",
                "superpowers:does-not-exist",
            ]
        }
        skill_a = _make_entry(
            "superpowers-brainstorming",
            type="skill",
            source_url="https://github.com/obra/superpowers/tree/main/skills/brainstorming",
        )
        skill_a["namespace"] = "superpowers:brainstorming"
        skill_b = _make_entry(
            "superpowers-writing-plans",
            type="skill",
            source_url="https://github.com/obra/superpowers/tree/main/skills/writing-plans",
        )
        skill_b["namespace"] = "superpowers:writing-plans"

        entries = [plugin, skill_a, skill_b]
        merge_index._apply_bundled_in_annotations(entries)

        self.assertIn("bundle", plugin)
        self.assertIn("bundled_skill_ids", plugin["bundle"])
        self.assertEqual(
            plugin["bundle"]["bundled_skill_ids"],
            ["superpowers-brainstorming", "superpowers-writing-plans", None],
        )
        self.assertEqual(
            len(plugin["bundle"]["bundled_skill_ids"]),
            len(plugin["bundle"]["skills_namespaces"]),
        )

    def test_apply_bundled_in_skips_empty_namespaces_for_reverse(self):
        """Plugin with empty/missing ``skills_namespaces`` must NOT have
        ``bundle.bundled_skill_ids`` set (absent, not ``[]``)."""
        plugin_empty = _make_entry(
            "no-skills-plugin",
            type="plugin",
            source_url="https://github.com/example/no-skills",
        )
        plugin_empty["bundle"] = {"skills_namespaces": []}

        plugin_missing = _make_entry(
            "no-bundle-plugin",
            type="plugin",
            source_url="https://github.com/example/no-bundle",
        )
        # No "bundle" key at all.

        entries = [plugin_empty, plugin_missing]
        merge_index._apply_bundled_in_annotations(entries)

        # Empty list case: bundle dict present (from input), but no reverse field.
        self.assertIn("bundle", plugin_empty)
        self.assertNotIn("bundled_skill_ids", plugin_empty["bundle"])

        # Missing bundle case: we must not have manufactured one with the field.
        bundle = plugin_missing.get("bundle") or {}
        self.assertNotIn("bundled_skill_ids", bundle)


class TestOrphanSubSkillSynthesis(unittest.TestCase):
    """Tests for synthesizing standalone type=skill entries for orphan
    sub-skills bundled by a plugin (merge_index._apply_bundled_in_annotations
    orphan branch + _synthetic_skill_id helper)."""

    def test_synthetic_id_is_kebab_idempotent(self):
        """Synthetic ids must satisfy to_kebab_case(id) == id so the downloaded
        folder name (to_kebab_case) matches the raw id costrict-web looks up."""
        from utils import to_kebab_case

        cases = [
            ("everything-claude-code-superpowers", "Brainstorming"),
            ("foo_bar__plugin", "writing_plans"),
            ("Plugin Name", "Skill Name With Spaces"),
            ("a", "b"),
        ]
        for plugin_id, skill_name in cases:
            sid = merge_index._synthetic_skill_id(plugin_id, skill_name, set())
            self.assertRegex(sid, r"^[a-z0-9-]+$", f"id {sid!r} not kebab-safe")
            self.assertEqual(
                to_kebab_case(sid), sid,
                f"id {sid!r} not idempotent under to_kebab_case",
            )

    def test_synthetic_id_collision_appends_shorthash(self):
        existing = {"superpowers-brainstorming"}
        sid = merge_index._synthetic_skill_id(
            "superpowers", "brainstorming", existing
        )
        self.assertNotIn(sid, existing)
        self.assertTrue(sid.startswith("superpowers-brainstorming-"))
        self.assertRegex(sid, r"^[a-z0-9-]+$")

    def test_orphan_synthesizes_standalone_skill_entry(self):
        """Plugin with a matched skill + an orphan sub-skill (carrying
        skill_paths/source_repo in bundle) produces a new type=skill entry with
        the right id/install/bundled_in, and backfills bundled_skill_ids."""
        plugin = _make_entry(
            "superpowers-plugin",
            type="plugin",
            source_url="https://github.com/obra/superpowers",
        )
        plugin["bundle"] = {
            "skills_namespaces": [
                "superpowers:brainstorming",
                "superpowers:secret-skill",
            ],
            "skill_paths": [
                "skills/brainstorming/SKILL.md",
                "skills/secret-skill/SKILL.md",
            ],
            "source_repo": "obra/superpowers",
            "source_ref": "main",
        }
        skill_a = _make_entry(
            "superpowers-brainstorming",
            type="skill",
            source_url="https://github.com/obra/superpowers/tree/main/skills/brainstorming",
        )
        skill_a["namespace"] = "superpowers:brainstorming"

        entries = [plugin, skill_a]
        merge_index._apply_bundled_in_annotations(entries)

        # A new synthesized skill entry should now exist.
        synth = [
            e for e in entries
            if e.get("source") == "plugin-bundled-skill"
        ]
        self.assertEqual(len(synth), 1)
        s = synth[0]
        self.assertEqual(s["type"], "skill")
        self.assertEqual(s["bundled_in"], "superpowers-plugin")
        self.assertEqual(s["name"], "secret-skill")
        # id kebab-safe + idempotent
        from utils import to_kebab_case
        self.assertRegex(s["id"], r"^[a-z0-9-]+$")
        self.assertEqual(to_kebab_case(s["id"]), s["id"])
        # install block usable by download_catalog (git_clone + repo + path)
        self.assertEqual(s["install"]["method"], "git_clone")
        self.assertEqual(
            s["install"]["repo"], "https://github.com/obra/superpowers.git"
        )
        self.assertEqual(s["install"]["branch"], "main")
        self.assertEqual(s["install"]["path"], "skills/secret-skill")
        # OUTWARD source_path = real path (no plugin_root here → verbatim)
        self.assertEqual(s["source_path"], "skills/secret-skill/SKILL.md")
        # reverse mapping backfilled with the synthetic id (not None)
        ids = plugin["bundle"]["bundled_skill_ids"]
        self.assertEqual(ids[0], "superpowers-brainstorming")
        self.assertEqual(ids[1], s["id"])
        self.assertIsNone(None if ids[1] else True)

    def test_orphan_skill_source_path_is_plugin_root_relative_real_path(self):
        """cospower case: bundled skills live under <plugin_root>/skills/<name>/.
        The synthesized child's OUTWARD source_path must be the plugin-root
        relative REAL path (skills/<name>/SKILL.md) — same shape as evaluators
        and archive uploads — so the work tree mirrors GitHub at the real name,
        NOT a synthetic-id stub. install.path stays FULL repo-relative."""
        plugin = _make_entry(
            "cos-req",
            type="plugin",
            source_url="https://github.com/yhangf/csc-plugins/tree/main/cos-req",
        )
        plugin["bundle"] = {
            "skills_namespaces": ["cos-req:requirement-analysis"],
            "skill_paths": [
                "cospowers-requirements-plugin/skills/requirement-analysis/SKILL.md"
            ],
            "plugin_root": "cospowers-requirements-plugin",
            "source_repo": "yhangf/csc-plugins",
            "source_ref": "main",
        }
        entries = [plugin]
        merge_index._apply_bundled_in_annotations(entries)

        s = next(e for e in entries if e.get("source") == "plugin-bundled-skill")
        # plugin-root relative real path, no <plugin_root>/ prefix
        self.assertEqual(s["source_path"], "skills/requirement-analysis/SKILL.md")
        self.assertFalse(s["source_path"].startswith("cospowers-requirements-plugin/"))
        # install.path stays FULL repo-relative for the directory download
        self.assertEqual(
            s["install"]["path"],
            "cospowers-requirements-plugin/skills/requirement-analysis",
        )

    def test_orphan_without_skill_paths_falls_back_to_none(self):
        """Legacy bundle without skill_paths/source_repo → orphan stays None,
        no synthesis (back-compat)."""
        plugin = _make_entry(
            "legacy-plugin",
            type="plugin",
            source_url="https://github.com/x/legacy",
        )
        plugin["bundle"] = {
            "skills_namespaces": ["legacy:ghost"],
        }
        entries = [plugin]
        merge_index._apply_bundled_in_annotations(entries)

        self.assertEqual(
            len([e for e in entries if e.get("source") == "plugin-bundled-skill"]),
            0,
        )
        self.assertEqual(plugin["bundle"]["bundled_skill_ids"], [None])

    def test_orphan_skill_keeps_head_ref_for_default_branch_resolution(self):
        plugin = _make_entry(
            "head-plugin",
            type="plugin",
            source_url="https://github.com/x/head-plugin",
        )
        plugin["bundle"] = {
            "skills_namespaces": ["head:ghost"],
            "skill_paths": ["skills/ghost/SKILL.md"],
            "source_repo": "x/head-plugin",
            "source_ref": "HEAD",
        }

        entries = [plugin]
        merge_index._apply_bundled_in_annotations(entries)

        synth = next(e for e in entries if e.get("source") == "plugin-bundled-skill")
        self.assertEqual(synth["install"]["branch"], "HEAD")

    def test_reused_existing_bundled_skill_gets_source_path_backfilled(self):
        """REGRESSION: a bundled skill already present in catalog/skills/index.json
        from an earlier (pre-P3) synthesis carries source_path=None. The reuse/
        match path must BACKFILL the plugin-root-relative real source_path from
        the current bundle's skill_paths (NOT keep the stale None), and must NOT
        create a duplicate. This is the exact path unit tests missed (they only
        synthesized into an empty catalog)."""
        plugin = _make_entry(
            "cos-req",
            type="plugin",
            source_url="https://github.com/yhangf/csc-plugins/tree/main/cos-req",
        )
        plugin["bundle"] = {
            "skills_namespaces": ["cos-req:requirement-analysis"],
            "skill_paths": [
                "cos-req-plugin/skills/requirement-analysis/SKILL.md"
            ],
            "plugin_root": "cos-req-plugin",
            "source_repo": "yhangf/csc-plugins",
            "source_ref": "main",
        }
        # Pre-existing entry (id == the deterministic synthetic id) WITHOUT a
        # source_path — exactly what HEAD's catalog/skills/index.json holds.
        old_child = _make_entry(
            "cos-req-requirement-analysis",
            name="requirement-analysis",
            type="skill",
            source_url="https://github.com/yhangf/csc-plugins/tree/main/cos-req-plugin/skills/requirement-analysis",
        )
        old_child["bundled_in"] = "cos-req"
        old_child["source"] = "plugin-bundled-skill"
        old_child["install"] = {
            "method": "git_clone",
            "repo": "https://github.com/yhangf/csc-plugins.git",
            "branch": "main",
            "path": "cos-req-plugin/skills/requirement-analysis",
        }
        # NOTE: deliberately no "source_path" key (None/missing).
        self.assertNotIn("source_path", old_child)

        entries = [plugin, old_child]
        merge_index._apply_bundled_in_annotations(entries)

        bundled = [e for e in entries if e.get("source") == "plugin-bundled-skill"]
        # no duplicate created
        self.assertEqual(len(bundled), 1)
        reused = bundled[0]
        self.assertIs(reused, old_child)  # same object reused
        # source_path BACKFILLED to the plugin-root-relative real path
        self.assertEqual(reused["source_path"], "skills/requirement-analysis/SKILL.md")
        # install untouched (still full repo-relative)
        self.assertEqual(
            reused["install"]["path"], "cos-req-plugin/skills/requirement-analysis"
        )

    def test_reused_bundled_skill_overwrites_stale_source_path(self):
        """If a re-loaded entry has an explicit-None / stale source_path it is
        OVERWRITTEN with the fresh plugin-root-relative path."""
        plugin = _make_entry(
            "cos-req", type="plugin",
            source_url="https://github.com/yhangf/csc-plugins/tree/main/cos-req",
        )
        plugin["bundle"] = {
            "skills_namespaces": ["cos-req:session-context"],
            "skill_paths": ["cos-req-plugin/skills/session-context/SKILL.md"],
            "plugin_root": "cos-req-plugin",
            "source_repo": "yhangf/csc-plugins",
            "source_ref": "main",
        }
        old_child = _make_entry(
            "cos-req-session-context", name="session-context", type="skill",
            source_url="https://github.com/yhangf/csc-plugins/tree/main/cos-req-plugin/skills/session-context",
        )
        old_child["bundled_in"] = "cos-req"
        old_child["source"] = "plugin-bundled-skill"
        old_child["source_path"] = None  # explicit stale None

        entries = [plugin, old_child]
        merge_index._apply_bundled_in_annotations(entries)
        self.assertEqual(
            old_child["source_path"], "skills/session-context/SKILL.md"
        )

    def test_final_score_inherited_from_parent_plugin(self):
        """Synthesized plugin children inherit the parent plugin's score."""
        plugin = _make_entry("p1", type="plugin", source_url="https://github.com/x/p1")
        plugin["final_score"] = 72.5
        synth = _make_entry("p1-ghost", type="skill", source_url="https://github.com/x/p1/tree/main/skills/ghost")
        synth["source"] = "plugin-bundled-skill"
        synth["bundled_in"] = "p1"
        synth["final_score"] = 0
        mcp = _make_entry("p1-mcp-ghost", type="mcp", source_url="https://github.com/x/p1")
        mcp["source"] = "plugin-bundled-mcp"
        mcp["bundled_in"] = "p1"
        mcp["final_score"] = 0
        entries = [plugin, synth, mcp]
        merge_index._backfill_bundled_child_final_scores(entries)
        self.assertEqual(synth["final_score"], 72.5)
        self.assertEqual(mcp["final_score"], 72.5)

    def test_final_score_backfill_skips_non_synthesized(self):
        """A real standalone skill that carries bundled_in keeps its own score
        (only source == plugin-bundled-skill is rewritten)."""
        plugin = _make_entry("p2", type="plugin", source_url="https://github.com/x/p2")
        plugin["final_score"] = 90
        real = _make_entry("real-skill", type="skill", source_url="https://github.com/x/p2/tree/main/skills/real")
        real["source"] = "anthropics-skills"
        real["bundled_in"] = "p2"
        real["final_score"] = 30
        entries = [plugin, real]
        merge_index._backfill_bundled_child_final_scores(entries)
        self.assertEqual(real["final_score"], 30)


class TestBundledMcpSynthesis(unittest.TestCase):
    """Tests for synthesizing standalone MCP entries from plugin bundle config."""

    def test_synthesizes_standalone_mcp_entries(self):
        plugin = _make_entry(
            "zoom-plugin",
            type="plugin",
            source_url="https://github.com/zoom/zoom-plugin",
        )
        plugin["bundle"] = {
            "mcp_server_names": ["zoom-mcp", "zoom-docs-mcp", "missing-config"],
            "mcp_server_configs": {
                "zoom-mcp": {"command": "npx", "args": ["zoom-mcp"]},
                "zoom-docs-mcp": {"url": "https://example.com/mcp"},
            },
        }

        entries = [plugin]
        merge_index._apply_bundled_in_annotations(entries)

        synth = [
            e for e in entries
            if e.get("source") == "plugin-bundled-mcp"
        ]
        self.assertEqual(len(synth), 2)
        by_name = {e["name"]: e for e in synth}
        self.assertEqual(set(by_name), {"zoom-mcp", "zoom-docs-mcp"})
        self.assertEqual(by_name["zoom-mcp"]["type"], "mcp")
        self.assertEqual(by_name["zoom-mcp"]["bundled_in"], "zoom-plugin")
        self.assertEqual(
            by_name["zoom-mcp"]["install"],
            {"method": "mcp_config", "config": {"command": "npx", "args": ["zoom-mcp"]}},
        )
        self.assertRegex(by_name["zoom-mcp"]["id"], r"^[a-z0-9-]+$")
        # MCP children intentionally carry NO source_path: their downstream
        # identity is <path>#<server-key> (synthetic), not a faithful file path.
        self.assertNotIn("source_path", by_name["zoom-mcp"])
        self.assertEqual(
            plugin["bundle"]["bundled_mcp_ids"],
            [by_name["zoom-mcp"]["id"], by_name["zoom-docs-mcp"]["id"], None],
        )

    def test_does_not_synthesize_mcp_without_install_info(self):
        plugin = _make_entry(
            "empty-mcp-plugin",
            type="plugin",
            source_url="https://github.com/example/empty",
        )
        plugin["bundle"] = {
            "mcp_server_names": ["empty"],
            "mcp_server_configs": {"empty": {"args": ["no-command"]}},
        }

        entries = [plugin]
        merge_index._apply_bundled_in_annotations(entries)

        self.assertEqual(
            [e for e in entries if e.get("source") == "plugin-bundled-mcp"],
            [],
        )
        self.assertEqual(plugin["bundle"]["bundled_mcp_ids"], [None])

    def test_reuses_existing_plugin_bundled_mcp_entry(self):
        plugin = _make_entry(
            "zoom-plugin",
            type="plugin",
            source_url="https://github.com/zoom/zoom-plugin",
        )
        plugin["bundle"] = {
            "mcp_server_names": ["zoom-mcp"],
            "mcp_server_configs": {
                "zoom-mcp": {"command": "npx", "args": ["zoom-mcp@latest"]},
            },
        }
        existing = _make_entry(
            "zoom-plugin-mcp-zoom-mcp",
            name="zoom-mcp",
            type="mcp",
            source_url="https://github.com/zoom/zoom-plugin",
        )
        existing["source"] = "plugin-bundled-mcp"
        existing["bundled_in"] = "zoom-plugin"
        existing["install"] = {"method": "mcp_config", "config": {"command": "old"}}

        entries = [plugin, existing]
        merge_index._apply_bundled_in_annotations(entries)

        synth = [e for e in entries if e.get("source") == "plugin-bundled-mcp"]
        self.assertEqual(len(synth), 1)
        self.assertEqual(plugin["bundle"]["bundled_mcp_ids"], [existing["id"]])
        self.assertEqual(
            existing["install"],
            {"method": "mcp_config", "config": {"command": "npx", "args": ["zoom-mcp@latest"]}},
        )

    def test_prunes_stale_plugin_child_refs_after_governance(self):
        plugin = _make_entry("p1", type="plugin", source_url="https://github.com/x/p1")
        plugin["bundle"] = {
            "bundled_skill_ids": ["missing-skill", "kept-skill"],
            "bundled_mcp_ids": ["missing-mcp", "kept-mcp"],
        }
        skill = _make_entry("kept-skill", type="skill", source_url="https://github.com/x/p1")
        skill["source"] = "plugin-bundled-skill"
        skill["bundled_in"] = "p1"
        mcp = _make_entry("kept-mcp", type="mcp", source_url="https://github.com/x/p1")
        mcp["source"] = "plugin-bundled-mcp"
        mcp["bundled_in"] = "p1"
        orphan = _make_entry("orphan-child", type="mcp", source_url="https://github.com/x/orphan")
        orphan["source"] = "plugin-bundled-mcp"
        orphan["bundled_in"] = "filtered-plugin"

        entries = merge_index._prune_invalid_plugin_child_refs([plugin, skill, mcp, orphan])

        self.assertNotIn("orphan-child", {e["id"] for e in entries})
        self.assertEqual(plugin["bundle"]["bundled_skill_ids"], [None, "kept-skill"])
        self.assertEqual(plugin["bundle"]["bundled_mcp_ids"], [None, "kept-mcp"])


class TestSearchIndex(unittest.TestCase):
    """Tests for lightweight search index generation."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        for t in merge_index.TYPES:
            os.makedirs(os.path.join(self.tmpdir, t), exist_ok=True)
        self._orig_catalog_dir = merge_index.CATALOG_DIR
        merge_index.CATALOG_DIR = self.tmpdir

    def tearDown(self):
        merge_index.CATALOG_DIR = self._orig_catalog_dir

    def _write_index(self, type_name, entries, filename="index.json"):
        path = os.path.join(self.tmpdir, type_name, filename)
        with open(path, "w") as f:
            json.dump(entries, f)

    def _read_search_index(self):
        path = os.path.join(self.tmpdir, "search-index.json")
        with open(path) as f:
            return json.load(f)

    def _run_merge(self):
        with unittest.mock.patch("merge_index.enrich_entries") as mock_enrich, \
             unittest.mock.patch("merge_index.apply_governance") as mock_gov:
            mock_enrich.side_effect = lambda x: x
            mock_gov.side_effect = lambda x: x
            merge_index.merge()

    def test_search_index_generated(self):
        self._write_index(
            "mcp", [_make_entry("a", source_url="https://github.com/t/a")]
        )
        self._run_merge()
        path = os.path.join(self.tmpdir, "search-index.json")
        self.assertTrue(os.path.exists(path))

    def test_search_index_fields(self):
        self._write_index(
            "mcp", [_make_entry("a", source_url="https://github.com/t/a")]
        )
        self._run_merge()
        result = self._read_search_index()
        self.assertEqual(len(result), 1)
        expected_fields = {
            "id", "name", "type", "category", "tags", "tech_stack",
            "stars", "description", "description_zh", "source_url",
            "install_method", "final_score", "decision", "search_text",
            "freshness_label", "bundled_in", "source",
        }
        self.assertEqual(set(result[0].keys()), expected_fields)

    def test_search_index_carries_freshness_label(self):
        entry = _make_entry("a", source_url="https://github.com/t/a")
        entry["freshness_label"] = "active"
        self._write_index("mcp", [entry])
        self._run_merge()
        result = self._read_search_index()
        row = next(r for r in result if r["id"] == "a")
        self.assertEqual(row["freshness_label"], "active")

    def test_search_index_excludes_heavy_fields(self):
        entry = _make_entry("a", source_url="https://github.com/t/a")
        entry["evaluation"] = {"coding_relevance": 5}
        entry["health"] = {"score": 90}
        entry["added_at"] = "2026-01-01"
        self._write_index("mcp", [entry])
        self._run_merge()
        result = self._read_search_index()
        self.assertNotIn("evaluation", result[0])
        self.assertNotIn("health", result[0])
        self.assertNotIn("install", result[0])
        self.assertNotIn("added_at", result[0])
        # But lightweight scoring fields ARE included
        self.assertIn("final_score", result[0])
        self.assertIn("decision", result[0])

    def test_install_method_extracted(self):
        entry = _make_entry("a", source_url="https://github.com/t/a")
        entry["install"] = {"method": "mcp_config", "config": {"command": "npx"}}
        self._write_index("mcp", [entry])
        self._run_merge()
        result = self._read_search_index()
        self.assertEqual(result[0]["install_method"], "mcp_config")

    def test_install_method_null_when_missing(self):
        entry = _make_entry("a", source_url="https://github.com/t/a")
        entry.pop("install", None)
        self._write_index("mcp", [entry])
        self._run_merge()
        result = self._read_search_index()
        self.assertIsNone(result[0]["install_method"])

    def test_search_index_smaller_than_full(self):
        entries = [
            _make_entry(f"e{i}", source_url=f"https://github.com/t/e{i}")
            for i in range(50)
        ]
        # Add heavy metadata fields that exist in full index but are stripped
        # from search index, so the size ratio is realistic.
        for e in entries:
            e["evaluation"] = {"coding_relevance": 8, "content_quality": 7,
                               "specificity": 6, "composite_score": 70,
                               "reason": "x" * 200}
            e["health"] = {"popularity": 60, "freshness": 80, "quality": 70,
                           "installability": 50}
            e["readme_summary"] = "A" * 300
            e["install"] = {"method": "mcp_config", "config": {"command": "npx",
                            "args": ["@example/server"], "env": {"KEY": "val"}}}
        self._write_index("mcp", entries)
        self._run_merge()
        full_size = os.path.getsize(os.path.join(self.tmpdir, "index.json"))
        search_size = os.path.getsize(os.path.join(self.tmpdir, "search-index.json"))
        self.assertLess(search_size / full_size, 0.50)

    def test_search_index_preserves_order(self):
        entries = [
            _make_entry("high", stars=1000, source_url="https://github.com/t/high"),
            _make_entry("low", stars=1, source_url="https://github.com/t/low"),
        ]
        entries[0]["description"] = "A" * 100
        entries[0]["install"]["method"] = "mcp_config"
        self._write_index("mcp", entries)
        self._run_merge()
        result = self._read_search_index()
        self.assertEqual(result[0]["id"], "high")
        self.assertEqual(result[1]["id"], "low")


class TestGenericBundledChildSynthesis(unittest.TestCase):
    """Tests for synthesizing standalone command/subagent/evaluator/rule/template
    entries from a plugin bundle's position-aligned (<kind>_namespaces,
    <kind>_paths) pairs (merge_index._apply_bundled_in_annotations generic loop).
    """

    def _plugin_with_all_kinds(self):
        plugin = _make_entry(
            "cos-req",
            type="plugin",
            source_url="https://github.com/yhangf/csc-plugins/tree/main/cos-req",
        )
        plugin["final_score"] = 100
        plugin["bundle"] = {
            "evaluators_namespaces": ["cos-req:aireq-evaluator"],
            "evaluator_paths": ["cos-req-plugin/evaluators/aireq-evaluator/SKILL.md"],
            "commands_namespaces": ["cos-req:run"],
            "command_paths": ["cos-req-plugin/commands/run.md"],
            "agents_namespaces": ["cos-req:code-reviewer"],
            "agent_paths": ["cos-req-plugin/agents/code-reviewer.md"],
            "rules_namespaces": ["cos-req:dfx/安全"],
            "rule_paths": ["cos-req-plugin/rules/dfx/安全.md"],
            "templates_namespaces": ["cos-req:user-requirement-template"],
            "template_paths": ["cos-req-plugin/templates/user-requirement-template.md"],
            "plugin_root": "cos-req-plugin",
            "source_repo": "yhangf/csc-plugins",
            "source_ref": "main",
        }
        return plugin

    def test_synthesizes_one_entry_per_kind_with_correct_type(self):
        plugin = self._plugin_with_all_kinds()
        entries = [plugin]
        merge_index._apply_bundled_in_annotations(entries)

        by_source = {}
        for e in entries:
            src = e.get("source")
            if src and src.startswith("plugin-bundled-") and src != "plugin-bundled-skill":
                by_source.setdefault(src, []).append(e)

        # one of each generic kind
        self.assertEqual(set(by_source), {
            "plugin-bundled-evaluator",
            "plugin-bundled-command",
            "plugin-bundled-subagent",
            "plugin-bundled-rule",
            "plugin-bundled-template",
        })
        # catalog types map 1:1 (evaluator → skill, agent → subagent)
        self.assertEqual(by_source["plugin-bundled-evaluator"][0]["type"], "skill")
        self.assertEqual(by_source["plugin-bundled-command"][0]["type"], "command")
        self.assertEqual(by_source["plugin-bundled-subagent"][0]["type"], "subagent")
        self.assertEqual(by_source["plugin-bundled-rule"][0]["type"], "rule")
        self.assertEqual(by_source["plugin-bundled-template"][0]["type"], "template")
        # every synthesized child links back to the parent plugin
        for kids in by_source.values():
            self.assertEqual(kids[0]["bundled_in"], "cos-req")

    def test_source_path_is_plugin_root_relative_incl_nested_non_ascii(self):
        """OUTWARD source_path MUST be plugin-root relative (NO <plugin_root>/
        prefix) so it matches the archive-upload path root exactly; while
        install.path/files keep the FULL repo-relative path for content fetch."""
        plugin = self._plugin_with_all_kinds()
        entries = [plugin]
        merge_index._apply_bundled_in_annotations(entries)

        rule = next(e for e in entries if e.get("source") == "plugin-bundled-rule")
        # source_path: plugin-root relative, nested non-ASCII preserved, no prefix
        self.assertEqual(rule["source_path"], "rules/dfx/安全.md")
        self.assertNotIn("cos-req-plugin/", rule["source_path"])
        # install: still FULL repo-relative (download uses it for the raw URL)
        self.assertEqual(rule["install"]["method"], "git_clone")
        self.assertEqual(rule["install"]["path"], "cos-req-plugin/rules/dfx/安全.md")
        self.assertEqual(rule["install"]["files"], ["cos-req-plugin/rules/dfx/安全.md"])
        self.assertEqual(
            rule["install"]["repo"], "https://github.com/yhangf/csc-plugins.git"
        )
        self.assertEqual(rule["install"]["branch"], "main")

    def test_all_kinds_source_path_plugin_root_relative(self):
        """Every generic kind's source_path matches its archive-upload root."""
        plugin = self._plugin_with_all_kinds()
        entries = [plugin]
        merge_index._apply_bundled_in_annotations(entries)

        expected = {
            "plugin-bundled-evaluator": "evaluators/aireq-evaluator/SKILL.md",
            "plugin-bundled-command": "commands/run.md",
            "plugin-bundled-subagent": "agents/code-reviewer.md",
            "plugin-bundled-rule": "rules/dfx/安全.md",
            "plugin-bundled-template": "templates/user-requirement-template.md",
        }
        for src, want in expected.items():
            child = next(e for e in entries if e.get("source") == src)
            self.assertEqual(child["source_path"], want, src)
            self.assertFalse(
                child["source_path"].startswith("cos-req-plugin/"),
                f"{src} source_path still carries plugin_root prefix",
            )

    def test_evaluator_is_directory_install_like_skill(self):
        plugin = self._plugin_with_all_kinds()
        entries = [plugin]
        merge_index._apply_bundled_in_annotations(entries)

        ev = next(e for e in entries if e.get("source") == "plugin-bundled-evaluator")
        # directory kind: install.path is the parent dir (no /SKILL.md), no files
        # pin — and stays FULL repo-relative for the directory download.
        self.assertEqual(
            ev["install"]["path"], "cos-req-plugin/evaluators/aireq-evaluator"
        )
        self.assertNotIn("files", ev["install"])
        # OUTWARD source_path is plugin-root relative (matches archive root)
        self.assertEqual(
            ev["source_path"], "evaluators/aireq-evaluator/SKILL.md"
        )

    def test_synthetic_ids_kebab_round_trip_and_namespaced_by_kind(self):
        from utils import to_kebab_case

        # source tag → internal kind (note subagent's source tag != kind "agent").
        kind_by_source = {k.source: k.kind for k in merge_index._BUNDLED_CHILD_KINDS}

        plugin = self._plugin_with_all_kinds()
        entries = [plugin]
        merge_index._apply_bundled_in_annotations(entries)

        for e in entries:
            src = e.get("source") or ""
            if src not in kind_by_source:
                continue
            # id MUST round-trip under to_kebab_case (download writes folder =
            # to_kebab_case(id); web hub looks up by raw id).
            self.assertEqual(to_kebab_case(e["id"]), e["id"], e["id"])
            # kind is namespaced into the id so command/rule of same name differ
            self.assertIn(f"-{kind_by_source[src]}-", e["id"])

    def test_reverse_id_maps_written_per_kind(self):
        plugin = self._plugin_with_all_kinds()
        entries = [plugin]
        merge_index._apply_bundled_in_annotations(entries)

        bundle = plugin["bundle"]
        for field in (
            "bundled_evaluator_ids",
            "bundled_command_ids",
            "bundled_agent_ids",
            "bundled_rule_ids",
            "bundled_template_ids",
        ):
            self.assertIn(field, bundle)
            self.assertEqual(len(bundle[field]), 1)
            self.assertIsNotNone(bundle[field][0])

    def test_plugin_root_relative_helper(self):
        f = merge_index._plugin_root_relative
        # strips the <root>/ prefix (incl. nested non-ASCII tail)
        self.assertEqual(
            f("cos-req-plugin/rules/dfx/安全.md", "cos-req-plugin"),
            "rules/dfx/安全.md",
        )
        # tolerant of trailing/leading slashes on the root
        self.assertEqual(
            f("cos-req-plugin/templates/x.md", "/cos-req-plugin/"),
            "templates/x.md",
        )
        # defensive: path that doesn't start with root → unchanged
        self.assertEqual(f("rules/x.md", "cos-req-plugin"), "rules/x.md")
        # no/empty root → unchanged
        self.assertEqual(f("a/b.md", None), "a/b.md")
        self.assertEqual(f("a/b.md", ""), "a/b.md")
        # empty/None path passes through
        self.assertIsNone(f(None, "cos-req-plugin"))

    def test_synthesis_without_plugin_root_leaves_path_unchanged(self):
        """Defensive: if a bundle has no plugin_root, source_path is the repo
        path verbatim (back-compat; better than crashing)."""
        plugin = self._plugin_with_all_kinds()
        del plugin["bundle"]["plugin_root"]
        entries = [plugin]
        merge_index._apply_bundled_in_annotations(entries)
        rule = next(e for e in entries if e.get("source") == "plugin-bundled-rule")
        self.assertEqual(rule["source_path"], "cos-req-plugin/rules/dfx/安全.md")

    def test_missing_path_or_repo_records_none_and_does_not_synthesize(self):
        plugin = _make_entry("p", type="plugin", source_url="https://github.com/x/p")
        # rules declared but no rule_paths AND no source_repo → cannot synthesize
        plugin["bundle"] = {
            "rules_namespaces": ["p:ghost"],
            "rule_paths": [],
        }
        entries = [plugin]
        merge_index._apply_bundled_in_annotations(entries)

        self.assertEqual(
            [e for e in entries if e.get("source") == "plugin-bundled-rule"], []
        )
        self.assertEqual(plugin["bundle"]["bundled_rule_ids"], [None])

    def test_reused_generic_child_with_none_source_path_is_backfilled(self):
        """REGRESSION: a generic bundled child (rule/template/...) re-loaded from
        a prior index with source_path=None must be MATCHED (via the id fallback,
        since the path-key index skips None source_paths), BACKFILLED with the
        plugin-root-relative real path, and NOT duplicated."""
        plugin = self._plugin_with_all_kinds()
        # Pre-existing rule child WITHOUT source_path (id == deterministic
        # synthetic id for this plugin+kind+name).
        old_rule = _make_entry(
            "cos-req-rule-dfx安全", name="安全", type="rule",
            source_url="https://github.com/yhangf/csc-plugins/tree/main/cos-req-plugin/rules/dfx/安全.md",
        )
        old_rule["bundled_in"] = "cos-req"
        old_rule["source"] = "plugin-bundled-rule"
        old_rule["install"] = {
            "method": "git_clone",
            "repo": "https://github.com/yhangf/csc-plugins.git",
            "branch": "main",
            "path": "cos-req-plugin/rules/dfx/安全.md",
            "files": ["cos-req-plugin/rules/dfx/安全.md"],
        }
        # confirm the id matches what synthesis would derive
        self.assertEqual(
            old_rule["id"],
            merge_index._synthetic_child_id("cos-req", "rule", "dfx/安全", set()),
        )
        self.assertNotIn("source_path", old_rule)

        entries = [plugin, old_rule]
        merge_index._apply_bundled_in_annotations(entries)

        rules = [e for e in entries if e.get("source") == "plugin-bundled-rule"]
        # reused, not duplicated
        self.assertEqual(len(rules), 1)
        self.assertIs(rules[0], old_rule)
        # backfilled to the plugin-root-relative real (nested non-ASCII) path
        self.assertEqual(old_rule["source_path"], "rules/dfx/安全.md")
        # reverse map points at the reused id (not None / not a new id)
        self.assertEqual(plugin["bundle"]["bundled_rule_ids"], ["cos-req-rule-dfx安全"])


class TestSynthesizedChildrenReachTypeIndexes(unittest.TestCase):
    """CRITICAL regression guard for merge_index._sync_synthesized_children_to_type_indexes.

    The historical bug: the type-index sync hardcoded {"skills","mcp"} buckets,
    so any newly-synthesized child kind never reached its type index → the
    downloader skipped it → the bundle dropped it as an orphan, SILENTLY.
    These tests run the full merge() and assert every kind lands in its
    per-type index on disk.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        for t in merge_index.TYPES:
            os.makedirs(os.path.join(self.tmpdir, t), exist_ok=True)
        self._orig_catalog_dir = merge_index.CATALOG_DIR
        merge_index.CATALOG_DIR = self.tmpdir

    def tearDown(self):
        merge_index.CATALOG_DIR = self._orig_catalog_dir

    def _write_index(self, type_name, entries, filename="index.json"):
        os.makedirs(os.path.join(self.tmpdir, type_name), exist_ok=True)
        path = os.path.join(self.tmpdir, type_name, filename)
        with open(path, "w") as f:
            json.dump(entries, f)

    def _read_type_index(self, type_dir):
        path = os.path.join(self.tmpdir, type_dir, "index.json")
        if not os.path.exists(path):
            return []
        with open(path) as f:
            return json.load(f)

    def test_each_synthesized_kind_lands_in_its_type_index(self):
        plugin = _make_entry(
            "cos-req",
            type="plugin",
            source_url="https://github.com/yhangf/csc-plugins/tree/main/cos-req",
        )
        plugin["install"] = {
            "method": "plugin_marketplace",
            "marketplace_repo": "yhangf/csc-plugins",
            "marketplace_verified": True,
        }
        plugin["bundle"] = {
            "evaluators_namespaces": ["cos-req:aireq-evaluator"],
            "evaluator_paths": ["cos-req-plugin/evaluators/aireq-evaluator/SKILL.md"],
            "commands_namespaces": ["cos-req:run"],
            "command_paths": ["cos-req-plugin/commands/run.md"],
            "agents_namespaces": ["cos-req:code-reviewer"],
            "agent_paths": ["cos-req-plugin/agents/code-reviewer.md"],
            "rules_namespaces": ["cos-req:dfx/安全"],
            "rule_paths": ["cos-req-plugin/rules/dfx/安全.md"],
            "templates_namespaces": ["cos-req:user-requirement-template"],
            "template_paths": ["cos-req-plugin/templates/user-requirement-template.md"],
            "plugin_root": "cos-req-plugin",
            "source_repo": "yhangf/csc-plugins",
            "source_ref": "main",
        }
        self._write_index("plugins", [plugin])

        with unittest.mock.patch("merge_index.enrich_entries") as mock_enrich, \
             unittest.mock.patch("merge_index.apply_governance") as mock_gov:
            mock_enrich.side_effect = lambda x: x
            mock_gov.side_effect = lambda x: x
            merge_index.merge(verify_plugin_manifest=False)

        # evaluators are type=skill → skills/ index
        skills = self._read_type_index("skills")
        evaluator_ids = {
            e["id"] for e in skills if e.get("source") == "plugin-bundled-evaluator"
        }
        self.assertEqual(len(evaluator_ids), 1, "evaluator missing from skills/ index")

        # each single-file kind lands in its OWN type dir
        for type_dir, source_tag in (
            ("commands", "plugin-bundled-command"),
            ("subagents", "plugin-bundled-subagent"),
            ("rules", "plugin-bundled-rule"),
            ("templates", "plugin-bundled-template"),
        ):
            idx = self._read_type_index(type_dir)
            ids = {e["id"] for e in idx if e.get("source") == source_tag}
            self.assertEqual(
                len(ids), 1,
                f"{source_tag} child did not reach {type_dir}/index.json "
                f"(type-index bucket missing → would be silently dropped)",
            )

    def test_source_to_type_dir_covers_every_child_kind(self):
        """Static guard: every synthesized source tag has a type-dir bucket, so
        adding a kind to _BUNDLED_CHILD_KINDS without a bucket fails loudly."""
        for source in merge_index._PLUGIN_BUNDLED_SOURCES:
            self.assertIn(
                source, merge_index._SOURCE_TO_TYPE_DIR,
                f"source {source!r} has no type-dir bucket → children stranded",
            )

    def _plugin_index_payload(self):
        return {
            "id": "cos-req", "name": "cos-req", "type": "plugin",
            "description": "d",
            "source_url": "https://github.com/yhangf/csc-plugins/tree/main/cos-req",
            "stars": 1, "category": "tooling", "tags": [], "tech_stack": [],
            "install": {
                "method": "plugin_marketplace",
                "marketplace_repo": "yhangf/csc-plugins",
                "marketplace_verified": True,
            },
            "source": "csc-plugins", "last_synced": "2026-06-17", "final_score": 100,
            "bundle": {
                "rules_namespaces": ["cos-req:dfx/安全"],
                "rule_paths": ["cos-req-plugin/rules/dfx/安全.md"],
                "templates_namespaces": ["cos-req:tpl"],
                "template_paths": ["cos-req-plugin/templates/tpl.md"],
                "plugin_root": "cos-req-plugin",
                "source_repo": "yhangf/csc-plugins", "source_ref": "main",
            },
        }

    def test_rerunning_merge_does_not_duplicate_synthesized_children(self):
        """Re-running merge() re-loads the prior synthesized children from their
        type indexes; the synthesis pass MUST reuse (not re-mint) them, or each
        run accumulates duplicates."""
        os.environ["MERGE_INDEX_SKIP_PUSHED_AT_BACKFILL"] = "true"
        try:
            ids_per_run = []
            for _ in range(3):
                self._write_index("plugins", [self._plugin_index_payload()])
                with unittest.mock.patch("merge_index.enrich_entries") as me, \
                     unittest.mock.patch("merge_index.apply_governance") as mg:
                    me.side_effect = lambda x: x
                    mg.side_effect = lambda x: x
                    merge_index.merge(verify_plugin_manifest=False)
                top_path = os.path.join(self.tmpdir, "index.json")
                with open(top_path) as f:
                    top = json.load(f)
                ids = sorted(
                    e["id"] for e in top
                    if str(e.get("source", "")).startswith("plugin-bundled-")
                )
                ids_per_run.append(ids)
            # stable id set across runs
            self.assertEqual(ids_per_run[0], ids_per_run[1])
            self.assertEqual(ids_per_run[1], ids_per_run[2])
            # exactly one rule + one template synthesized, no accumulation
            self.assertEqual(len(ids_per_run[2]), 2)
            for td in ("rules", "templates"):
                idx = self._read_type_index(td)
                synth = [
                    e for e in idx
                    if str(e.get("source", "")).startswith("plugin-bundled-")
                ]
                self.assertEqual(len(synth), 1, f"{td} accumulated duplicates")
        finally:
            os.environ.pop("MERGE_INDEX_SKIP_PUSHED_AT_BACKFILL", None)


class _FakeLayout:
    """Minimal stand-in for ai_resource_eval.fetcher.plugin.PluginLayout.

    Only the two fields the gate reads (``is_plugin`` / ``fetch_error``) are
    modelled.
    """

    def __init__(self, is_plugin=True, fetch_error=None):
        self.is_plugin = is_plugin
        self.fetch_error = fetch_error


class _FakeFetcher:
    """Stand-in for PluginContentFetcher used by the manifest-gate tests.

    ``layouts`` maps ``"owner/repo"`` → ``_FakeLayout`` (or an exception
    instance to simulate ``detect_plugin_layout`` raising). Records each repo
    probed in ``self.calls`` so tests can assert the per-repo cache collapses
    duplicate probes. Never touches the network.
    """

    def __init__(self, layouts):
        self._layouts = layouts
        self.calls = []
        self.closed = False

    def detect_plugin_layout(self, repo, plugin_root="", ref="HEAD"):
        self.calls.append((repo, plugin_root, ref))
        result = self._layouts.get(repo)
        if isinstance(result, Exception):
            raise result
        if result is None:
            # Default: treat unknown repos as a clean "no plugin.json" detection.
            return _FakeLayout(is_plugin=False, fetch_error=None)
        return result

    def close(self):
        # Mirrors PluginContentFetcher.close(); the gate must call this to free
        # the underlying httpx.Client.
        self.closed = True


class TestPluginManifestGate(unittest.TestCase):
    """Tests for the central .claude-plugin/plugin.json existence gate added to
    merge_index.merge() — drops type=plugin entries whose repo genuinely lacks
    a plugin manifest, while failing open on Tree API wobble / no token /
    disabled gate.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        for t in merge_index.TYPES:
            os.makedirs(os.path.join(self.tmpdir, t), exist_ok=True)
        self._orig_catalog_dir = merge_index.CATALOG_DIR
        merge_index.CATALOG_DIR = self.tmpdir
        # Ensure the no-token fail-open path is deterministic regardless of CI env.
        self._orig_token = os.environ.pop("GITHUB_TOKEN", None)

    def tearDown(self):
        merge_index.CATALOG_DIR = self._orig_catalog_dir
        if self._orig_token is not None:
            os.environ["GITHUB_TOKEN"] = self._orig_token
        else:
            os.environ.pop("GITHUB_TOKEN", None)

    def _write_plugins(self, entries):
        path = os.path.join(self.tmpdir, "plugins", "index.json")
        with open(path, "w") as f:
            json.dump(entries, f)

    def _read_output(self):
        with open(os.path.join(self.tmpdir, "index.json")) as f:
            return json.load(f)

    @staticmethod
    def _plugin(id, *, repo, sub="", verified=True):
        """Build a fully install-valid plugin entry pointing at ``repo``.

        ``sub`` appends a /tree/HEAD/<sub> monorepo sub-path to the source_url.
        """
        url = f"https://github.com/{repo}"
        if sub:
            url = f"{url}/tree/HEAD/{sub}"
        e = _make_entry(id, type="plugin", source_url=url)
        e["install"] = {
            "method": "plugin_marketplace",
            "plugin_name": id,
            "marketplace_repo": repo,
            "marketplace_name": id,
            "marketplace_verified": verified,
            "marketplace": repo,
        }
        return e

    def _run(self, fetcher, *, verify=True):
        """Run merge() with the manifest fetcher injected (or default path).

        When ``fetcher`` is not None it's injected via patching
        _build_plugin_manifest_fetcher (bypassing the token check). When None,
        the real builder runs (no token in env → fail-open).
        """
        patches = [
            unittest.mock.patch("merge_index.enrich_entries", side_effect=lambda x: x),
            unittest.mock.patch("merge_index.apply_governance", side_effect=lambda x: x),
        ]
        if fetcher is not None:
            patches.append(
                unittest.mock.patch(
                    "merge_index._build_plugin_manifest_fetcher",
                    return_value=fetcher,
                )
            )
        with patches[0], patches[1]:
            if fetcher is not None:
                with patches[2]:
                    merge_index.merge(verify_plugin_manifest=verify)
            else:
                merge_index.merge(verify_plugin_manifest=verify)
        return self._read_output()

    def test_repo_with_plugin_json_kept(self):
        """is_plugin=True, fetch_error=None → entry retained."""
        fetcher = _FakeFetcher(
            {"anthropics/claude-plugins-official": _FakeLayout(is_plugin=True)}
        )
        self._write_plugins(
            [self._plugin("good", repo="anthropics/claude-plugins-official")]
        )
        result = self._run(fetcher)
        ids = {r["id"] for r in result if r.get("type") == "plugin"}
        self.assertEqual(ids, {"good"})

    def test_repo_without_plugin_json_dropped(self):
        """is_plugin=False, fetch_error=None → entry dropped."""
        fetcher = _FakeFetcher(
            {"someorg/skills-marketplace": _FakeLayout(is_plugin=False)}
        )
        self._write_plugins(
            [self._plugin("phantom", repo="someorg/skills-marketplace")]
        )
        with self.assertLogs("utils", level="WARNING") as cm:
            result = self._run(fetcher)
        ids = {r["id"] for r in result if r.get("type") == "plugin"}
        self.assertEqual(ids, set())
        self.assertTrue(
            any(
                "no .claude-plugin/plugin.json" in line and "phantom" in line
                for line in cm.output
            ),
            f"Expected drop WARNING for phantom; got: {cm.output}",
        )

    def test_tree_api_error_keeps_entry(self):
        """is_plugin=False but fetch_error set (Tree API wobble) → keep for retry."""
        fetcher = _FakeFetcher(
            {"flaky/repo": _FakeLayout(is_plugin=False, fetch_error="503")}
        )
        self._write_plugins([self._plugin("flaky", repo="flaky/repo")])
        result = self._run(fetcher)
        ids = {r["id"] for r in result if r.get("type") == "plugin"}
        self.assertEqual(ids, {"flaky"}, "Tree API error must NOT drop the entry")

    def test_detect_raises_keeps_entry(self):
        """detect_plugin_layout raising any exception → keep (fail-open)."""
        fetcher = _FakeFetcher({"boom/repo": RuntimeError("kaboom")})
        self._write_plugins([self._plugin("boom", repo="boom/repo")])
        result = self._run(fetcher)
        ids = {r["id"] for r in result if r.get("type") == "plugin"}
        self.assertEqual(ids, {"boom"})

    def test_verify_flag_false_skips_gate(self):
        """verify_plugin_manifest=False → no fetcher built, all entries kept."""
        # Even though this repo has no plugin.json, the gate is off so it stays.
        self._write_plugins(
            [self._plugin("kept", repo="someorg/skills-marketplace")]
        )
        # fetcher=None + verify=False: _build_plugin_manifest_fetcher is never
        # even reached for fetch; assert the entry survives.
        result = self._run(None, verify=False)
        ids = {r["id"] for r in result if r.get("type") == "plugin"}
        self.assertEqual(ids, {"kept"})

    def test_no_github_token_fail_open(self):
        """No GITHUB_TOKEN → fetcher is None → gate skipped, all entries kept."""
        # GITHUB_TOKEN already popped in setUp; run the REAL builder path.
        self._write_plugins(
            [self._plugin("kept", repo="someorg/skills-marketplace")]
        )
        result = self._run(None, verify=True)
        ids = {r["id"] for r in result if r.get("type") == "plugin"}
        self.assertEqual(ids, {"kept"})

    def test_non_github_source_url_kept(self):
        """Unparseable / non-GitHub source_url → cannot verify → keep."""
        fetcher = _FakeFetcher({})
        e = self._plugin("gitlab", repo="someorg/thing")
        e["source_url"] = "https://gitlab.com/someorg/thing"
        self._write_plugins([e])
        result = self._run(fetcher)
        ids = {r["id"] for r in result if r.get("type") == "plugin"}
        self.assertEqual(ids, {"gitlab"})
        self.assertEqual(fetcher.calls, [], "Non-GitHub URL must not be probed")

    def test_external_injected_entry_also_gated(self):
        """A type=plugin entry with NO sync-stage stamp (mimicking the
        github-trending external injection) is gated purely on source_url +
        repo contents — the gate does not look at any sync marker."""
        fetcher = _FakeFetcher(
            {"trendyorg/cool-sdk": _FakeLayout(is_plugin=False)}
        )
        # No bundle / sync fields — just install-valid + source_url, like an
        # entry merged in from the externally-injected github-trending source.
        injected = self._plugin("injected", repo="trendyorg/cool-sdk")
        injected.pop("source", None)
        injected.pop("last_synced", None)
        self._write_plugins([injected])
        result = self._run(fetcher)
        ids = {r["id"] for r in result if r.get("type") == "plugin"}
        self.assertEqual(ids, set(), "Externally-injected non-plugin must be dropped")

    def test_layout_cache_collapses_duplicate_repo_probes(self):
        """Two entries from the same (repo, ref, sub) → detect called once."""
        fetcher = _FakeFetcher(
            {"dup/repo": _FakeLayout(is_plugin=True)}
        )
        self._write_plugins(
            [
                self._plugin("a", repo="dup/repo"),
                self._plugin("b", repo="dup/repo"),
            ]
        )
        result = self._run(fetcher)
        ids = {r["id"] for r in result if r.get("type") == "plugin"}
        self.assertEqual(ids, {"a", "b"})
        probes = [c for c in fetcher.calls if c[0] == "dup/repo"]
        self.assertEqual(
            len(probes), 1,
            f"Expected one Tree probe for dup/repo (cache hit on second); got {probes}",
        )

    def test_fetcher_closed_after_gate(self):
        """The gate must close the fetcher (free its httpx.Client) when done."""
        fetcher = _FakeFetcher({"some/repo": _FakeLayout(is_plugin=True)})
        self._write_plugins([self._plugin("ok", repo="some/repo")])
        self._run(fetcher)
        self.assertTrue(
            fetcher.closed, "Manifest fetcher must be closed after the gate runs"
        )

    def test_fetcher_closed_even_when_probe_raises_in_loop(self):
        """A failure inside the validation loop still closes the fetcher.

        ``_repo_has_plugin_manifest`` is itself fail-open, so to force the loop
        to actually propagate an error we patch it to raise — the finally block
        must still close the fetcher (no leaked httpx.Client).
        """
        fetcher = _FakeFetcher({"some/repo": _FakeLayout(is_plugin=True)})
        self._write_plugins([self._plugin("ok", repo="some/repo")])

        with unittest.mock.patch(
            "merge_index.enrich_entries", side_effect=lambda x: x
        ), unittest.mock.patch(
            "merge_index.apply_governance", side_effect=lambda x: x
        ), unittest.mock.patch(
            "merge_index._build_plugin_manifest_fetcher", return_value=fetcher
        ), unittest.mock.patch(
            "merge_index._repo_has_plugin_manifest",
            side_effect=RuntimeError("boom in loop"),
        ):
            with self.assertRaises(RuntimeError):
                merge_index.merge(verify_plugin_manifest=True)
        self.assertTrue(
            fetcher.closed,
            "Fetcher must be closed via finally even when the loop raises",
        )


if __name__ == "__main__":
    unittest.main()
