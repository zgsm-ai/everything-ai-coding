"""Tests for ai_resource_eval.scoring.governor and decision modules."""

from __future__ import annotations

import pytest

from ai_resource_eval.api.types import (
    HealthSignals,
    HeuristicSignalWeight,
    MetricResult,
    ThresholdsConfig,
)
from ai_resource_eval.scoring.decision import judge_decision
from ai_resource_eval.scoring.governor import ScoringGovernor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mr(score: int) -> MetricResult:
    """Create a minimal MetricResult with the given score."""
    return MetricResult(score=score, evidence=[], missing=[], suggestion="")


EVEN_WEIGHTS = {
    "coding_relevance": 1 / 6,
    "doc_completeness": 1 / 6,
    "desc_accuracy": 1 / 6,
    "writing_quality": 1 / 6,
    "specificity": 1 / 6,
    "install_clarity": 1 / 6,
}


# ===================================================================
# ScoringGovernor.compute_final_score
# ===================================================================


class TestComputeFinalScore:
    """Tests for the weighted final_score computation."""

    def test_all_fives_gives_100(self):
        """All metrics scored 5 → final_score = 100."""
        metrics = {name: _mr(5) for name in EVEN_WEIGHTS}
        score = ScoringGovernor.compute_final_score(metrics, EVEN_WEIGHTS)
        assert score == pytest.approx(100.0, abs=0.01)

    def test_all_ones_gives_20(self):
        """All metrics scored 1 → final_score = 20."""
        metrics = {name: _mr(1) for name in EVEN_WEIGHTS}
        score = ScoringGovernor.compute_final_score(metrics, EVEN_WEIGHTS)
        assert score == pytest.approx(20.0, abs=0.01)

    def test_all_threes_gives_60(self):
        """All metrics scored 3 → final_score = 60."""
        metrics = {name: _mr(3) for name in EVEN_WEIGHTS}
        score = ScoringGovernor.compute_final_score(metrics, EVEN_WEIGHTS)
        assert score == pytest.approx(60.0, abs=0.01)

    def test_mixed_scores_with_uneven_weights(self):
        """Verify formula with uneven weights and mixed scores."""
        metrics = {
            "coding_relevance": _mr(5),
            "doc_completeness": _mr(1),
        }
        weights = {
            "coding_relevance": 0.7,
            "doc_completeness": 0.3,
        }
        # (5/5 * 100 * 0.7) + (1/5 * 100 * 0.3) = 70 + 6 = 76
        score = ScoringGovernor.compute_final_score(metrics, weights)
        assert score == pytest.approx(76.0, abs=0.01)

    def test_single_metric(self):
        """Single metric with weight 1.0."""
        metrics = {"only": _mr(4)}
        weights = {"only": 1.0}
        # 4/5 * 100 * 1.0 = 80
        score = ScoringGovernor.compute_final_score(metrics, weights)
        assert score == pytest.approx(80.0, abs=0.01)

    def test_weights_must_sum_to_one(self):
        """Weights that do not sum to 1.0 (±0.001) raise ValueError."""
        metrics = {"a": _mr(3), "b": _mr(3)}
        weights = {"a": 0.5, "b": 0.3}  # sums to 0.8
        with pytest.raises(ValueError, match="sum to 1.0"):
            ScoringGovernor.compute_final_score(metrics, weights)

    def test_weights_tolerance_within_bounds(self):
        """Weights summing to 1.0 within tolerance (±0.001) are accepted."""
        metrics = {"a": _mr(5), "b": _mr(5), "c": _mr(5)}
        # 0.333 + 0.333 + 0.334 = 1.000
        weights = {"a": 0.333, "b": 0.333, "c": 0.334}
        score = ScoringGovernor.compute_final_score(metrics, weights)
        assert score == pytest.approx(100.0, abs=0.1)

    def test_mismatched_keys_raises(self):
        """Metrics and weights must have matching keys."""
        metrics = {"a": _mr(3)}
        weights = {"b": 1.0}
        with pytest.raises(ValueError, match="[Mm]ismatch"):
            ScoringGovernor.compute_final_score(metrics, weights)


