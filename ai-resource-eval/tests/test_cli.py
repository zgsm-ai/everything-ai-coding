"""Tests for ai_resource_eval.cli — CLI commands via typer CliRunner.

Tests cover:
- run: argument parsing, missing args, API key requirement, full pipeline (mocked)
- review: argument parsing, interactive review (mocked input)
- ls: metrics and tasks listing
- report: markdown and json output, empty results
- cache stats: display statistics
- cache clear: clear expired and all
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from ai_resource_eval.cli import app


runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_catalog_items(count: int = 3) -> list[dict]:
    """Build a list of minimal catalog entry dicts."""
    return [
        {
            "id": f"item-{i}",
            "name": f"Test Resource {i}",
            "source_url": f"https://github.com/owner/repo-{i}",
            "description": f"Description for item {i}",
            "stars": 100 + i,
        }
        for i in range(count)
    ]


def _make_results(count: int = 3) -> list[dict]:
    """Build a list of result dicts for report testing."""
    decisions = ["accept", "review", "reject"]
    return [
        {
            "entry_id": f"item-{i}",
            "metrics": {
                "coding_relevance": {"score": 4, "evidence": [], "missing": [], "suggestion": ""},
                "doc_completeness": {"score": 3, "evidence": [], "missing": [], "suggestion": ""},
            },
            "health": {"freshness": 0, "popularity": 0, "source_trust": 0},
            "final_score": 40 + i * 20,
            "decision": decisions[i % 3],
            "star_weight": 1.0,
            "content_hash": f"hash{i}",
            "rubric_version": "1.abc12345",
            "model_id": "test-model",
            "evaluated_at": "2026-01-01T00:00:00Z",
        }
        for i in range(count)
    ]


# ===================================================================
# run command
# ===================================================================


class TestRunCommand:
    """Test the 'run' command argument parsing and execution."""

    def test_run_missing_required_args(self):
        """run without --task and --input should fail."""
        result = runner.invoke(app, ["run"])
        assert result.exit_code != 0

    def test_run_missing_task(self, tmp_path):
        """run without --task should fail."""
        input_file = tmp_path / "input.json"
        input_file.write_text("[]")
        result = runner.invoke(app, ["run", "--input", str(input_file)])
        assert result.exit_code != 0

    def test_run_missing_input(self):
        """run without --input should fail."""
        result = runner.invoke(app, ["run", "--task", "skill"])
        assert result.exit_code != 0

    def test_run_missing_api_key(self, tmp_path):
        """run without JUDGE_API_KEY should fail with exit code 1."""
        input_file = tmp_path / "input.json"
        input_file.write_text(json.dumps(_make_catalog_items()))

        result = runner.invoke(
            app,
            ["run", "--task", "skill", "--input", str(input_file)],
            env={"JUDGE_API_KEY": "", "LLM_API_KEY": ""},
        )
        assert result.exit_code == 1
        assert "API_KEY" in result.output

    def test_run_input_file_not_found(self, tmp_path):
        """run with non-existent input file should fail."""
        result = runner.invoke(
            app,
            [
                "run",
                "--task", "skill",
                "--input", str(tmp_path / "nonexistent.json"),
            ],
            env={"JUDGE_API_KEY": "test-key"},
        )
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_run_invalid_json_input(self, tmp_path):
        """run with invalid JSON input should fail."""
        input_file = tmp_path / "input.json"
        input_file.write_text("not valid json{{{")

        result = runner.invoke(
            app,
            ["run", "--task", "skill", "--input", str(input_file)],
            env={"JUDGE_API_KEY": "test-key"},
        )
        assert result.exit_code == 1

    def test_run_non_array_json(self, tmp_path):
        """run with non-array JSON should fail."""
        input_file = tmp_path / "input.json"
        input_file.write_text('{"not": "an array"}')

        result = runner.invoke(
            app,
            ["run", "--task", "skill", "--input", str(input_file)],
            env={"JUDGE_API_KEY": "test-key"},
        )
        assert result.exit_code == 1
        assert "array" in result.output

    @patch("ai_resource_eval.runner.EvalRunner")
    def test_run_full_pipeline(self, MockRunner, tmp_path):
        """run with valid args executes the full pipeline."""
        # Setup
        input_file = tmp_path / "input.json"
        input_file.write_text(json.dumps(_make_catalog_items(2)))
        output_file = tmp_path / "results.json"

        # Mock the runner
        mock_instance = MagicMock()
        mock_instance.run.return_value = []
        mock_instance.review_queue = []
        MockRunner.return_value = mock_instance

        result = runner.invoke(
            app,
            [
                "run",
                "--task", "skill",
                "--input", str(input_file),
                "--output", str(output_file),
                "--judge", "deepseek",
                "--concurrency", "2",
                "--incremental",
                "--no-interactive",
                "--on-fail", "queue",
                "--cache-dir", str(tmp_path / "cache"),
            ],
            env={"JUDGE_API_KEY": "test-key-123"},
        )

        assert result.exit_code == 0
        MockRunner.assert_called_once()
        call_kwargs = MockRunner.call_args[1]
        assert call_kwargs["concurrency"] == 2
        assert call_kwargs["incremental"] is True
        assert call_kwargs["interactive"] is False
        assert call_kwargs["on_fail"] == "queue"
        assert call_kwargs["cache_dir"] == str(tmp_path / "cache")

    @patch("ai_resource_eval.runner.EvalRunner")
    def test_run_writes_output_file(self, MockRunner, tmp_path):
        """run writes results to the output file."""
        input_file = tmp_path / "input.json"
        input_file.write_text(json.dumps(_make_catalog_items(1)))
        output_file = tmp_path / "results.json"

        mock_instance = MagicMock()
        mock_result = MagicMock()
        mock_result.model_dump.return_value = {"entry_id": "item-0", "final_score": 75}
        mock_instance.run.return_value = [mock_result]
        mock_instance.review_queue = []
        MockRunner.return_value = mock_instance

        result = runner.invoke(
            app,
            [
                "run",
                "--task", "skill",
                "--input", str(input_file),
                "--output", str(output_file),
            ],
            env={"JUDGE_API_KEY": "test-key"},
        )

        assert result.exit_code == 0
        assert output_file.exists()
        written = json.loads(output_file.read_text())
        assert len(written) == 1
        assert written[0]["entry_id"] == "item-0"

    @patch("ai_resource_eval.runner.EvalRunner")
    def test_run_writes_review_queue(self, MockRunner, tmp_path):
        """run writes review_queue.json when there are queued entries."""
        input_file = tmp_path / "input.json"
        input_file.write_text(json.dumps(_make_catalog_items(1)))
        output_file = tmp_path / "results.json"

        mock_instance = MagicMock()
        mock_instance.run.return_value = []
        mock_instance.review_queue = [{"id": "queued-1", "_review_reason": "fetch_failed"}]
        MockRunner.return_value = mock_instance

        result = runner.invoke(
            app,
            [
                "run",
                "--task", "skill",
                "--input", str(input_file),
                "--output", str(output_file),
                "--on-fail", "queue",
            ],
            env={"JUDGE_API_KEY": "test-key"},
        )

        assert result.exit_code == 0
        queue_path = tmp_path / "review_queue.json"
        assert queue_path.exists()
        queued = json.loads(queue_path.read_text())
        assert len(queued) == 1
        assert queued[0]["id"] == "queued-1"

    @patch("ai_resource_eval.runner.EvalRunner")
    def test_run_stdout_when_no_output(self, MockRunner, tmp_path):
        """run outputs to stdout when --output is not specified."""
        input_file = tmp_path / "input.json"
        input_file.write_text(json.dumps(_make_catalog_items(1)))

        mock_instance = MagicMock()
        mock_result = MagicMock()
        mock_result.model_dump.return_value = {"entry_id": "item-0"}
        mock_instance.run.return_value = [mock_result]
        mock_instance.review_queue = []
        MockRunner.return_value = mock_instance

        result = runner.invoke(
            app,
            [
                "run",
                "--task", "skill",
                "--input", str(input_file),
            ],
            env={"JUDGE_API_KEY": "test-key"},
        )

        assert result.exit_code == 0
        # stdout should contain JSON
        assert "item-0" in result.output

    def test_run_invalid_task_name(self, tmp_path):
        """run with non-existent task name should fail."""
        input_file = tmp_path / "input.json"
        input_file.write_text(json.dumps(_make_catalog_items()))

        result = runner.invoke(
            app,
            [
                "run",
                "--task", "nonexistent_task_xyz",
                "--input", str(input_file),
            ],
            env={"JUDGE_API_KEY": "test-key"},
        )
        assert result.exit_code == 1


# ===================================================================
# review command
# ===================================================================


class TestReviewCommand:
    """Test the 'review' command."""

    def test_review_missing_queue(self):
        """review without --queue should fail."""
        result = runner.invoke(app, ["review"])
        assert result.exit_code != 0

    def test_review_nonexistent_queue(self, tmp_path):
        """review with non-existent queue file should fail."""
        result = runner.invoke(
            app,
            ["review", "--queue", str(tmp_path / "nonexistent.json")],
        )
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_review_empty_queue(self, tmp_path):
        """review with empty array should exit gracefully."""
        queue_file = tmp_path / "queue.json"
        queue_file.write_text("[]")

        result = runner.invoke(
            app,
            ["review", "--queue", str(queue_file)],
        )
        assert result.exit_code == 0
        assert "No items" in result.output

    def test_review_invalid_json(self, tmp_path):
        """review with invalid JSON should fail."""
        queue_file = tmp_path / "queue.json"
        queue_file.write_text("not json!")

        result = runner.invoke(
            app,
            ["review", "--queue", str(queue_file)],
        )
        assert result.exit_code == 1

    @patch("typer.prompt")
    def test_review_interactive(self, mock_prompt, tmp_path):
        """review displays items and writes reviewed output."""
        queue_file = tmp_path / "queue.json"
        items = [
            {
                "id": "review-1",
                "name": "Test Item",
                "source_url": "https://github.com/test/repo",
                "description": "A test item",
                "_review_reason": "fetch_failed",
            }
        ]
        queue_file.write_text(json.dumps(items))

        mock_prompt.return_value = "accept"

        result = runner.invoke(
            app,
            ["review", "--queue", str(queue_file)],
        )

        assert result.exit_code == 0
        assert "Review Queue" in result.output

        # Check reviewed output
        reviewed_path = tmp_path / f"reviewed_{queue_file.name}"
        assert reviewed_path.exists()
        reviewed = json.loads(reviewed_path.read_text())
        assert len(reviewed) == 1
        assert reviewed[0]["_review_decision"] == "accept"


# ===================================================================
# ls command
# ===================================================================


class TestLsCommand:
    """Test the 'ls' command."""

    def test_ls_missing_target(self):
        """ls without argument should fail."""
        result = runner.invoke(app, ["ls"])
        assert result.exit_code != 0

    def test_ls_invalid_target(self):
        """ls with invalid target should fail."""
        result = runner.invoke(app, ["ls", "invalid_target"])
        assert result.exit_code != 0

    def test_ls_metrics(self):
        """ls metrics should list all registered metrics."""
        result = runner.invoke(app, ["ls", "metrics"])

        assert result.exit_code == 0
        assert "Registered Metrics" in result.output
        # Check for known metrics
        assert "coding_relevance" in result.output
        assert "doc_completeness" in result.output
        assert "desc_accuracy" in result.output
        assert "writing_quality" in result.output
        assert "specificity" in result.output
        assert "install_clarity" in result.output
        assert "6 metrics registered" in result.output

    def test_ls_tasks(self):
        """ls tasks should list available task YAML files."""
        result = runner.invoke(app, ["ls", "tasks"])

        assert result.exit_code == 0
        # Rich table title may be split across lines; check for key content
        assert "tasks available" in result.output
        # Check for known tasks
        assert "skill" in result.output
        assert "mcp_server" in result.output


# ===================================================================
# report command
# ===================================================================


class TestReportCommand:
    """Test the 'report' command."""

    def test_report_missing_input(self):
        """report without --input should fail."""
        result = runner.invoke(app, ["report"])
        assert result.exit_code != 0

    def test_report_nonexistent_input(self, tmp_path):
        """report with non-existent input file should fail."""
        result = runner.invoke(
            app,
            ["report", "--input", str(tmp_path / "nonexistent.json")],
        )
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_report_markdown_default(self, tmp_path):
        """report generates markdown by default."""
        results_file = tmp_path / "results.json"
        results_file.write_text(json.dumps(_make_results()))

        result = runner.invoke(
            app,
            ["report", "--input", str(results_file)],
        )

        assert result.exit_code == 0
        assert "# Evaluation Report" in result.output
        assert "Decision Distribution" in result.output
        assert "Score Histogram" in result.output
        assert "accept" in result.output

    def test_report_json_format(self, tmp_path):
        """report with --format json outputs valid JSON."""
        results_file = tmp_path / "results.json"
        results_file.write_text(json.dumps(_make_results()))

        result = runner.invoke(
            app,
            ["report", "--input", str(results_file), "--format", "json"],
        )

        assert result.exit_code == 0
        stats = json.loads(result.output)
        assert "total" in stats
        assert stats["total"] == 3
        assert "decisions" in stats
        assert "score_histogram" in stats
        assert "score_stats" in stats
        assert "metric_averages" in stats

    def test_report_empty_results(self, tmp_path):
        """report with empty results array produces a valid report."""
        results_file = tmp_path / "results.json"
        results_file.write_text("[]")

        result = runner.invoke(
            app,
            ["report", "--input", str(results_file)],
        )

        assert result.exit_code == 0
        assert "Total entries evaluated" in result.output

    def test_report_decision_counts(self, tmp_path):
        """report correctly counts decisions."""
        results = _make_results(6)  # 2 accept, 2 review, 2 reject
        results_file = tmp_path / "results.json"
        results_file.write_text(json.dumps(results))

        result = runner.invoke(
            app,
            ["report", "--input", str(results_file), "--format", "json"],
        )

        assert result.exit_code == 0
        stats = json.loads(result.output)
        assert stats["decisions"]["accept"] == 2
        assert stats["decisions"]["review"] == 2
        assert stats["decisions"]["reject"] == 2

    def test_report_score_stats(self, tmp_path):
        """report computes correct score statistics."""
        results = [
            {"entry_id": "a", "final_score": 20, "decision": "reject", "metrics": {}},
            {"entry_id": "b", "final_score": 60, "decision": "review", "metrics": {}},
            {"entry_id": "c", "final_score": 80, "decision": "accept", "metrics": {}},
        ]
        results_file = tmp_path / "results.json"
        results_file.write_text(json.dumps(results))

        result = runner.invoke(
            app,
            ["report", "--input", str(results_file), "--format", "json"],
        )

        assert result.exit_code == 0
        stats = json.loads(result.output)
        assert stats["score_stats"]["mean"] == pytest.approx(53.33, abs=0.01)
        assert stats["score_stats"]["min"] == 20.0
        assert stats["score_stats"]["max"] == 80.0

    def test_report_invalid_json(self, tmp_path):
        """report with invalid JSON should fail."""
        results_file = tmp_path / "results.json"
        results_file.write_text("not json!")

        result = runner.invoke(
            app,
            ["report", "--input", str(results_file)],
        )
        assert result.exit_code == 1


# ===================================================================
# cache stats command
# ===================================================================


class TestCacheStatsCommand:
    """Test the 'cache stats' command."""

    def test_cache_stats_no_db(self, tmp_path):
        """cache stats with no database should exit gracefully."""
        result = runner.invoke(
            app,
            ["cache", "stats", "--cache-dir", str(tmp_path / "no_cache")],
        )
        assert result.exit_code == 0
        assert "No cache database" in result.output

    def test_cache_stats_with_db(self, tmp_path):
        """cache stats displays statistics from an existing database."""
        from ai_resource_eval.cache import CacheEntry, EvalCache

        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        cache = EvalCache(db_path=cache_dir / "eval_cache.db")

        # Add a test entry
        entry = CacheEntry(
            cache_key="test_key",
            entry_id="test-1",
            content_hash="hash123",
            rubric_version="1.abc",
            result_json='{"test": true}',
            evaluated_at="2026-01-01T00:00:00Z",
            expires_at="2027-01-01T00:00:00Z",
            model_id="test-model",
            prompt_tokens=100,
            completion_tokens=50,
            cost_usd=0.005,
        )
        cache.put("test_key", entry)
        cache.close()

        result = runner.invoke(
            app,
            ["cache", "stats", "--cache-dir", str(cache_dir)],
        )

        assert result.exit_code == 0
        assert "Cache Statistics" in result.output
        assert "1" in result.output  # entries count


# ===================================================================
# cache clear command
# ===================================================================


class TestCacheClearCommand:
    """Test the 'cache clear' command."""

    def test_cache_clear_no_db(self, tmp_path):
        """cache clear with no database should exit gracefully."""
        result = runner.invoke(
            app,
            ["cache", "clear", "--cache-dir", str(tmp_path / "no_cache")],
        )
        assert result.exit_code == 0
        assert "No cache database" in result.output

    def test_cache_clear_expired(self, tmp_path):
        """cache clear --expired removes only expired entries."""
        from ai_resource_eval.cache import CacheEntry, EvalCache

        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        cache = EvalCache(db_path=cache_dir / "eval_cache.db")

        # Add an expired entry
        expired_entry = CacheEntry(
            cache_key="expired_key",
            entry_id="expired-1",
            content_hash="hash1",
            rubric_version="1.abc",
            result_json='{}',
            evaluated_at="2020-01-01T00:00:00Z",
            expires_at="2020-01-02T00:00:00Z",  # long expired
            cost_usd=0.001,
        )
        cache.put("expired_key", expired_entry)

        # Add a valid entry
        valid_entry = CacheEntry(
            cache_key="valid_key",
            entry_id="valid-1",
            content_hash="hash2",
            rubric_version="1.abc",
            result_json='{}',
            evaluated_at="2026-01-01T00:00:00Z",
            expires_at="2027-01-01T00:00:00Z",  # far future
            cost_usd=0.002,
        )
        cache.put("valid_key", valid_entry)
        cache.close()

        result = runner.invoke(
            app,
            ["cache", "clear", "--expired", "--cache-dir", str(cache_dir)],
        )

        assert result.exit_code == 0
        assert "expired" in result.output.lower()

        # Verify valid entry still exists
        cache2 = EvalCache(db_path=cache_dir / "eval_cache.db")
        stats = cache2.stats()
        assert stats["entries"] == 1
        cache2.close()

    def test_cache_clear_all(self, tmp_path):
        """cache clear without --expired removes all entries."""
        from ai_resource_eval.cache import CacheEntry, EvalCache

        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        cache = EvalCache(db_path=cache_dir / "eval_cache.db")

        entry = CacheEntry(
            cache_key="key1",
            entry_id="entry-1",
            content_hash="hash",
            rubric_version="1.abc",
            result_json='{}',
            evaluated_at="2026-01-01T00:00:00Z",
            expires_at="2027-01-01T00:00:00Z",
            cost_usd=0.001,
        )
        cache.put("key1", entry)
        cache.close()

        result = runner.invoke(
            app,
            ["cache", "clear", "--cache-dir", str(cache_dir)],
        )

        assert result.exit_code == 0
        assert "Cleared all" in result.output

        # Verify empty
        cache2 = EvalCache(db_path=cache_dir / "eval_cache.db")
        stats = cache2.stats()
        assert stats["entries"] == 0
        cache2.close()


# ===================================================================
# Help output
# ===================================================================


class TestHelpOutput:
    """Test that --help works for all commands."""

    def test_main_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "ai-resource-eval" in result.output.lower() or "evaluation" in result.output.lower()

    def test_run_help(self):
        result = runner.invoke(app, ["run", "--help"])
        assert result.exit_code == 0
        assert "--task" in result.output
        assert "--input" in result.output

    def test_review_help(self):
        result = runner.invoke(app, ["review", "--help"])
        assert result.exit_code == 0
        assert "--queue" in result.output

    def test_ls_help(self):
        result = runner.invoke(app, ["ls", "--help"])
        assert result.exit_code == 0

    def test_report_help(self):
        result = runner.invoke(app, ["report", "--help"])
        assert result.exit_code == 0
        assert "--input" in result.output
        assert "--format" in result.output

    def test_cache_help(self):
        result = runner.invoke(app, ["cache", "--help"])
        assert result.exit_code == 0

    def test_cache_stats_help(self):
        result = runner.invoke(app, ["cache", "stats", "--help"])
        assert result.exit_code == 0

    def test_cache_clear_help(self):
        result = runner.invoke(app, ["cache", "clear", "--help"])
        assert result.exit_code == 0
        assert "--expired" in result.output
