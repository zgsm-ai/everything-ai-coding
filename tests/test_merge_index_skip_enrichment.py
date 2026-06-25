"""Tests for merge_index.py --skip-enrichment CLI flag.

Covers Chunk 2A of the harden-merge-pipeline change: data-only catalog
emission when LLM enrichment is deferred to a separate per-type job.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

SCRIPTS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "scripts")
)
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


class TestMergeIndexSkipEnrichment(unittest.TestCase):
    """merge_index.py --skip-enrichment skips LLM eval and emits empty
    evaluation placeholder so a downstream aggregate job can fill it in.
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
        path = os.path.join(self.tmpdir, type_name, filename)
        with open(path, "w") as f:
            json.dump(entries, f)

    def _read_output(self):
        path = os.path.join(self.tmpdir, "index.json")
        with open(path) as f:
            return json.load(f)

    def test_skip_enrichment_does_not_call_enrich_entries(self):
        """With --skip-enrichment, enrich_entries must never be called."""
        self._write_index(
            "mcp", [_make_entry("a", source_url="https://github.com/t/a")]
        )
        with unittest.mock.patch("merge_index.enrich_entries") as mock_enrich:
            mock_enrich.side_effect = lambda x: x
            merge_index.merge(skip_enrichment=True)
        mock_enrich.assert_not_called()

    def test_skip_enrichment_writes_empty_evaluation(self):
        """Every output entry has evaluation == {} (empty dict, not missing)."""
        self._write_index(
            "mcp",
            [
                _make_entry("a", source_url="https://github.com/t/a"),
                _make_entry(
                    "b",
                    type="skill",
                    source_url="https://github.com/t/b",
                ),
            ],
        )
        with unittest.mock.patch("merge_index.enrich_entries"):
            merge_index.merge(skip_enrichment=True)
        result = self._read_output()
        self.assertEqual(len(result), 2)
        for entry in result:
            self.assertIn("evaluation", entry)
            self.assertEqual(
                entry["evaluation"],
                {},
                f"entry {entry.get('id')} has non-empty evaluation: "
                f"{entry['evaluation']!r}",
            )
            # Promoted defaults must still match the safe placeholder
            self.assertEqual(entry["final_score"], 0)
            self.assertEqual(entry["decision"], "review")

    def test_skip_enrichment_clears_prior_evaluation_overlay(self):
        """A prior evaluation overlay from existing index.json must not leak
        into a skip-enrichment run; the data-only catalog stays clean."""
        self._write_index(
            "mcp", [_make_entry("a", source_url="https://github.com/t/a")]
        )
        # Seed a prior catalog/index.json with a populated evaluation
        prior = [
            {
                "id": "a",
                "type": "mcp",
                "source_url": "https://github.com/t/a",
                "evaluation": {
                    "final_score": 87,
                    "decision": "accept",
                    "evaluated_at": "2026-03-01T00:00:00Z",
                },
            }
        ]
        with open(os.path.join(self.tmpdir, "index.json"), "w") as f:
            json.dump(prior, f)

        with unittest.mock.patch("merge_index.enrich_entries"):
            merge_index.merge(skip_enrichment=True)
        result = self._read_output()
        target = next(r for r in result if r["id"] == "a")
        self.assertEqual(target["evaluation"], {})
        self.assertNotIn("_prior_evaluation", target)
        self.assertEqual(target["final_score"], 0)
        self.assertEqual(target["decision"], "review")

    def test_no_flag_calls_enrich_entries(self):
        """Default behavior (skip_enrichment=False) calls enrich_entries once."""
        self._write_index(
            "mcp", [_make_entry("a", source_url="https://github.com/t/a")]
        )
        with unittest.mock.patch("merge_index.enrich_entries") as mock_enrich, \
                unittest.mock.patch("merge_index.apply_governance") as mock_gov:
            mock_enrich.side_effect = lambda x: x
            mock_gov.side_effect = lambda x, **kwargs: x
            merge_index.merge()
        self.assertEqual(mock_enrich.call_count, 1)

    def test_apply_governance_invoked_with_health_only_true(self):
        """skip_enrichment=True must propagate health_only=True to governance."""
        self._write_index(
            "mcp", [_make_entry("a", source_url="https://github.com/t/a")]
        )
        with unittest.mock.patch("merge_index.enrich_entries"), \
                unittest.mock.patch("merge_index.apply_governance") as mock_gov:
            mock_gov.side_effect = lambda x, **kwargs: x
            merge_index.merge(skip_enrichment=True)
        mock_gov.assert_called_once()
        # Either kwarg or positional — accept both
        call = mock_gov.call_args
        health_only = call.kwargs.get("health_only")
        if health_only is None and len(call.args) >= 2:
            health_only = call.args[1]
        self.assertTrue(health_only)

    def test_apply_governance_invoked_without_health_only_by_default(self):
        """Default mode must NOT pass health_only kwarg, so legacy mocks of
        apply_governance(x) (single-positional) continue to work."""
        self._write_index(
            "mcp", [_make_entry("a", source_url="https://github.com/t/a")]
        )
        with unittest.mock.patch("merge_index.enrich_entries"), \
                unittest.mock.patch("merge_index.apply_governance") as mock_gov:
            mock_gov.side_effect = lambda x: x
            merge_index.merge()
        mock_gov.assert_called_once()
        call = mock_gov.call_args
        # Default path: no health_only kwarg passed (backwards compatible)
        self.assertNotIn("health_only", call.kwargs)
        self.assertEqual(len(call.args), 1)

    def test_main_dispatches_skip_enrichment(self):
        """CLI main(['--skip-enrichment']) propagates the flag to merge()."""
        with unittest.mock.patch("merge_index.merge") as mock_merge:
            merge_index.main(["--skip-enrichment"])
        # main() also forwards the plugin-manifest gate flag (on by default).
        mock_merge.assert_called_once_with(
            skip_enrichment=True, verify_plugin_manifest=True
        )

    def test_main_default_no_skip(self):
        """CLI main([]) calls merge with skip_enrichment=False."""
        with unittest.mock.patch("merge_index.merge") as mock_merge:
            merge_index.main([])
        mock_merge.assert_called_once_with(
            skip_enrichment=False, verify_plugin_manifest=True
        )

    def test_cli_help_shows_flag(self):
        """`python scripts/merge_index.py --help` advertises --skip-enrichment."""
        repo_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..")
        )
        result = subprocess.run(
            [sys.executable, "scripts/merge_index.py", "--help"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--skip-enrichment", result.stdout)


class TestScoringGovernorHealthOnly(unittest.TestCase):
    """apply_governance(health_only=True) — direct unit tests on the governor."""

    def test_health_only_clears_evaluation(self):
        from scoring_governor import apply_governance

        entries = [
            {
                "id": "a",
                "type": "mcp",
                "evaluation": {"final_score": 90, "decision": "accept"},
                "health": {"freshness_label": "fresh"},
            },
            {
                "id": "b",
                "type": "skill",
                "evaluation": {"final_score": 10, "decision": "reject"},
            },
        ]
        result = apply_governance(entries, health_only=True)
        # Both entries pass through (no reject filter in health-only mode)
        self.assertEqual(len(result), 2)
        for entry in result:
            self.assertEqual(entry["evaluation"], {})
            self.assertEqual(entry["final_score"], 0)
            self.assertEqual(entry["decision"], "review")
            self.assertEqual(entry["weak_dims"], [])
        # freshness_label still surfaced from health.{}
        self.assertEqual(result[0].get("freshness_label"), "fresh")

    def test_default_mode_unchanged(self):
        """health_only=False (default) preserves the existing behavior."""
        from scoring_governor import apply_governance

        entries = [
            {
                "id": "a",
                "type": "mcp",
                "evaluation": {"final_score": 90, "decision": "accept"},
            }
        ]
        result = apply_governance(entries)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["final_score"], 90)
        self.assertEqual(result[0]["decision"], "accept")


if __name__ == "__main__":
    unittest.main()