# ===================================================================
# ScoringGovernor.compute_health_score
# ===================================================================


class TestComputeHealthScore:
    """Tests for health score computation with weight redistribution."""

    @pytest.fixture()
    def default_signal_weights(self) -> list[HeuristicSignalWeight]:
        return [
            HeuristicSignalWeight(signal="freshness", weight=0.30),
            HeuristicSignalWeight(signal="popularity", weight=0.30),
            HeuristicSignalWeight(signal="source_trust", weight=0.40),
        ]

    def test_no_exclusions(self, default_signal_weights):
        """No excluded signals → weights used as-is."""
        signals = HealthSignals(freshness=80.0, popularity=60.0, source_trust=90.0)
        score = ScoringGovernor.compute_health_score(
            signals, default_signal_weights
        )
        # 80*0.30 + 60*0.30 + 90*0.40 = 24 + 18 + 36 = 78
        assert score == pytest.approx(78.0, abs=0.01)

    def test_exclude_popularity_redistributes(self, default_signal_weights):
        """Excluding popularity → its weight redistributed proportionally."""
        signals = HealthSignals(freshness=80.0, popularity=60.0, source_trust=90.0)
        score = ScoringGovernor.compute_health_score(
            signals, default_signal_weights,
            excluded_signals={"popularity"},
        )
        # Redistributed weights:
        #   freshness  = 0.30 + 0.30 * (0.30/0.70) = 0.30 + 0.12857 = 0.42857
        #   source_trust = 0.40 + 0.30 * (0.40/0.70) = 0.40 + 0.17143 = 0.57143
        # score = 80 * 0.42857 + 90 * 0.57143 = 34.286 + 51.429 = 85.714
        assert score == pytest.approx(85.714, abs=0.01)

    def test_exclude_freshness_redistributes(self, default_signal_weights):
        """Excluding freshness → its weight redistributed proportionally."""
        signals = HealthSignals(freshness=0.0, popularity=60.0, source_trust=90.0)
        score = ScoringGovernor.compute_health_score(
            signals, default_signal_weights,
            excluded_signals={"freshness"},
        )
        # Redistributed:
        #   popularity   = 0.30 + 0.30 * (0.30/0.70) = 0.42857
        #   source_trust = 0.40 + 0.30 * (0.40/0.70) = 0.57143
        # score = 60 * 0.42857 + 90 * 0.57143 = 25.714 + 51.429 = 77.143
        assert score == pytest.approx(77.143, abs=0.01)

    def test_exclude_both_popularity_and_freshness(self, default_signal_weights):
        """Excluding both popularity and freshness → only source_trust remains."""
        signals = HealthSignals(freshness=0.0, popularity=0.0, source_trust=80.0)
        score = ScoringGovernor.compute_health_score(
            signals, default_signal_weights,
            excluded_signals={"popularity", "freshness"},
        )
        # Only source_trust with weight 1.0 (0.40 + 0.30 + 0.30 redistributed)
        # score = 80 * 1.0 = 80
        assert score == pytest.approx(80.0, abs=0.01)

    def test_exclude_redistribution_exact_values(self, default_signal_weights):
        """Verify exact redistributed weight values."""
        signals = HealthSignals(freshness=100.0, popularity=0.0, source_trust=100.0)
        score = ScoringGovernor.compute_health_score(
            signals, default_signal_weights,
            excluded_signals={"popularity"},
        )
        # freshness_w = 0.4286, source_trust_w = 0.5714
        # 100 * 0.4286 + 100 * 0.5714 = 100.0
        assert score == pytest.approx(100.0, abs=0.01)

    def test_all_zeros_health(self, default_signal_weights):
        """All signal values zero → health score = 0."""
        signals = HealthSignals(freshness=0.0, popularity=0.0, source_trust=0.0)
        score = ScoringGovernor.compute_health_score(
            signals, default_signal_weights
        )
        assert score == pytest.approx(0.0, abs=0.01)

    def test_all_hundred_health(self, default_signal_weights):
        """All signal values 100 → health score = 100."""
        signals = HealthSignals(freshness=100.0, popularity=100.0, source_trust=100.0)
        score = ScoringGovernor.compute_health_score(
            signals, default_signal_weights
        )
        assert score == pytest.approx(100.0, abs=0.01)

    def test_no_popularity_signal_configured(self):
        """If no 'popularity' signal is configured, excluding it has no effect."""
        signal_weights = [
            HeuristicSignalWeight(signal="freshness", weight=0.50),
            HeuristicSignalWeight(signal="source_trust", weight=0.50),
        ]
        signals = HealthSignals(freshness=80.0, popularity=60.0, source_trust=90.0)
        score = ScoringGovernor.compute_health_score(
            signals, signal_weights,
            excluded_signals={"popularity"},
        )
        # No popularity weight to redistribute → 80*0.50 + 90*0.50 = 85
        assert score == pytest.approx(85.0, abs=0.01)

    def test_custom_two_signal_redistribution(self):
        """Custom weights with only freshness+popularity: excluding pop gives all to freshness."""
        signal_weights = [
            HeuristicSignalWeight(signal="freshness", weight=0.40),
            HeuristicSignalWeight(signal="popularity", weight=0.60),
        ]
        signals = HealthSignals(freshness=50.0, popularity=100.0, source_trust=0.0)
        score = ScoringGovernor.compute_health_score(
            signals, signal_weights,
            excluded_signals={"popularity"},
        )
        # popularity zeroed, freshness gets all: 0.40 + 0.60*(0.40/0.40) = 1.0
        # score = 50 * 1.0 = 50
        assert score == pytest.approx(50.0, abs=0.01)

    def test_empty_excluded_signals_same_as_none(self, default_signal_weights):
        """Empty set behaves the same as None."""
        signals = HealthSignals(freshness=80.0, popularity=60.0, source_trust=90.0)
        score_none = ScoringGovernor.compute_health_score(
            signals, default_signal_weights
        )
        score_empty = ScoringGovernor.compute_health_score(
            signals, default_signal_weights,
            excluded_signals=set(),
        )
        assert score_none == pytest.approx(score_empty, abs=0.001)


