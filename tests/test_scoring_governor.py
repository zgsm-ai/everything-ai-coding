import os
import sys
import unittest
import unittest.mock

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import scoring_governor  # noqa: E402


class ApplyGovernanceTests(unittest.TestCase):
    def test_harness_passthrough(self):
        """Entries with final_score from harness are passed through as-is."""
        entries = [
            {
                "id": "e1",
                "type": "mcp",
                "evaluation": {
                    "model_id": "deepseek-chat",
                    "final_score": 85.0,
                    "decision": "accept",
                },
            },
        ]
        result = scoring_governor.apply_governance(entries)
        self.assertEqual(result[0]["final_score"], 85.0)
        self.assertEqual(result[0]["decision"], "accept")

    def test_unevaluated_gets_defaults(self):
        """Entries without final_score get score=0, decision=review."""
        entries = [{"id": "e1", "type": "mcp"}]
        result = scoring_governor.apply_governance(entries)
        self.assertEqual(result[0]["final_score"], 0)
        self.assertEqual(result[0]["decision"], "review")
        self.assertEqual(result[0]["evaluation"]["final_score"], 0)
        self.assertEqual(result[0]["evaluation"]["decision"], "review")

    def test_reject_filtered_when_not_dry_run(self):
        entries = [
            {
                "id": "bad",
                "type": "mcp",
                "evaluation": {"final_score": 30.0, "decision": "reject"},
            },
        ]
        with unittest.mock.patch.dict(os.environ, {"EVAL_DRY_RUN": "false"}):
            result = scoring_governor.apply_governance(entries)
        self.assertEqual(len(result), 0)

    def test_reject_kept_in_dry_run(self):
        entries = [
            {
                "id": "bad",
                "type": "mcp",
                "evaluation": {"final_score": 30.0, "decision": "reject"},
            },
        ]
        with unittest.mock.patch.dict(os.environ, {"EVAL_DRY_RUN": "true"}):
            result = scoring_governor.apply_governance(entries)
        self.assertEqual(len(result), 1)

    def test_mixed_entries(self):
        """Mix of harness-evaluated, unevaluated, and rejected entries."""
        entries = [
            {"id": "good", "evaluation": {"final_score": 80.0, "decision": "accept"}},
            {"id": "new", "type": "skill"},
            {"id": "bad", "evaluation": {"final_score": 20.0, "decision": "reject"}},
        ]
        with unittest.mock.patch.dict(os.environ, {"EVAL_DRY_RUN": "false"}):
            result = scoring_governor.apply_governance(entries)
        ids = [e["id"] for e in result]
        self.assertIn("good", ids)
        self.assertIn("new", ids)  # unevaluated → review → kept
        self.assertNotIn("bad", ids)  # reject → filtered

    def test_weak_dims_single_dim(self):
        entries = [
            {
                "id": "e1",
                "type": "mcp",
                "evaluation": {
                    "coding_relevance": 5,
                    "doc_completeness": 5,
                    "desc_accuracy": 5,
                    "writing_quality": 5,
                    "specificity": 5,
                    "install_clarity": 2,
                    "final_score": 70,
                    "decision": "accept",
                },
            },
        ]
        result = scoring_governor.apply_governance(entries)
        self.assertEqual(result[0]["weak_dims"], ["install_clarity"])

    def test_weak_dims_multiple_in_canonical_order(self):
        """weak_dims must follow LLM_DIMENSION_ORDER, not dict insertion order."""
        # Insert keys in scrambled order to prove ordering comes from governor.
        ev = {}
        ev["install_clarity"] = 1
        ev["specificity"] = 5
        ev["writing_quality"] = 5
        ev["desc_accuracy"] = 5
        ev["doc_completeness"] = 5
        ev["coding_relevance"] = 2
        ev["final_score"] = 50
        ev["decision"] = "review"
        entries = [{"id": "e1", "type": "mcp", "evaluation": ev}]
        result = scoring_governor.apply_governance(entries)
        self.assertEqual(
            result[0]["weak_dims"], ["coding_relevance", "install_clarity"]
        )

    def test_weak_dims_unevaluated(self):
        entries = [{"id": "e1", "type": "mcp"}]
        result = scoring_governor.apply_governance(entries)
        self.assertEqual(result[0]["weak_dims"], [])

    def test_weak_dims_partial_eval_without_final_score(self):
        """Partial evaluation (dims present, no final_score) → treated as unevaluated."""
        entries = [
            {
                "id": "e1",
                "type": "mcp",
                "evaluation": {
                    "install_clarity": 2,
                    "coding_relevance": 5,
                },
            },
        ]
        result = scoring_governor.apply_governance(entries)
        self.assertEqual(result[0]["weak_dims"], [])

    def test_freshness_label_denormalized(self):
        entries = [
            {
                "id": "e1",
                "type": "mcp",
                "health": {"freshness_label": "active", "score": 90},
            },
        ]
        result = scoring_governor.apply_governance(entries)
        self.assertEqual(result[0]["freshness_label"], "active")

    def test_freshness_label_absent_when_no_health(self):
        entries = [{"id": "e1", "type": "mcp"}]
        result = scoring_governor.apply_governance(entries)
        self.assertNotIn("freshness_label", result[0])

    def test_mcp_registry_strict_accept_default_drops_non_accept(self):
        """registry.modelcontextprotocol.io entries with decision != accept are dropped by default."""
        entries = [
            {
                "id": "reg-accept",
                "type": "mcp",
                "source": "registry.modelcontextprotocol.io",
                "evaluation": {"final_score": 80.0, "decision": "accept"},
            },
            {
                "id": "reg-review",
                "type": "mcp",
                "source": "registry.modelcontextprotocol.io",
                "evaluation": {"final_score": 60.0, "decision": "review"},
            },
            {
                "id": "other-review",
                "type": "mcp",
                "source": "awesome-mcp-servers",
                "evaluation": {"final_score": 60.0, "decision": "review"},
            },
        ]
        with unittest.mock.patch.dict(os.environ, {"EVAL_DRY_RUN": "true"}, clear=False):
            result = scoring_governor.apply_governance(entries)
        ids = [e["id"] for e in result]
        self.assertIn("reg-accept", ids)
        self.assertNotIn("reg-review", ids)
        self.assertIn("other-review", ids)  # non-registry sources unaffected

    def test_mcp_registry_strict_accept_can_be_disabled(self):
        """MCP_REGISTRY_STRICT_ACCEPT=false keeps all registry entries (legacy behavior)."""
        entries = [
            {
                "id": "reg-review",
                "type": "mcp",
                "source": "registry.modelcontextprotocol.io",
                "evaluation": {"final_score": 60.0, "decision": "review"},
            },
        ]
        with unittest.mock.patch.dict(
            os.environ,
            {"MCP_REGISTRY_STRICT_ACCEPT": "false", "EVAL_DRY_RUN": "true"},
            clear=False,
        ):
            result = scoring_governor.apply_governance(entries)
        self.assertEqual([e["id"] for e in result], ["reg-review"])


