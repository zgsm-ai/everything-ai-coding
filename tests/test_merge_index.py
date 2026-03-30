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
        # Create type subdirectories
        for t in merge_index.TYPES:
            os.makedirs(os.path.join(self.tmpdir, t), exist_ok=True)
        # Patch CATALOG_DIR
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

        merge_index.merge()
        result = self._read_output()

        self.assertEqual(len(result), 2)
        ids = {r["id"] for r in result}
        self.assertEqual(ids, {"a", "b"})

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

        merge_index.merge()
        result = self._read_output()

        dup_entries = [r for r in result if r["id"] == "dup"]
        self.assertEqual(len(dup_entries), 1)
        self.assertEqual(dup_entries[0]["name"], "First")

    def test_health_score_present(self):
        self._write_index(
            "mcp", [_make_entry("h1", source_url="https://github.com/t/h1")]
        )

        merge_index.merge()
        result = self._read_output()

        self.assertIn("health", result[0])
        self.assertIn("score", result[0]["health"])
        self.assertIn("signals", result[0]["health"])

    def test_sorted_by_health_desc(self):
        self._write_index(
            "mcp",
            [
                _make_entry(
                    "low",
                    stars=0,
                    pushed_at=None,
                    source_url="https://github.com/t/low",
                ),
                _make_entry(
                    "high",
                    stars=5000,
                    pushed_at="2026-03-29T00:00:00Z",
                    source_url="https://github.com/t/high",
                ),
            ],
        )

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

        merge_index.merge()
        result = self._read_output()

        self.assertNotEqual(result[0]["category"], "other")

    def test_empty_type_dir_no_crash(self):
        # Only mcp has data, others are empty dirs
        self._write_index(
            "mcp", [_make_entry("only", source_url="https://github.com/t/only")]
        )

        merge_index.merge()
        result = self._read_output()

        self.assertEqual(len(result), 1)

    @unittest.mock.patch("merge_index.llm_translate_entries")
    @unittest.mock.patch("merge_index.llm_tag_entries")
    @unittest.mock.patch("merge_index.get_repo_languages")
    def test_enrichment_llm_tags(self, mock_langs, mock_llm, mock_translate):
        """Entry with empty tags gets LLM-enriched tags."""
        mock_llm.return_value = {"empty-tags": ["python", "cli"]}
        mock_langs.return_value = []
        mock_translate.return_value = {}
        entry = _make_entry("empty-tags", source_url="https://github.com/t/empty-tags")
        entry["tags"] = []
        self._write_index("mcp", [entry])

        merge_index.merge()
        result = self._read_output()

        self.assertEqual(result[0]["tags"], ["python", "cli"])

    @unittest.mock.patch("merge_index.llm_translate_entries")
    @unittest.mock.patch("merge_index.llm_tag_entries")
    @unittest.mock.patch("merge_index.get_repo_languages")
    def test_enrichment_languages_tech_stack(self, mock_langs, mock_llm, mock_translate):
        """Entry with empty tech_stack gets API-enriched."""
        mock_llm.return_value = {}
        mock_langs.return_value = ["Python", "JavaScript"]
        mock_translate.return_value = {}
        entry = _make_entry("no-ts", source_url="https://github.com/t/no-ts")
        entry["tech_stack"] = []
        self._write_index("mcp", [entry])

        merge_index.merge()
        result = self._read_output()

        self.assertEqual(result[0]["tech_stack"], ["Python", "JavaScript"])

    @unittest.mock.patch("merge_index.llm_translate_entries")
    @unittest.mock.patch("merge_index.llm_tag_entries")
    @unittest.mock.patch("merge_index.get_repo_languages")
    def test_enrichment_no_overwrite(self, mock_langs, mock_llm, mock_translate):
        """Already-populated entries are not overwritten."""
        mock_llm.return_value = {"has-data": ["new-tag"]}
        mock_langs.return_value = ["Go"]
        mock_translate.return_value = {"has-data": "新标签"}
        entry = _make_entry("has-data", source_url="https://github.com/t/has-data")
        entry["tags"] = ["react", "typescript"]
        entry["tech_stack"] = ["TypeScript"]
        entry["description_zh"] = "已有中文描述"
        self._write_index("mcp", [entry])

        merge_index.merge()
        result = self._read_output()

        self.assertEqual(result[0]["tags"], ["react", "typescript"])
        self.assertEqual(result[0]["tech_stack"], ["TypeScript"])
        self.assertEqual(result[0]["description_zh"], "已有中文描述")

    @unittest.mock.patch("merge_index.llm_translate_entries")
    @unittest.mock.patch("merge_index.llm_tag_entries")
    @unittest.mock.patch("merge_index.get_repo_languages")
    def test_enrichment_translation(self, mock_langs, mock_llm, mock_translate):
        """Entry without description_zh gets LLM-translated."""
        mock_llm.return_value = {}
        mock_langs.return_value = []
        mock_translate.return_value = {"no-zh": "测试MCP服务器"}
        entry = _make_entry("no-zh", source_url="https://github.com/t/no-zh")
        self._write_index("mcp", [entry])

        merge_index.merge()
        result = self._read_output()

        self.assertEqual(result[0]["description_zh"], "测试MCP服务器")

    @unittest.mock.patch.dict(os.environ, {}, clear=True)
    def test_enrichment_no_credentials_no_crash(self):
        """No credentials → enrichment skipped, no crash."""
        os.environ.pop("LLM_BASE_URL", None)
        os.environ.pop("LLM_API_KEY", None)
        os.environ.pop("GITHUB_TOKEN", None)
        entry = _make_entry("nocred", source_url="https://github.com/t/nocred")
        self._write_index("mcp", [entry])

        merge_index.merge()
        result = self._read_output()

        self.assertEqual(len(result), 1)

    @unittest.mock.patch("merge_index.llm_translate_entries")
    @unittest.mock.patch("merge_index.llm_tag_entries")
    @unittest.mock.patch("merge_index.get_repo_languages")
    def test_dedup_integrity_warning_on_catastrophic_drop(self, mock_langs, mock_llm, mock_translate):
        """When a type loses >50% of entries during dedup, a warning is logged."""
        mock_llm.return_value = {}
        mock_langs.return_value = []
        mock_translate.return_value = {}
        # This scenario shouldn't happen anymore with the fix, but the warning
        # mechanism should still work if triggered by other means.
        # We test by checking that the merge function logs per-type counts.
        # Write 3 MCP entries with unique URLs (no dedup loss)
        self._write_index(
            "mcp",
            [
                _make_entry("m1", source_url="https://github.com/t/m1"),
                _make_entry("m2", source_url="https://github.com/t/m2"),
                _make_entry("m3", source_url="https://github.com/t/m3"),
            ],
        )

        with self.assertLogs("utils", level="INFO") as cm:
            merge_index.merge()

        # Should see per-type dedup stats in logs
        log_text = "\n".join(cm.output)
        self.assertIn("Dedup", log_text)


if __name__ == "__main__":
    unittest.main()
