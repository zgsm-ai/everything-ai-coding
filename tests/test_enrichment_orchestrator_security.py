"""Tests for the security_scan stage in scripts/enrichment_orchestrator.py."""

from __future__ import annotations

import os
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

# Force reimport to pick up the updated module under test.
if "enrichment_orchestrator" in sys.modules:
    del sys.modules["enrichment_orchestrator"]

import enrichment_orchestrator  # noqa: E402


def _fake_bridge_module(
    eval_mock: MagicMock,
    security_mock: MagicMock,
    authenticity_mock: MagicMock | None = None,
):
    fake = types.ModuleType("eval_bridge")
    fake.eval_and_map = eval_mock
    fake.security_scan_and_map = security_mock
    if authenticity_mock is not None:
        fake.authenticity_scan_and_map = authenticity_mock
    return fake


class SecurityStageOrchestrationTests(unittest.TestCase):
    """Verify the security_scan stage's placement and failure semantics."""

    def test_security_stage_called_after_eval(self):
        """Default: SECURITY_SCAN_ENABLED unset → security stage runs after eval."""
        call_order: list[str] = []

        def record_eval(*args, **kwargs):
            call_order.append("eval")

        def record_security(*args, **kwargs):
            call_order.append("security")

        eval_mock = MagicMock(side_effect=record_eval)
        security_mock = MagicMock(side_effect=record_security)
        fake_bridge = _fake_bridge_module(eval_mock, security_mock)

        entries = [{"id": "s1", "name": "x", "type": "skill"}]
        with patch.dict("sys.modules", {"eval_bridge": fake_bridge}):
            with patch.dict(os.environ, {}, clear=False):
                # Make sure SECURITY_SCAN_ENABLED is not set to false
                os.environ.pop("SECURITY_SCAN_ENABLED", None)
                enrichment_orchestrator.enrich_entries(entries)

        self.assertEqual(call_order, ["eval", "security"])
        eval_mock.assert_called_once()
        security_mock.assert_called_once()

    def test_security_stage_skipped_when_disabled(self):
        """SECURITY_SCAN_ENABLED=false → security stage skipped, eval still runs."""
        eval_mock = MagicMock()
        security_mock = MagicMock()
        fake_bridge = _fake_bridge_module(eval_mock, security_mock)

        entries = [{"id": "s1", "name": "x", "type": "skill"}]
        with patch.dict("sys.modules", {"eval_bridge": fake_bridge}):
            with patch.dict(os.environ, {"SECURITY_SCAN_ENABLED": "false"}):
                enrichment_orchestrator.enrich_entries(entries)

        eval_mock.assert_called_once()
        security_mock.assert_not_called()

    def test_security_stage_failure_does_not_block_pipeline(self):
        """If security stage raises, orchestrator logs and continues silently."""
        eval_mock = MagicMock()
        security_mock = MagicMock(side_effect=RuntimeError("security boom"))
        fake_bridge = _fake_bridge_module(eval_mock, security_mock)

        entries = [{"id": "s1", "name": "x", "type": "skill"}]
        with patch.dict("sys.modules", {"eval_bridge": fake_bridge}):
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("SECURITY_SCAN_ENABLED", None)
                # Should not raise
                enrichment_orchestrator.enrich_entries(entries)

        eval_mock.assert_called_once()
        security_mock.assert_called_once()

    def test_security_disabled_does_not_touch_existing_security_field(self):
        """SECURITY_SCAN_ENABLED=false leaves existing entry.security intact."""
        eval_mock = MagicMock()
        security_mock = MagicMock()
        fake_bridge = _fake_bridge_module(eval_mock, security_mock)

        entries = [
            {
                "id": "s1",
                "name": "x",
                "type": "skill",
                "security": {
                    "risk_level": "low",
                    "verdict": "safe",
                    "red_flags": [],
                    "permissions": {"files": [], "network": [], "commands": []},
                    "summary": "存量",
                    "recommendations": [],
                    "scan_model": "old-model",
                    "rubric_version": "1.aaa",
                    "content_hash": "h",
                    "scanned_at": "2026-04-01T00:00:00+00:00",
                },
            }
        ]
        with patch.dict("sys.modules", {"eval_bridge": fake_bridge}):
            with patch.dict(os.environ, {"SECURITY_SCAN_ENABLED": "false"}):
                enrichment_orchestrator.enrich_entries(entries)

        self.assertIn("security", entries[0])
        self.assertEqual(entries[0]["security"]["risk_level"], "low")
        self.assertEqual(entries[0]["security"]["scan_model"], "old-model")
        security_mock.assert_not_called()


class AuthenticityStageOrchestrationTests(unittest.TestCase):
    """Verify the resource_authenticity stage's placement and failure semantics."""

    def test_authenticity_stage_called_after_security(self):
        """Default: authenticity stage runs after eval + security."""
        call_order: list[str] = []
        eval_mock = MagicMock(side_effect=lambda *a, **k: call_order.append("eval"))
        security_mock = MagicMock(side_effect=lambda *a, **k: call_order.append("security"))
        authenticity_mock = MagicMock(
            side_effect=lambda *a, **k: call_order.append("authenticity")
        )
        fake_bridge = _fake_bridge_module(eval_mock, security_mock, authenticity_mock)

        entries = [{"id": "s1", "name": "x", "type": "skill"}]
        with patch.dict("sys.modules", {"eval_bridge": fake_bridge}):
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("SECURITY_SCAN_ENABLED", None)
                os.environ.pop("AUTHENTICITY_SCAN_ENABLED", None)
                enrichment_orchestrator.enrich_entries(entries)

        self.assertEqual(call_order, ["eval", "security", "authenticity"])
        authenticity_mock.assert_called_once()

    def test_authenticity_stage_skipped_when_disabled(self):
        """AUTHENTICITY_SCAN_ENABLED=false → authenticity skipped, eval still runs."""
        eval_mock = MagicMock()
        security_mock = MagicMock()
        authenticity_mock = MagicMock()
        fake_bridge = _fake_bridge_module(eval_mock, security_mock, authenticity_mock)

        entries = [{"id": "s1", "name": "x", "type": "skill"}]
        with patch.dict("sys.modules", {"eval_bridge": fake_bridge}):
            with patch.dict(os.environ, {"AUTHENTICITY_SCAN_ENABLED": "false"}):
                enrichment_orchestrator.enrich_entries(entries)

        eval_mock.assert_called_once()
        authenticity_mock.assert_not_called()

    def test_authenticity_stage_failure_does_not_block_pipeline(self):
        """If authenticity stage raises, orchestrator logs and continues silently."""
        eval_mock = MagicMock()
        security_mock = MagicMock()
        authenticity_mock = MagicMock(side_effect=RuntimeError("auth boom"))
        fake_bridge = _fake_bridge_module(eval_mock, security_mock, authenticity_mock)

        entries = [{"id": "s1", "name": "x", "type": "skill"}]
        with patch.dict("sys.modules", {"eval_bridge": fake_bridge}):
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("SECURITY_SCAN_ENABLED", None)
                os.environ.pop("AUTHENTICITY_SCAN_ENABLED", None)
                enrichment_orchestrator.enrich_entries(entries)  # Should not raise

        authenticity_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
