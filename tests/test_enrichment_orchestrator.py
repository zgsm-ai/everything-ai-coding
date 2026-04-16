import os
import sys
import types
import unittest
from unittest.mock import patch, MagicMock

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

# Force reimport of the simplified module
if "enrichment_orchestrator" in sys.modules:
    del sys.modules["enrichment_orchestrator"]

import enrichment_orchestrator  # noqa: E402


class EnrichmentOrchestratorTests(unittest.TestCase):
    def test_eval_harness_called_when_available(self):
        """When eval_bridge is importable, eval_and_map is called on entries."""
        mock_eval_and_map = MagicMock()
        entries = [
            {"id": "test-1", "name": "Test", "type": "skill", "tags": [], "description": "test"}
        ]

        fake_bridge = types.ModuleType("eval_bridge")
        fake_bridge.eval_and_map = mock_eval_and_map

        with patch.dict("sys.modules", {"eval_bridge": fake_bridge}):
            enrichment_orchestrator.enrich_entries(entries)

        mock_eval_and_map.assert_called_once()
        call_args = mock_eval_and_map.call_args
        self.assertIs(call_args[0][0], entries)

    def test_graceful_when_eval_bridge_missing(self):
        """When eval_bridge is not importable, orchestrator logs warning but doesn't crash."""
        entries = [
            {"id": "test-1", "name": "Test", "type": "skill", "tags": [], "description": "test"}
        ]

        with patch.dict("sys.modules", {"eval_bridge": None}):
            # Should not raise
            enrichment_orchestrator.enrich_entries(entries)

    def test_incremental_flag_from_env(self):
        """EVAL_INCREMENTAL env var is passed through to eval_and_map."""
        mock_eval_and_map = MagicMock()
        entries = [{"id": "test-1", "name": "Test", "type": "mcp", "tags": [], "description": "test"}]

        fake_bridge = types.ModuleType("eval_bridge")
        fake_bridge.eval_and_map = mock_eval_and_map

        with patch.dict("sys.modules", {"eval_bridge": fake_bridge}):
            with patch.dict(os.environ, {"EVAL_INCREMENTAL": "false"}):
                enrichment_orchestrator.enrich_entries(entries)

        call_kwargs = mock_eval_and_map.call_args
        self.assertFalse(call_kwargs[1]["incremental"])


if __name__ == "__main__":
    unittest.main()