# ===================================================================
# ScoringGovernor.compute_blended_score
# ===================================================================


class TestComputeBlendedScore:
    """Tests for the LLM + health blending formula."""

    def test_alpha_one_is_llm_only(self):
        """alpha=1.0 → blended = llm_score."""
        assert ScoringGovernor.compute_blended_score(80.0, 40.0, alpha=1.0) == pytest.approx(80.0)

    def test_alpha_zero_is_health_only(self):
        """alpha=0.0 → blended = health_score."""
        assert ScoringGovernor.compute_blended_score(80.0, 40.0, alpha=0.0) == pytest.approx(40.0)

    def test_default_alpha_085(self):
        """Default alpha=0.85 blends correctly."""
        # 0.85 * 80 + 0.15 * 40 = 68 + 6 = 74
        assert ScoringGovernor.compute_blended_score(80.0, 40.0) == pytest.approx(74.0)

    def test_equal_scores_unchanged(self):
        """When llm_score == health_score, blending preserves the value."""
        assert ScoringGovernor.compute_blended_score(70.0, 70.0, alpha=0.85) == pytest.approx(70.0)

    def test_low_health_pulls_down(self):
        """Low health score pulls final score below LLM score."""
        # 0.85 * 70 + 0.15 * 0 = 59.5
        blended = ScoringGovernor.compute_blended_score(70.0, 0.0, alpha=0.85)
        assert blended == pytest.approx(59.5)
        assert blended < 70.0

    def test_high_health_boosts(self):
        """High health score pushes final score above LLM score."""
        # 0.85 * 60 + 0.15 * 100 = 51 + 15 = 66
        blended = ScoringGovernor.compute_blended_score(60.0, 100.0, alpha=0.85)
        assert blended == pytest.approx(66.0)
        assert blended > 60.0