class SecurityGateGithubTrendingTests(unittest.TestCase):
    """github-trending 源：security verdict 参与 decision（仅此源）。"""

    def test_reject_verdict_sets_decision_reject(self):
        """verdict=reject（risk high/extreme）→ decision 置 reject。"""
        entries = [
            {
                "id": "gt-bad",
                "type": "skill",
                "source": "github-trending",
                "evaluation": {"final_score": 80.0, "decision": "accept"},
                "security": {"verdict": "reject", "risk_level": "high"},
            },
        ]
        with unittest.mock.patch.dict(os.environ, {"EVAL_DRY_RUN": "true"}, clear=False):
            result = scoring_governor.apply_governance(entries)
        self.assertEqual(result[0]["decision"], "reject")
        self.assertEqual(result[0]["evaluation"]["decision"], "reject")

    def test_reject_verdict_dropped_when_not_dry_run(self):
        """verdict=reject → 置 reject → 非 dry-run 下被 reject 过滤丢弃。"""
        entries = [
            {
                "id": "gt-bad",
                "type": "skill",
                "source": "github-trending",
                "evaluation": {"final_score": 80.0, "decision": "accept"},
                "security": {"verdict": "reject", "risk_level": "extreme"},
            },
        ]
        with unittest.mock.patch.dict(os.environ, {"EVAL_DRY_RUN": "false"}, clear=False):
            result = scoring_governor.apply_governance(entries)
        self.assertEqual(len(result), 0)

    def test_caution_verdict_downgrades_accept_to_review(self):
        """verdict=caution（medium）→ accept 降级为 review。"""
        entries = [
            {
                "id": "gt-caution",
                "type": "plugin",
                "source": "github-trending",
                "evaluation": {"final_score": 70.0, "decision": "accept"},
                "security": {"verdict": "caution", "risk_level": "medium"},
            },
        ]
        with unittest.mock.patch.dict(os.environ, {"EVAL_DRY_RUN": "true"}, clear=False):
            result = scoring_governor.apply_governance(entries)
        self.assertEqual(result[0]["decision"], "review")
        self.assertEqual(result[0]["evaluation"]["decision"], "review")

    def test_caution_verdict_leaves_non_accept_unchanged(self):
        """caution 只降 accept；已是 review 的不再动。"""
        entries = [
            {
                "id": "gt-caution-review",
                "type": "skill",
                "source": "github-trending",
                "evaluation": {"final_score": 55.0, "decision": "review"},
                "security": {"verdict": "caution", "risk_level": "medium"},
            },
        ]
        with unittest.mock.patch.dict(os.environ, {"EVAL_DRY_RUN": "true"}, clear=False):
            result = scoring_governor.apply_governance(entries)
        self.assertEqual(result[0]["decision"], "review")

    def test_safe_verdict_leaves_decision_untouched(self):
        """verdict=safe（clean/low）→ 不动 decision。"""
        entries = [
            {
                "id": "gt-clean",
                "type": "skill",
                "source": "github-trending",
                "evaluation": {"final_score": 80.0, "decision": "accept"},
                "security": {"verdict": "safe", "risk_level": "clean"},
            },
        ]
        with unittest.mock.patch.dict(os.environ, {"EVAL_DRY_RUN": "true"}, clear=False):
            result = scoring_governor.apply_governance(entries)
        self.assertEqual(result[0]["decision"], "accept")

    def test_other_source_security_does_not_affect_decision(self):
        """非 github-trending 源即便 verdict=reject 也不改 decision（保持现状）。"""
        entries = [
            {
                "id": "official-bad",
                "type": "plugin",
                "source": "claude-plugins-official",
                "evaluation": {"final_score": 80.0, "decision": "accept"},
                "security": {"verdict": "reject", "risk_level": "high"},
            },
        ]
        with unittest.mock.patch.dict(os.environ, {"EVAL_DRY_RUN": "false"}, clear=False):
            result = scoring_governor.apply_governance(entries)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["decision"], "accept")

    def test_no_security_field_no_change(self):
        """github-trending 但无 security 字段 → decision 不动。"""
        entries = [
            {
                "id": "gt-no-sec",
                "type": "skill",
                "source": "github-trending",
                "evaluation": {"final_score": 80.0, "decision": "accept"},
            },
        ]
        with unittest.mock.patch.dict(os.environ, {"EVAL_DRY_RUN": "true"}, clear=False):
            result = scoring_governor.apply_governance(entries)
        self.assertEqual(result[0]["decision"], "accept")


