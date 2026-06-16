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
            merge_index.merge()

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
            merge_index.merge()
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
            merge_index.merge()
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
            merge_index.merge()
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
        # reverse mapping backfilled with the synthetic id (not None)
        ids = plugin["bundle"]["bundled_skill_ids"]
        self.assertEqual(ids[0], "superpowers-brainstorming")
        self.assertEqual(ids[1], s["id"])
        self.assertIsNone(None if ids[1] else True)

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


if __name__ == "__main__":
    unittest.main()
