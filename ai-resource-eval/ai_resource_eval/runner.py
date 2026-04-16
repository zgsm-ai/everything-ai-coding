"""EvalRunner: orchestrates the full evaluation pipeline.

Loads a TaskConfig, initialises cache/judge/fetcher, then evaluates each
EvalItem concurrently via ThreadPoolExecutor.

Single-entry pipeline:
  fetch content -> check cache -> build prompt -> judge -> parse result
  -> compute score -> cache put -> return EvalResult
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai_resource_eval.api.judge import JudgeResult
from ai_resource_eval.api.metric import BaseMetric
from ai_resource_eval.api.types import (
    Decision,
    EnrichmentData,
    EvalItem,
    EvalResult,
    HealthSignals,
    MetricResult,
    TaskConfig,
)
from ai_resource_eval.cache import EvalCache
from ai_resource_eval.fetcher import GitHubFetcher, InteractiveFetcher
from ai_resource_eval.judges.base import BaseJudge
from ai_resource_eval.metrics.prompt_builder import (
    LLMEvalResponse,
    build_output_schema,
    build_system_prompt,
    metric_registry,
)
from ai_resource_eval.scoring.decision import judge_decision
from ai_resource_eval.scoring.governor import ScoringGovernor
from ai_resource_eval.scoring.star_router import StarRouter

logger = logging.getLogger(__name__)

# Default concurrency matches typical LLM API rate limits.
_DEFAULT_CONCURRENCY = 3


class FetchError(Exception):
    """Raised when content cannot be fetched and on_fail='error'."""


class EvalRunner:
    """Orchestrates evaluation of a batch of catalog entries.

    Parameters
    ----------
    task_config:
        Parsed YAML task configuration (metrics, weights, thresholds, etc.).
    judge:
        An LLM judge backend implementing BaseJudge.
    cache_dir:
        Directory for the SQLite cache database.
    concurrency:
        Maximum number of concurrent evaluation threads.
    incremental:
        When True, check cache before calling the judge and return
        cached results for entries whose content has not changed.
    interactive:
        When True, use InteractiveFetcher as fallback for fetch failures.
    on_fail:
        Strategy for fetch failures in non-interactive mode.
        One of ``"skip"``, ``"queue"``, or ``"error"``.
    """

    def __init__(
        self,
        task_config: TaskConfig,
        judge: BaseJudge,
        cache_dir: str = ".cache",
        concurrency: int | None = None,
        incremental: bool = False,
        interactive: bool = True,
        on_fail: str = "skip",
    ) -> None:
        self._task_config = task_config
        self._judge = judge
        self._concurrency = concurrency or _DEFAULT_CONCURRENCY
        self._incremental = incremental
        self._interactive = interactive
        self._on_fail = on_fail

        # Initialise cache
        cache_path = Path(cache_dir)
        cache_path.mkdir(parents=True, exist_ok=True)
        self._cache = EvalCache(db_path=cache_path / "eval_cache.db")

        # Build metric instances from task config
        self._metrics: list[BaseMetric] = []
        self._metric_weights: dict[str, float] = {}
        for mw in task_config.metrics:
            metric = metric_registry.get(mw.metric)
            self._metrics.append(metric)
            self._metric_weights[mw.metric] = mw.weight

        # Enrichment flag from task config
        self._enrichment = task_config.enrichment

        # Pre-build system prompt and schema (same for all entries)
        self._system_prompt = build_system_prompt(
            self._metrics, enrichment=self._enrichment
        )
        self._metric_names = [m.name for m in self._metrics]
        self._output_schema = build_output_schema(
            self._metric_names, enrichment=self._enrichment
        )

        # Compute rubric version: "{major}.{sha8}"
        sha8 = hashlib.sha256(self._system_prompt.encode()).hexdigest()[:8]
        self._rubric_version = f"{task_config.rubric_major_version}.{sha8}"

        # Initialise fetcher
        self._github_fetcher = GitHubFetcher(
            content_paths=task_config.content_paths,
        )

        # Star router
        self._star_router = StarRouter(task_config.star_routing)

        # Review queue for entries that failed fetch in queue mode
        self._review_queue: list[dict[str, Any]] = []

        # Accumulated cost for progress display
        self._total_cost_usd: float = 0.0

        # Current batch of entries (set during run() for monorepo detection)
        self._all_entries: list[EvalItem] = []

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def review_queue(self) -> list[dict[str, Any]]:
        """Entries that were queued for manual review due to fetch failures."""
        return list(self._review_queue)

    @property
    def cache(self) -> EvalCache:
        """The underlying cache instance."""
        return self._cache

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, entries: list[EvalItem]) -> list[EvalResult]:
        """Evaluate all entries and return results.

        Uses ThreadPoolExecutor for concurrent evaluation.  Progress is
        displayed via rich Progress when running in a TTY.

        Parameters
        ----------
        entries:
            List of catalog entries to evaluate.

        Returns
        -------
        list[EvalResult]
            Evaluation results for entries that were successfully processed.
        """
        results: list[EvalResult] = []
        self._review_queue = []
        self._all_entries = entries
        self._total_cost_usd = 0.0

        try:
            from rich.progress import (
                BarColumn,
                MofNCompleteColumn,
                Progress,
                SpinnerColumn,
                TextColumn,
                TimeElapsedColumn,
            )

            progress = Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                MofNCompleteColumn(),
                TimeElapsedColumn(),
                TextColumn("{task.fields[status]}"),
                transient=False,
            )
        except ImportError:
            progress = None

        cache_hits = 0
        evaluated = 0
        skipped = 0

        if progress is not None:
            progress.start()
            task_id = progress.add_task(
                "Evaluating",
                total=len(entries),
                status="",
            )

        def _update_progress() -> None:
            if progress is not None:
                status = (
                    f"[green]{evaluated} eval[/green]  "
                    f"[cyan]{cache_hits} cached[/cyan]  "
                    f"[yellow]{skipped} skip[/yellow]  "
                    f"[dim]${self._total_cost_usd:.4f}[/dim]"
                )
                progress.update(task_id, advance=1, status=status)

        try:
            with ThreadPoolExecutor(max_workers=self._concurrency) as pool:
                future_to_entry = {
                    pool.submit(self._eval_one, entry, entries): entry
                    for entry in entries
                }

                for future in as_completed(future_to_entry):
                    entry = future_to_entry[future]
                    try:
                        result = future.result()
                        if result is not None:
                            results.append(result)
                            if result.model_id == "__cached__":
                                cache_hits += 1
                            else:
                                evaluated += 1
                        else:
                            skipped += 1
                    except FetchError:
                        skipped += 1
                    except Exception:
                        logger.exception(
                            "Unexpected error evaluating %s", entry.id
                        )
                        skipped += 1

                    _update_progress()
        finally:
            if progress is not None:
                progress.stop()

        return results

    # ------------------------------------------------------------------
    # Single-entry pipeline
    # ------------------------------------------------------------------

    def _eval_one(
        self,
        entry: EvalItem,
        all_entries: list[EvalItem],
    ) -> EvalResult | None:
        """Evaluate a single entry through the full pipeline.

        Returns None when the entry should be skipped (fetch failure with
        on_fail='skip' or queued).
        """
        # 1. Fetch content
        fetch_result = self._fetch_content(entry)
        if fetch_result is None:
            return self._handle_fetch_failure(entry)

        content, content_hash = fetch_result

        # 2. Check cache (incremental mode)
        if self._incremental:
            cached = self._check_cache(entry.id, content_hash)
            if cached is not None:
                return cached

        # 3. Build user prompt
        user_prompt = self._build_user_prompt(entry, content)

        # 4. Call judge
        judge_result = self._judge.judge(
            system_prompt=self._system_prompt,
            user_prompt=user_prompt,
            schema=self._output_schema,
            pydantic_model=LLMEvalResponse,
        )

        # Accumulate cost
        self._total_cost_usd += judge_result.cost_usd

        # 5. Parse LLM response into MetricResults + enrichment
        parsed = self._parse_metrics(judge_result)
        if parsed is None:
            logger.warning(
                "Failed to parse LLM response for %s, skipping", entry.id
            )
            return None

        metric_results, enrichment = parsed

        # 6. Compute LLM score via ScoringGovernor
        llm_score = ScoringGovernor.compute_final_score(
            metric_results, self._metric_weights
        )

        # 7. Compute health signals from entry metadata
        health = self._compute_health_signals(entry)

        # 8. Compute star_weight via StarRouter
        star_weight = self._star_router.compute_star_weight(
            entry, all_entries
        )

        # 9. Blend LLM score with health score (if heuristic signals configured)
        if self._task_config.heuristic_signals:
            excluded_signals = self._get_excluded_signals(entry, star_weight)
            health_score = ScoringGovernor.compute_health_score(
                health,
                self._task_config.heuristic_signals,
                excluded_signals=excluded_signals,
            )
            final_score = ScoringGovernor.compute_blended_score(
                llm_score,
                health_score,
                alpha=self._task_config.health_blend_alpha,
            )
        else:
            final_score = llm_score

        # 10. Make decision via judge_decision
        coding_relevance_score = metric_results.get(
            "coding_relevance", MetricResult(score=3)
        ).score
        decision_str = judge_decision(
            final_score,
            coding_relevance_score,
            self._task_config.thresholds,
        )

        # 11. Build EvalResult
        eval_result = EvalResult(
            entry_id=entry.id,
            metrics=metric_results,
            enrichment=enrichment,
            health=health,
            llm_score=llm_score,
            final_score=final_score,
            decision=Decision(decision_str),
            star_weight=star_weight,
            content_hash=content_hash,
            rubric_version=self._rubric_version,
            model_id=judge_result.model_id,
            evaluated_at=datetime.now(timezone.utc),
        )

        # 12. Cache result
        self._cache_result(eval_result, content_hash, judge_result)

        return eval_result

    # ------------------------------------------------------------------
    # Health signals
    # ------------------------------------------------------------------

    @staticmethod
    def _get_excluded_signals(entry: EvalItem, star_weight: float) -> set[str]:
        """Determine which health signals lack valid data and should be excluded.

        Excluded signal weights are redistributed proportionally to the
        remaining signals in ``ScoringGovernor.compute_health_score``.
        """
        excluded: set[str] = set()
        if getattr(entry, "pushed_at", None) is None:
            excluded.add("freshness")
        if star_weight == 0.0:
            excluded.add("popularity")
        return excluded

    # Source → trust score mapping (0-100).
    _SOURCE_TRUST: dict[str, float] = {
        "curated": 90,
        "mcp.so": 80,
        "awesome-mcp-servers": 70,
        "awesome-mcp-zh": 65,
        "awesome-cursorrules": 60,
        "anthropics/claude-code": 85,
        "anthropics-skills": 75,
        "prompts-chat": 50,
        "rules-2.1-optimized": 50,
    }
    _SOURCE_TRUST_DEFAULT = 40  # unknown sources

    def _compute_health_signals(self, entry: EvalItem) -> HealthSignals:
        """Compute freshness / popularity / source_trust from entry metadata."""
        freshness = self._compute_freshness(entry)
        popularity = self._compute_popularity(entry)
        source_trust = self._compute_source_trust(entry)
        return HealthSignals(
            freshness=freshness,
            popularity=popularity,
            source_trust=source_trust,
        )

    @staticmethod
    def _compute_freshness(entry: EvalItem) -> float:
        """Score 0-100 based on pushed_at recency.

        100 = pushed today, 0 = pushed ≥ 365 days ago (linear decay).
        """
        pushed_at = getattr(entry, "pushed_at", None)
        if not pushed_at:
            return 0.0
        try:
            if isinstance(pushed_at, str):
                ts = pushed_at.replace("Z", "+00:00")
                pushed_dt = datetime.fromisoformat(ts)
            else:
                pushed_dt = pushed_at
            if pushed_dt.tzinfo is None:
                pushed_dt = pushed_dt.replace(tzinfo=timezone.utc)
            age_days = (datetime.now(timezone.utc) - pushed_dt).days
            # Linear decay: 0 days → 100, 365+ days → 0
            return max(0.0, min(100.0, 100.0 * (1.0 - age_days / 365.0)))
        except (ValueError, TypeError):
            return 0.0

    @staticmethod
    def _compute_popularity(entry: EvalItem) -> float:
        """Score 0-100 based on stars (log10 scale).

        0 stars → 0, 10 → 25, 100 → 50, 1000 → 75, 10000+ → 100.
        """
        stars = getattr(entry, "stars", None)
        if not stars or stars <= 0:
            return 0.0
        # log10 scale: 1→0, 10→25, 100→50, 1000→75, 10000→100
        return min(100.0, 25.0 * math.log10(stars))

    def _compute_source_trust(self, entry: EvalItem) -> float:
        """Score 0-100 based on source field."""
        source = getattr(entry, "source", None) or ""
        return self._SOURCE_TRUST.get(source, self._SOURCE_TRUST_DEFAULT)

    # ------------------------------------------------------------------
    # Fetching
    # ------------------------------------------------------------------

    def _is_monorepo_entry(self, entry: EvalItem) -> bool:
        """Check if entry comes from a monorepo (many entries share same repo)."""
        repo = StarRouter.extract_repo(entry.source_url)
        if repo is None:
            return False
        counts = self._star_router._get_repo_counts(self._all_entries or [])
        return counts.get(repo, 0) >= self._task_config.star_routing.monorepo_threshold

    def _fetch_content(self, entry: EvalItem) -> tuple[str, str] | None:
        """Attempt to fetch content for an entry.

        Tries GitHubFetcher first.  If that fails and interactive mode is
        enabled, falls back to InteractiveFetcher.  If the entry has a
        description and no source_url, uses the description as content.

        For monorepo entries where the fetched README is the shared repo-level
        README (not specific to this entry), the description is prepended to
        give the LLM entry-specific context.
        """
        github_content: str | None = None

        # Try GitHub fetch if there is a source URL
        if entry.source_url:
            result = self._github_fetcher.fetch(entry.source_url)
            if result is not None:
                github_content = result[0]

                # If this is a monorepo entry and we have a description,
                # prepend the description so the LLM knows what specific
                # resource it's evaluating (the README may be repo-level).
                if self._is_monorepo_entry(entry) and entry.description:
                    content = (
                        f"## Resource Description\n{entry.description}\n\n"
                        f"## Repository README\n{github_content}"
                    )
                    return content, EvalCache.content_hash(content)

                return result

        # Fallback: use description if configured
        if (
            self._task_config.content_fallback == "description"
            and entry.description
        ):
            content = entry.description
            # If we fetched a repo-level README but it's not specific,
            # still include it as supplementary context
            if github_content:
                content = (
                    f"## Resource Description\n{entry.description}\n\n"
                    f"## Repository README (shared repo)\n{github_content}"
                )
            return content, EvalCache.content_hash(content)

        # Interactive fallback
        if self._interactive:
            try:
                from ai_resource_eval.fetcher import (
                    InteractiveFetcher,
                    RepomixFetcher,
                    WebFetcher,
                )

                interactive = InteractiveFetcher(
                    web_fetcher=WebFetcher(),
                    repomix_fetcher=RepomixFetcher(),
                )
                return interactive.fetch(entry)
            except Exception:
                logger.debug(
                    "Interactive fetcher failed for %s", entry.id
                )
                return None

        return None

    def _handle_fetch_failure(self, entry: EvalItem) -> EvalResult | None:
        """Handle a fetch failure according to on_fail strategy."""
        if self._on_fail == "queue":
            queue_entry = entry.model_dump()
            queue_entry["_review_reason"] = "fetch_failed"
            self._review_queue.append(queue_entry)
            return None
        elif self._on_fail == "error":
            raise FetchError(
                f"Failed to fetch content for {entry.id} "
                f"({entry.source_url})"
            )
        else:
            # "skip" — default
            logger.info("Skipping %s: content fetch failed", entry.id)
            return None

    # ------------------------------------------------------------------
    # Caching
    # ------------------------------------------------------------------

    def _check_cache(
        self, entry_id: str, content_hash: str
    ) -> EvalResult | None:
        """Check cache for a previous result matching this content.

        Returns an EvalResult with model_id='__cached__' on hit.
        """
        cache_key = EvalCache.make_key(
            metric="__full__",
            content_hash=content_hash,
            rubric_version=self._rubric_version,
        )
        cached = self._cache.get(cache_key)
        if cached is None:
            return None

        try:
            result_data = json.loads(cached.result_json)
            result = EvalResult.model_validate(result_data)
            # Mark as cached
            result = result.model_copy(update={"model_id": "__cached__"})
            return result
        except Exception:
            logger.debug("Cache entry for %s is invalid, re-evaluating", entry_id)
            return None

    def _cache_result(
        self,
        eval_result: EvalResult,
        content_hash: str,
        judge_result: JudgeResult,
    ) -> None:
        """Store an evaluation result in the cache."""
        from ai_resource_eval.cache import CacheEntry

        cache_key = EvalCache.make_key(
            metric="__full__",
            content_hash=content_hash,
            rubric_version=self._rubric_version,
        )

        entry = CacheEntry(
            cache_key=cache_key,
            entry_id=eval_result.entry_id,
            content_hash=content_hash,
            rubric_version=self._rubric_version,
            result_json=eval_result.model_dump_json(),
            evaluated_at=datetime.now(timezone.utc).isoformat(),
            expires_at=self._cache.make_expires_at(),
            model_id=judge_result.model_id,
            prompt_tokens=judge_result.prompt_tokens,
            completion_tokens=judge_result.completion_tokens,
            cost_usd=judge_result.cost_usd,
            latency_ms=judge_result.latency_ms,
        )
        self._cache.put(cache_key, entry)

    # ------------------------------------------------------------------
    # Prompt building
    # ------------------------------------------------------------------

    def _build_user_prompt(self, entry: EvalItem, content: str) -> str:
        """Build the user prompt with entry metadata and README content."""
        parts: list[str] = []

        parts.append(f"# Resource: {entry.name}\n")

        if entry.type:
            parts.append(f"Type: {entry.type}\n")
        if entry.description:
            parts.append(f"Description: {entry.description}\n")
        if entry.source_url:
            parts.append(f"Source: {entry.source_url}\n")
        if entry.stars is not None:
            parts.append(f"Stars: {entry.stars}\n")
        if entry.tags:
            parts.append(f"Tags: {', '.join(entry.tags)}\n")

        parts.append("\n---\n\n")
        parts.append("## README Content\n\n")
        parts.append(content)

        return "".join(parts)

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def _parse_metrics(
        self, judge_result: JudgeResult
    ) -> tuple[dict[str, MetricResult], EnrichmentData | None] | None:
        """Parse the LLM response into MetricResult objects and optional enrichment.

        Returns a (metrics, enrichment) tuple, or None if metric parsing fails.
        Enrichment parse failure is non-fatal: returns (metrics, None).
        """
        if judge_result.structured is None:
            return None

        raw_metrics = judge_result.structured.get("metrics")
        if not isinstance(raw_metrics, dict):
            return None

        metrics: dict[str, MetricResult] = {}
        for name in self._metric_names:
            if name not in raw_metrics:
                logger.warning("Missing metric %s in LLM response", name)
                return None
            try:
                metrics[name] = MetricResult.model_validate(raw_metrics[name])
            except Exception:
                logger.warning("Invalid metric result for %s", name)
                return None

        # Parse enrichment (non-fatal)
        enrichment: EnrichmentData | None = None
        if self._enrichment:
            raw_enrichment = judge_result.structured.get("enrichment")
            if raw_enrichment and isinstance(raw_enrichment, dict):
                try:
                    enrichment = EnrichmentData.model_validate(raw_enrichment)
                except Exception:
                    logger.debug("Failed to parse enrichment, continuing without it")

        return metrics, enrichment
