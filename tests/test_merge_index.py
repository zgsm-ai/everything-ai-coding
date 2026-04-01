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

    def test_health_score_present(self):
        entry = _make_entry("h1", source_url="https://github.com/t/h1")
        entry["stars"] = 1000
        entry["install"]["method"] = "mcp_config"
        entry["description"] = "A" * 100
        entry["evaluation"] = {
            "coding_relevance": 5,
            "content_quality": 5,
            "specificity": 5,
            "source_trust": 5,
            "confidence": 5,
        }
        self._write_index("mcp", [entry])

        with unittest.mock.patch("merge_index.enrich_entries") as mock_enrich:
            mock_enrich.side_effect = lambda x: x
            merge_index.merge()
        result = self._read_output()

        self.assertIn("health", result[0])
        self.assertIn("score", result[0]["health"])
        self.assertIn("signals", result[0]["health"])

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

    def test_sorted_by_health_desc(self):
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

    def test_evaluation_and_governance_applied(self):
        """Entries get evaluation and governance after merge."""
        entry = _make_entry("gov1", source_url="https://github.com/t/gov1")
        # Give it enough score heuristic points to pass the threshold of 40
        # stars gives popularity score. install method gives installability.
        # desc gives some quality.
        entry["stars"] = 1000
        entry["install"]["method"] = "mcp_config"
        entry["description"] = "A" * 100

        # We need an evaluation object since the threshold checks the final_score calculated from signals
        entry["evaluation"] = {
            "coding_relevance": 5,
            "content_quality": 5,
            "specificity": 5,
            "source_trust": 5,
            "confidence": 5,
        }
        self._write_index("mcp", [entry])

        with unittest.mock.patch("merge_index.enrich_entries") as mock_enrich:
            mock_enrich.side_effect = lambda x: x
            merge_index.merge()
        result = self._read_output()

        self.assertIn("evaluation", result[0])
        self.assertIn("health", result[0])

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


if __name__ == "__main__":
    unittest.main()
