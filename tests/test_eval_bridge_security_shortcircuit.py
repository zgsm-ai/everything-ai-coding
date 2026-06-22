"""Tests for the entry-field security short-circuit (A) in eval_bridge.

Covers ``fix-security-scan-rescan-timeout`` item A: ``_run_security_scan`` must
drop entries that already carry a valid ``security`` block whose
``rubric_version`` matches the current security rubric BEFORE building EvalItems
/ entering the runner — so they trigger neither a GitHub raw fetch (the 429
source) nor an LLM call. Entries without a security block, with a stale rubric,
or with a half-written / dirty block must still go through the runner.
"""

from __future__ import annotations

import os
import sys
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import eval_bridge  # noqa: E402

# Skip the whole module if the eval package isn't importable (rubric helper
# returns None -> no short-circuit -> these assertions are meaningless).
_CURRENT_RUBRIC = eval_bridge._compute_security_rubric_version()
pytestmark = pytest.mark.skipif(
    _CURRENT_RUBRIC is None,
    reason="ai-resource-eval not installed; cannot compute security rubric_version",
)


def _valid_security_block(rubric: str) -> dict[str, Any]:
    """A structurally-complete, enum-valid security block at the given rubric."""
    return {
        "risk_level": "low",
        "verdict": "safe",
        "red_flags": [],
        "permissions": {"files": [], "network": [], "commands": []},
        "summary": "no external IO",
        "recommendations": [],
        "scan_model": "__cached__",
        "rubric_version": rubric,
        "content_hash": "a" * 64,
        "scanned_at": "2026-05-20T10:32:15Z",
    }


class _RecordingRunner:
    """Stand-in EvalRunner that records the eval_items it was handed.

    ``run`` returns an empty result list — these tests only care about WHICH
    entries reach the runner, not the scan output.
    """

    instances: list["_RecordingRunner"] = []

    def __init__(self, *args, **kwargs):
        self.run_items: list[Any] | None = None
        _RecordingRunner.instances.append(self)

    def run(self, eval_items):
        self.run_items = list(eval_items)
        return []


@pytest.fixture(autouse=True)
def _reset_runner_instances():
    _RecordingRunner.instances.clear()
    yield
    _RecordingRunner.instances.clear()


def _run(entries, tmp_path):
    """Invoke _run_security_scan with the runner + judge mocked out.

    Returns the list of entry ids that actually reached the runner.
    """
    with patch.object(eval_bridge, "_build_judge", return_value=MagicMock()), patch(
        "ai_resource_eval.runner.EvalRunner", _RecordingRunner
    ):
        eval_bridge._run_security_scan(
            entries, cache_dir=str(tmp_path / ".eval_cache")
        )
    if not _RecordingRunner.instances:
        return []
    runner = _RecordingRunner.instances[-1]
    if runner.run_items is None:
        return []
    return [getattr(it, "id", None) for it in runner.run_items]


# ---------------------------------------------------------------------------
# Core short-circuit behaviour
# ---------------------------------------------------------------------------


class TestEntryFieldShortCircuit:
    def test_valid_matching_block_is_skipped(self, tmp_path):
        """entry with a valid security block at the current rubric -> not scanned."""
        entries = [
            {
                "id": "skill-already",
                "name": "already",
                "type": "skill",
                "security": _valid_security_block(_CURRENT_RUBRIC),
            }
        ]
        scanned = _run(entries, tmp_path)
        assert "skill-already" not in scanned
        # No runner was even constructed (all entries short-circuited -> early
        # return before EvalRunner()).
        assert _RecordingRunner.instances == []
        # The existing security block is preserved untouched.
        assert entries[0]["security"]["rubric_version"] == _CURRENT_RUBRIC

    def test_no_security_block_still_scanned(self, tmp_path):
        entries = [{"id": "skill-new", "name": "new", "type": "skill"}]
        scanned = _run(entries, tmp_path)
        assert scanned == ["skill-new"]

    def test_stale_rubric_still_scanned(self, tmp_path):
        block = _valid_security_block("1.deadbeef")  # wrong / old rubric
        entries = [
            {"id": "skill-stale", "name": "stale", "type": "skill", "security": block}
        ]
        scanned = _run(entries, tmp_path)
        assert scanned == ["skill-stale"]

    def test_incomplete_block_still_scanned(self, tmp_path):
        """A half-written block (missing summary) must not count as 'scanned'."""
        block = _valid_security_block(_CURRENT_RUBRIC)
        block.pop("summary")
        entries = [
            {"id": "skill-partial", "name": "p", "type": "skill", "security": block}
        ]
        scanned = _run(entries, tmp_path)
        assert scanned == ["skill-partial"]

    def test_invalid_verdict_block_still_scanned(self, tmp_path):
        block = _valid_security_block(_CURRENT_RUBRIC)
        block["verdict"] = "totally-invalid"
        entries = [
            {"id": "skill-badverdict", "name": "b", "type": "skill", "security": block}
        ]
        scanned = _run(entries, tmp_path)
        assert scanned == ["skill-badverdict"]

    def test_invalid_risk_level_block_still_scanned(self, tmp_path):
        block = _valid_security_block(_CURRENT_RUBRIC)
        block["risk_level"] = "catastrophic"  # not in enum
        entries = [
            {"id": "skill-badrisk", "name": "b", "type": "skill", "security": block}
        ]
        scanned = _run(entries, tmp_path)
        assert scanned == ["skill-badrisk"]

    def test_verdict_risk_level_mismatch_still_scanned(self, tmp_path):
        """Enum-valid but inconsistent verdict/risk_level (high should map to
        reject, not safe) is a dirty block and must be rescanned, not skipped."""
        block = _valid_security_block(_CURRENT_RUBRIC)
        block["risk_level"] = "high"  # high -> reject
        block["verdict"] = "safe"  # mismatch
        entries = [
            {"id": "skill-mismatch", "name": "m", "type": "skill", "security": block}
        ]
        scanned = _run(entries, tmp_path)
        assert scanned == ["skill-mismatch"]

    def test_non_dict_security_field_still_scanned(self, tmp_path):
        entries = [
            {"id": "skill-junk", "name": "j", "type": "skill", "security": "oops"}
        ]
        scanned = _run(entries, tmp_path)
        assert scanned == ["skill-junk"]