class AuthenticityGateGithubTrendingTests(unittest.TestCase):
    """github-trending 源：resource_authenticity (is_primary_skill) 参与 decision（仅此源）。"""

    def test_not_primary_skill_sets_decision_reject(self):
        """is_primary_skill=False → decision 置 reject（镜像进 evaluation）。"""
        entries = [
            {
                "id": "gt-app",
                "type": "skill",
                "source": "github-trending",
                "evaluation": {"final_score": 80.0, "decision": "accept"},
                "resource_authenticity": {
                    "is_primary_skill": False,
                    "reason": "主体是一个 agent framework，恰好捆了 skill",
                },
            },
        ]
        with unittest.mock.patch.dict(os.environ, {"EVAL_DRY_RUN": "true"}, clear=False):
            result = scoring_governor.apply_governance(entries)
        self.assertEqual(result[0]["decision"], "reject")
        self.assertEqual(result[0]["evaluation"]["decision"], "reject")

    def test_not_primary_skill_dropped_when_not_dry_run(self):
        """is_primary_skill=False → 置 reject → 非 dry-run 下被 reject 过滤丢弃。"""
        entries = [
            {
                "id": "gt-app",
                "type": "skill",
                "source": "github-trending",
                "evaluation": {"final_score": 80.0, "decision": "accept"},
                "resource_authenticity": {"is_primary_skill": False, "reason": "app"},
            },
        ]
        with unittest.mock.patch.dict(os.environ, {"EVAL_DRY_RUN": "false"}, clear=False):
            result = scoring_governor.apply_governance(entries)
        self.assertEqual(len(result), 0)

    def test_primary_skill_true_leaves_decision_untouched(self):
        """is_primary_skill=True → 不动 decision。"""
        entries = [
            {
                "id": "gt-real-skill",
                "type": "skill",
                "source": "github-trending",
                "evaluation": {"final_score": 80.0, "decision": "accept"},
                "resource_authenticity": {
                    "is_primary_skill": True,
                    "reason": "主体是一个可复用 skill",
                },
            },
        ]
        with unittest.mock.patch.dict(os.environ, {"EVAL_DRY_RUN": "true"}, clear=False):
            result = scoring_governor.apply_governance(entries)
        self.assertEqual(result[0]["decision"], "accept")

    def test_missing_authenticity_field_no_change(self):
        """github-trending 但无 resource_authenticity 字段（LLM 失败/未评估）→ decision 不动。"""
        entries = [
            {
                "id": "gt-no-auth",
                "type": "skill",
                "source": "github-trending",
                "evaluation": {"final_score": 80.0, "decision": "accept"},
            },
        ]
        with unittest.mock.patch.dict(os.environ, {"EVAL_DRY_RUN": "true"}, clear=False):
            result = scoring_governor.apply_governance(entries)
        self.assertEqual(result[0]["decision"], "accept")

    def test_other_source_authenticity_does_not_affect_decision(self):
        """非 github-trending 源即便 is_primary_skill=False 也不改 decision（仅本源生效）。"""
        entries = [
            {
                "id": "official-app",
                "type": "skill",
                "source": "anthropics-skills",
                "evaluation": {"final_score": 80.0, "decision": "accept"},
                "resource_authenticity": {"is_primary_skill": False, "reason": "app"},
            },
        ]
        with unittest.mock.patch.dict(os.environ, {"EVAL_DRY_RUN": "false"}, clear=False):
            result = scoring_governor.apply_governance(entries)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["decision"], "accept")

    def test_authenticity_field_not_dict_no_change(self):
        """resource_authenticity 非 dict（脏数据）→ 保守不动 decision，不崩。"""
        entries = [
            {
                "id": "gt-dirty",
                "type": "skill",
                "source": "github-trending",
                "evaluation": {"final_score": 80.0, "decision": "accept"},
                "resource_authenticity": "not-a-dict",
            },
        ]
        with unittest.mock.patch.dict(os.environ, {"EVAL_DRY_RUN": "true"}, clear=False):
            result = scoring_governor.apply_governance(entries)
        self.assertEqual(result[0]["decision"], "accept")


if __name__ == "__main__":
    unittest.main()
