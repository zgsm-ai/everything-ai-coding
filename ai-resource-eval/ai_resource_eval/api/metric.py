"""Abstract base class for evaluation metrics."""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseMetric(ABC):
    """Abstract base metric that concrete dimensions must implement.

    Each metric defines a single evaluation dimension (e.g. ``coding_relevance``,
    ``doc_completeness``).  It provides:

    * **name** — the dimension identifier used as key in ``EvalResult.metrics``.
    * **weight** — relative importance (set at construction time).
    * **requires_content** — whether the metric needs the full README text or
      can operate on metadata alone.
    * **build_rubric()** — returns a prompt fragment with behavioural anchors
      for scores 1-5, concatenated into the LLM system prompt at evaluation time.
    """

    def __init__(self, weight: float = 1.0) -> None:
        if weight < 0:
            raise ValueError(f"weight must be non-negative, got {weight}")
        self._weight = weight

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def name(self) -> str:
        """Dimension identifier (e.g. ``'coding_relevance'``)."""

    @property
    @abstractmethod
    def requires_content(self) -> bool:
        """``True`` if the metric needs README content; ``False`` for metadata-only."""

    @abstractmethod
    def build_rubric(self) -> str:
        """Return a prompt fragment with behavioural anchors for scores 1-5.

        The returned string is concatenated (with other metrics' rubrics) into
        the LLM system prompt when assembling an evaluation call.
        """

    # ------------------------------------------------------------------
    # Concrete helpers
    # ------------------------------------------------------------------

    @property
    def weight(self) -> float:
        """Relative weight of this metric in the final score."""
        return self._weight

    def __repr__(self) -> str:
        return f"{type(self).__name__}(name={self.name!r}, weight={self._weight})"