# ---------------------------------------------------------------------------
# Mixed batch: regression scenario (the 2820-already-scanned simulation)
# ---------------------------------------------------------------------------


class TestMixedBatch:
    def test_only_new_entries_reach_runner(self, tmp_path):
        """N entries already carrying a valid block -> only the genuinely-new
        entries reach the runner (the 2820-recovered-entries scenario)."""
        entries: list[dict[str, Any]] = []
        # 50 already-scanned (skipped)
        for i in range(50):
            entries.append(
                {
                    "id": f"already-{i}",
                    "name": f"a{i}",
                    "type": "skill",
                    "security": _valid_security_block(_CURRENT_RUBRIC),
                }
            )
        # 3 genuinely new (no block)
        for i in range(3):
            entries.append({"id": f"fresh-{i}", "name": f"f{i}", "type": "skill"})

        scanned = _run(entries, tmp_path)
        assert sorted(scanned) == ["fresh-0", "fresh-1", "fresh-2"]
        # exactly one runner constructed (the 50 didn't trigger an early return
        # because 3 remained to scan)
        assert len(_RecordingRunner.instances) == 1

    def test_all_already_scanned_no_runner(self, tmp_path):
        """Every entry already scanned -> early return, no runner, no judge."""
        entries = [
            {
                "id": f"already-{i}",
                "name": f"a{i}",
                "type": "skill",
                "security": _valid_security_block(_CURRENT_RUBRIC),
            }
            for i in range(2820)
        ]
        with patch.object(
            eval_bridge, "_build_judge", return_value=MagicMock()
        ) as mock_judge, patch(
            "ai_resource_eval.runner.EvalRunner", _RecordingRunner
        ):
            out = eval_bridge._run_security_scan(
                entries, cache_dir=str(tmp_path / ".eval_cache")
            )
        assert out == {}
        # No runner constructed at all.
        assert _RecordingRunner.instances == []
        # _build_judge is still called (the short-circuit happens after the
        # judge check), but the point is no scanning work occurs.
        assert mock_judge.called


# ---------------------------------------------------------------------------
# Rubric helper / block-completeness helper edge cases
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_complete_block_accepts_valid(self):
        assert eval_bridge._is_security_block_complete(
            _valid_security_block(_CURRENT_RUBRIC)
        )

    def test_complete_block_rejects_missing_permissions(self):
        block = _valid_security_block(_CURRENT_RUBRIC)
        block["permissions"] = None
        assert not eval_bridge._is_security_block_complete(block)

    def test_complete_block_rejects_non_dict(self):
        assert not eval_bridge._is_security_block_complete("x")
        assert not eval_bridge._is_security_block_complete(None)

    def test_complete_block_rejects_verdict_risk_mismatch(self):
        block = _valid_security_block(_CURRENT_RUBRIC)
        block["risk_level"] = "extreme"  # extreme -> reject
        block["verdict"] = "caution"  # mismatch
        assert not eval_bridge._is_security_block_complete(block)

    def test_complete_block_accepts_each_valid_mapping(self):
        pairs = [
            ("clean", "safe"),
            ("low", "safe"),
            ("medium", "caution"),
            ("high", "reject"),
            ("extreme", "reject"),
        ]
        for risk, verdict in pairs:
            block = _valid_security_block(_CURRENT_RUBRIC)
            block["risk_level"] = risk
            block["verdict"] = verdict
            assert eval_bridge._is_security_block_complete(block), (risk, verdict)

    def test_rubric_version_format(self):
        # major.sha8 form, major is the security_scan.yaml value (currently 2)
        assert _CURRENT_RUBRIC is not None
        major, _, sha = _CURRENT_RUBRIC.partition(".")
        assert major.isdigit()
        assert len(sha) == 8
