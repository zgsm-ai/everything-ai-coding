"""Decision logic: map final_score + hard rules to accept/review/reject."""

from __future__ import annotations

from ai_resource_eval.api.types import ThresholdsConfig


def judge_decision(
    final_score: float,
    coding_relevance_score: int,
    thresholds: ThresholdsConfig,
) -> str:
    """Determine the evaluation decision based on score and hard rules.

    Decision logic:

    1. Threshold determination:
       - ``final_score >= accept_threshold`` → ``"accept"``
       - ``review_threshold <= final_score < accept_threshold`` → ``"review"``
       - ``final_score < review_threshold`` → ``"reject"``

    2. Hard rule — coding_relevance cap:
       - If ``coding_relevance_score <= 1``, the decision is capped at
         ``"review"`` (i.e., ``"accept"`` is downgraded to ``"review"``).

    Parameters
    ----------
    final_score:
        Weighted aggregate score (0-100).
    coding_relevance_score:
        The coding_relevance metric score (1-5).
    thresholds:
        Accept and review threshold values.

    Returns
    -------
    str
        One of ``"accept"``, ``"review"``, or ``"reject"``.
    """
    # 1. Threshold determination.
    if final_score >= thresholds.accept:
        decision = "accept"
    elif final_score >= thresholds.review:
        decision = "review"
    else:
        decision = "reject"

    # 2. Hard rule: coding_relevance <= 2 caps at "review".
    if coding_relevance_score <= 2 and decision == "accept":
        decision = "review"

    return decision