# ===================================================================
# judge_decision — threshold determination
# ===================================================================


class TestJudgeDecision:
    """Tests for accept/review/reject threshold logic."""

    @pytest.fixture()
    def thresholds(self) -> ThresholdsConfig:
        """Standard thresholds: accept=65, review=40."""
        return ThresholdsConfig(accept=65, review=40)

    def test_accept_at_threshold(self, thresholds):
        """final_score == accept_threshold → accept."""
        assert judge_decision(65.0, 3, thresholds) == "accept"

    def test_accept_above_threshold(self, thresholds):
        """final_score > accept_threshold → accept."""
        assert judge_decision(90.0, 5, thresholds) == "accept"

    def test_review_at_threshold(self, thresholds):
        """final_score == review_threshold → review."""
        assert judge_decision(40.0, 3, thresholds) == "review"

    def test_review_between_thresholds(self, thresholds):
        """review_threshold <= final_score < accept_threshold → review."""
        assert judge_decision(50.0, 3, thresholds) == "review"

    def test_review_just_below_accept(self, thresholds):
        """final_score just below accept_threshold → review."""
        assert judge_decision(64.99, 3, thresholds) == "review"

    def test_reject_below_review(self, thresholds):
        """final_score < review_threshold → reject."""
        assert judge_decision(39.99, 3, thresholds) == "reject"

    def test_reject_zero(self, thresholds):
        """final_score = 0 → reject."""
        assert judge_decision(0.0, 3, thresholds) == "reject"

    def test_accept_perfect_score(self, thresholds):
        """final_score = 100 → accept."""
        assert judge_decision(100.0, 5, thresholds) == "accept"


# ===================================================================
# judge_decision — hard rule (coding_relevance cap)
# ===================================================================


class TestCodingRelevanceHardRule:
    """Tests for the coding_relevance <= 2 hard cap rule."""

    @pytest.fixture()
    def thresholds(self) -> ThresholdsConfig:
        return ThresholdsConfig(accept=65, review=40)

    def test_coding_relevance_one_caps_accept_to_review(self, thresholds):
        """coding_relevance=1 + high score → capped to 'review'."""
        assert judge_decision(90.0, 1, thresholds) == "review"

    def test_coding_relevance_two_caps_accept_to_review(self, thresholds):
        """coding_relevance=2 + high score → capped to 'review'."""
        assert judge_decision(90.0, 2, thresholds) == "review"

    def test_coding_relevance_two_keeps_review(self, thresholds):
        """coding_relevance=2 + review-range score → stays 'review'."""
        assert judge_decision(50.0, 2, thresholds) == "review"

    def test_coding_relevance_one_keeps_reject(self, thresholds):
        """coding_relevance=1 + low score → stays 'reject' (cap doesn't upgrade)."""
        assert judge_decision(20.0, 1, thresholds) == "reject"

    def test_coding_relevance_two_keeps_reject(self, thresholds):
        """coding_relevance=2 + low score → stays 'reject'."""
        assert judge_decision(20.0, 2, thresholds) == "reject"

    def test_coding_relevance_three_no_cap(self, thresholds):
        """coding_relevance=3 → no cap, accept is possible."""
        assert judge_decision(90.0, 3, thresholds) == "accept"

    def test_coding_relevance_five_no_cap(self, thresholds):
        """coding_relevance=5 → no cap."""
        assert judge_decision(90.0, 5, thresholds) == "accept"

    def test_coding_relevance_two_at_accept_boundary(self, thresholds):
        """coding_relevance=2 at exactly accept_threshold → capped to review."""
        assert judge_decision(65.0, 2, thresholds) == "review"

    def test_coding_relevance_one_at_100(self, thresholds):
        """coding_relevance=1 with perfect score → capped to review."""
        assert judge_decision(100.0, 1, thresholds) == "review"
