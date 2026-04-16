"""ScoringGovernor: compute final_score and health_score for evaluation."""

from __future__ import annotations

from ai_resource_eval.api.types import (
    HealthSignals,
    HeuristicSignalWeight,
    MetricResult,
)


class ScoringGovernor:
    """Computes final evaluation scores from metric results and health signals.

    All methods are static — the class is a namespace for scoring logic.
    """

    @staticmethod
    def compute_final_score(
        metric_results: dict[str, MetricResult],
        weights: dict[str, float],
    ) -> float:
        """Compute the weighted final score (0-100) from LLM metric results.

        Formula: ``final_score = Σ (metric_score / 5 × 100 × weight)``

        Parameters
        ----------
        metric_results:
            Metric name → MetricResult mapping (each score is 1-5).
        weights:
            Metric name → weight mapping.  Weights must sum to 1.0 (±0.001).

        Returns
        -------
        float
            Aggregate score in the range [0, 100].

        Raises
        ------
        ValueError
            If weights do not sum to 1.0 or keys do not match.
        """
        # Validate weight sum.
        weight_sum = sum(weights.values())
        if abs(weight_sum - 1.0) > 0.001:
            raise ValueError(
                f"Metric weights must sum to 1.0 (±0.001), got {weight_sum:.4f}"
            )

        # Validate matching keys.
        if set(metric_results.keys()) != set(weights.keys()):
            raise ValueError(
                f"Mismatch between metric_results keys {set(metric_results.keys())} "
                f"and weights keys {set(weights.keys())}"
            )

        return sum(
            (metric_results[name].score / 5) * 100 * weights[name]
            for name in weights
        )

    @staticmethod
    def compute_health_score(
        signals: HealthSignals,
        signal_weights: list[HeuristicSignalWeight],
        *,
        excluded_signals: set[str] | None = None,
    ) -> float:
        """Compute the heuristic health score (0-100) with weight redistribution.

        When a signal is in *excluded_signals*, its configured weight is
        redistributed proportionally to the remaining signals.  This handles
        both star-noise (popularity excluded) and missing metadata (freshness
        excluded when ``pushed_at`` is ``None``).

        Parameters
        ----------
        signals:
            Health signal values (each 0-100).
        signal_weights:
            Configured heuristic signal weights (must sum to 1.0).
        excluded_signals:
            Signal names whose weights should be redistributed (e.g.
            ``{"popularity"}`` for star-noise, ``{"freshness"}`` when
            ``pushed_at`` is ``None``).

        Returns
        -------
        float
            Weighted health score in the range [0, 100].
        """
        excluded = excluded_signals or set()

        # Build a mutable weight map from the config.
        weight_map: dict[str, float] = {
            sw.signal: sw.weight
            for sw in signal_weights
            if sw.signal not in excluded
        }

        # Redistribute excluded signal weights proportionally.
        excluded_weight = sum(
            sw.weight for sw in signal_weights if sw.signal in excluded
        )
        if excluded_weight > 0 and weight_map:
            remaining_sum = sum(weight_map.values())
            if remaining_sum > 0:
                for sig in weight_map:
                    weight_map[sig] += excluded_weight * (
                        weight_map[sig] / remaining_sum
                    )

        # Build signal value map from the HealthSignals model.
        signal_values: dict[str, float] = {
            "freshness": signals.freshness,
            "popularity": signals.popularity,
            "source_trust": signals.source_trust,
        }

        return sum(
            signal_values.get(sig, 0.0) * w
            for sig, w in weight_map.items()
        )

    @staticmethod
    def compute_blended_score(
        llm_score: float,
        health_score: float,
        alpha: float = 0.85,
    ) -> float:
        """Blend the LLM quality score with the heuristic health score.

        Formula: ``blended = α × llm_score + (1 - α) × health_score``

        Parameters
        ----------
        llm_score:
            Weighted LLM metric score (0-100).
        health_score:
            Weighted heuristic health score (0-100).
        alpha:
            Blend ratio.  1.0 = LLM only, 0.0 = health only.

        Returns
        -------
        float
            Blended score in the range [0, 100].
        """
        return alpha * llm_score + (1 - alpha) * health_score
