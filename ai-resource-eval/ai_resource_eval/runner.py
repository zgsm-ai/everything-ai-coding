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
    McpInstallabilityData,
    MetricResult,
    SecurityScanResult,
    TaskConfig,
)
from ai_resource_eval.cache import EvalCache
from ai_resource_eval.fetcher import (
    GitHubFetcher,
    InteractiveFetcher,
    PluginContentFetcher,
)
from ai_resource_eval.judges.base import BaseJudge
from ai_resource_eval.metrics.prompt_builder import (
    LLMEvalResponse,
    build_output_schema,
    build_system_prompt,
    metric_registry,
)
from ai_resource_eval.metrics.security_scan_prompt import (
    LLMSecurityResponse,
    SECURITY_SCAN_SYSTEM_PROMPT,
    build_security_output_schema,
    build_security_user_prompt,
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
        self._mcp_installability = task_config.mcp_installability
        self._security_scan = getattr(task_config, "security_scan", False)

        # Pre-build system prompt and schema (same for all entries).
        # security_scan task uses a dedicated prompt/schema (no metric rubrics,
        # no enrichment block); it also runs through its own runner branch so
        # the metric/enrichment prompt is never consulted for that task.
        if self._security_scan:
            self._system_prompt = SECURITY_SCAN_SYSTEM_PROMPT
            self._output_schema = build_security_output_schema()
        else:
            self._system_prompt = build_system_prompt(
                self._metrics,
                enrichment=self._enrichment,
                mcp_installability=self._mcp_installability,
            )
            self._output_schema = build_output_schema(
                [m.name for m in self._metrics],
                enrichment=self._enrichment,
                mcp_installability=self._mcp_installability,
            )
        self._metric_names = [m.name for m in self._metrics]

        # Compute rubric version: "{major}.{sha8}"
        sha8 = hashlib.sha256(self._system_prompt.encode()).hexdigest()[:8]
        self._rubric_version = f"{task_config.rubric_major_version}.{sha8}"

        # Cache namespace: security_scan rows live in a separate namespace so
        # bumping security rubric_major_version doesn't invalidate quality
        # cache (and vice versa).
        self._cache_namespace: str | None = "security" if self._security_scan else None

        # Initialise fetcher
        self._github_fetcher = GitHubFetcher(
            content_paths=task_config.content_paths,
        )
        # Plugin bundle fetcher：用于 entry.type == "plugin" 的条目，将 plugin.json
        # + skills/agents/commands 拼成单个评估串。Layout 检测失败（无
        # .claude-plugin/plugin.json）时返 None，runner 会自动降级到
        # GitHubFetcher 走 README 评估，行为与现行 plugin task 等价。
        self._plugin_fetcher: PluginContentFetcher = PluginContentFetcher()

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

        health-only 路径（plugin task：``self._metrics == []``）：
        跳过 metric LLM 调用与 ``compute_final_score``；若 ``enrichment=True``
        仍发起一次 enrichment-only LLM 调用以获得 summary / tags 等字段；
        ``final_score = health_score``。
        """
        # 1. Fetch content
        fetch_result = self._fetch_content(entry)
        if fetch_result is None:
            return self._handle_fetch_failure(entry)

        content, content_hash = fetch_result
        if self._mcp_installability:
            install_metadata = self._build_install_metadata_block(entry)
            if install_metadata:
                content_hash = EvalCache.content_hash(
                    f"{content}\n\n{install_metadata}"
                )

        # security_scan task：完整走独立路径（独立 prompt / schema / cache namespace /
        # failure semantics — 解析失败返 None 不写 result，不影响主管线）。
        if self._security_scan:
            return self._eval_one_security(entry, content, content_hash)

        # 2. Check cache (incremental mode)
        if self._incremental:
            cached = self._check_cache(entry.id, content_hash)
            if cached is not None:
                return cached

        metric_results: dict[str, MetricResult] = {}
        enrichment: EnrichmentData | None = None
        mcp_installability: McpInstallabilityData | None = None
        llm_score: float | None = None
        judge_result: JudgeResult | None = None

        if self._metrics:
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

            # 5. Parse LLM response into MetricResults + enrichment/installability
            parsed = self._parse_metrics(judge_result)
            if parsed is None:
                logger.warning(
                    "Failed to parse LLM response for %s, skipping", entry.id
                )
                return None

            metric_results, enrichment, mcp_installability = parsed

            # 6. Compute LLM score via ScoringGovernor
            llm_score = ScoringGovernor.compute_final_score(
                metric_results, self._metric_weights
            )
        elif self._enrichment:
            # health-only + enrichment：发起 enrichment-only LLM 调用，仅产出
            # summary / summary_zh / tags / tech_stack / search_terms / highlights。
            # 失败时 enrichment 留空（不阻塞 health-only final_score）。
            user_prompt = self._build_user_prompt(entry, content)
            try:
                judge_result = self._judge.judge(
                    system_prompt=self._system_prompt,
                    user_prompt=user_prompt,
                    schema=self._output_schema,
                    pydantic_model=LLMEvalResponse,
                )
                self._total_cost_usd += judge_result.cost_usd
                parsed = self._parse_metrics(judge_result)
                if parsed is not None:
                    _, enrichment, mcp_installability = parsed
            except Exception:
                logger.debug(
                    "Enrichment-only LLM call failed for %s, continuing without it",
                    entry.id,
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
            if llm_score is None:
                # health-only：直接用 health_score 作为 final_score
                final_score = health_score
            else:
                final_score = ScoringGovernor.compute_blended_score(
                    llm_score,
                    health_score,
                    alpha=self._task_config.health_blend_alpha,
                )
        else:
            # 既无 heuristic signals 又无 LLM 维度：兜底用 0 分（理论上不会发生，
            # validate_weights 保证至少一侧非空）
            final_score = llm_score if llm_score is not None else 0.0

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
            mcp_installability=mcp_installability,
            health=health,
            llm_score=llm_score,
            final_score=final_score,
            decision=Decision(decision_str),
            star_weight=star_weight,
            content_hash=content_hash,
            rubric_version=self._rubric_version,
            # health-only + 无 enrichment 时 judge_result 为 None，model_id 留空
            model_id=judge_result.model_id if judge_result is not None else None,
            evaluated_at=datetime.now(timezone.utc),
        )

        # 12. Cache result（health-only 无 LLM 调用时 judge_result 为 None，
        # 用占位 JudgeResult 保留 cache 写入语义；后续短路 lookup 仍可命中）
        if judge_result is None:
            from ai_resource_eval.api.judge import JudgeResult as _JR

            judge_result = _JR(
                content="",
                cost_usd=0.0,
                prompt_tokens=0,
                completion_tokens=0,
                latency_ms=0,
                model_id="",
                structured=None,
            )
        self._cache_result(eval_result, content_hash, judge_result)

        return eval_result

    # ------------------------------------------------------------------
    # Security scan path
    # ------------------------------------------------------------------

    def _eval_one_security(
        self,
        entry: EvalItem,
        content: str,
        content_hash: str,
    ) -> EvalResult | None:
        """Run security_scan LLM call for a single entry.

        Returns an :class:`EvalResult` whose ``security`` field is populated and
        all metric / enrichment / health-derived fields are left at safe defaults
        (``metrics={}``, ``final_score=0``, ``decision=review``, ``health``
        defaults). The caller (eval_bridge) only reads ``result.security`` for
        this task, so the unused fields are inert filler that keeps the shared
        ``EvalResult`` schema happy.

        Failure modes (LLM error, JSON parse error, verdict↔risk_level mismatch
        rejected by :class:`SecurityScanResult` validator) all return ``None``
        without writing a cache row — per spec, missing ``security`` block means
        "not yet evaluated" and the next run will retry.
        """
        # Cache lookup (security namespace)
        if self._incremental:
            cached = self._check_cache(entry.id, content_hash)
            if cached is not None and cached.security is not None:
                return cached

        user_prompt = build_security_user_prompt(entry, content)

        try:
            judge_result = self._judge.judge(
                system_prompt=self._system_prompt,
                user_prompt=user_prompt,
                schema=self._output_schema,
                pydantic_model=LLMSecurityResponse,
            )
        except Exception:
            logger.exception("Security LLM call failed for %s", entry.id)
            return None

        if judge_result is None or judge_result.structured is None:
            logger.debug("Security LLM returned unparseable response for %s", entry.id)
            return None

        self._total_cost_usd += judge_result.cost_usd

        try:
            security = SecurityScanResult.model_validate(judge_result.structured)
        except Exception:
            logger.debug(
                "Security result for %s rejected by validator (verdict↔risk_level "
                "mismatch or schema violation); will retry next cycle",
                entry.id,
            )
            return None

        eval_result = EvalResult(
            entry_id=entry.id,
            metrics={},
            enrichment=None,
            mcp_installability=None,
            security=security,
            health=HealthSignals(),
            llm_score=None,
            final_score=0.0,
            decision=Decision.review,
            star_weight=1.0,
            content_hash=content_hash,
            rubric_version=self._rubric_version,
            model_id=judge_result.model_id,
            evaluated_at=datetime.now(timezone.utc),
        )
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
        # install_popularity 信号仅 skills.sh 派生条目可信。其它源（GitHub 搜索 /
        # anthropics/skills 镜像 / 手工 curated）无 install_count 字段，强行计 0
        # 会拉低混合分；从权重表中剔除并按比例重分配剩余权重，保持 health_score
        # 在「数据缺失」与「数据齐全」之间可比。
        install_count = getattr(entry, "install_count", None)
        if install_count is None or install_count <= 0:
            excluded.add("install_popularity")
        # manifest_completeness 信号仅 plugin 类型可信（由 sync_plugins_official
        # 写入 entry.manifest_completeness）。非 plugin entry 没有该字段——等价于
        # weight=0 + 按比例分回原 3 信号（freshness / popularity / source_trust）。
        # 与 install_popularity 同款 excluded 路径。
        if (
            getattr(entry, "type", None) != "plugin"
            or getattr(entry, "manifest_completeness", None) is None
        ):
            excluded.add("manifest_completeness")
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
        # plugin 源（add-plugins-category 决策 4）：marketplace 官方源 100，
        # superpowers-marketplace 95，社区 registry 70，curated 80，awesome list 50。
        "claude-plugins-official": 100,
        "anthropics/claude-plugins-official": 100,
        "superpowers-marketplace": 95,
        "obra/superpowers-marketplace": 95,
        "claude-plugins.dev": 70,
        "awesome-claude-plugins": 50,
        # 自动发现源（GitHub Search 主动捞）：未经人工策展，给与 unknown 同档的
        # 适度低信任值。显式登记表达"有意为之"而非靠默认兜底；source_trust 在
        # final_score 里影响极小（最多约 3.6 分摆动），主闸门仍是 LLM 内容质量。
        "github-trending": 40,
    }
    _SOURCE_TRUST_DEFAULT = 40  # unknown sources

    def _compute_health_signals(self, entry: EvalItem) -> HealthSignals:
        """Compute freshness / popularity / source_trust / install_popularity / manifest_completeness from entry metadata."""
        freshness = self._compute_freshness(entry)
        popularity = self._compute_popularity(entry)
        source_trust = self._compute_source_trust(entry)
        install_popularity = self._compute_install_popularity(entry)
        manifest_completeness = self._compute_manifest_completeness(entry)
        return HealthSignals(
            freshness=freshness,
            popularity=popularity,
            source_trust=source_trust,
            install_popularity=install_popularity,
            manifest_completeness=manifest_completeness,
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

    @staticmethod
    def _compute_manifest_completeness(entry: EvalItem) -> float:
        """Score 0-100 from entry.manifest_completeness (0.0–1.0).

        plugin 类型条目由 sync_plugins_official.py 计算 manifest_completeness
        字段（0.0 / 0.3 / 0.7 / 1.0 阶梯，详见 specs/plugins-category/spec.md
        Manifest completeness signal computation）。

        非 plugin 类型 entry 没有该字段——返回默认 100（满分），与 runner 的
        ``excluded_signals`` 路径配合使该信号在权重表中被剔除并按比例分回，
        与「该信号不存在」的语义等价。
        """
        mc = getattr(entry, "manifest_completeness", None)
        if mc is None:
            return 100.0
        try:
            v = float(mc)
        except (TypeError, ValueError):
            return 100.0
        # entry.manifest_completeness 约定为 0.0–1.0；放宽一点容错（如 0–100 直填）
        if v <= 1.0:
            v = v * 100.0
        return max(0.0, min(100.0, v))

    @staticmethod
    def _compute_install_popularity(entry: EvalItem) -> float:
        """Score 0-100 based on skills.sh install_count (log10 scale).

        公式: ``min(100, log10(max(install_count, 1)) / log10(100000) * 100)``

        约定: install_count = 100000 → 100 分；install_count ≤ 1 → 0 分。
        无 install_count 字段或值为 0/None → 0 分。
        """
        install_count = getattr(entry, "install_count", None)
        if not install_count or install_count <= 0:
            return 0.0
        # log10 标度归一到 [0, 100]，以 install_count=100000 为满分基准
        return min(
            100.0,
            math.log10(max(install_count, 1)) / math.log10(100000) * 100.0,
        )

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

        Routing:

        1. ``entry.type == "plugin"`` and has a source_url → try
           ``PluginContentFetcher`` first. When it returns ``None`` (no
           ``.claude-plugin/plugin.json`` at the target sub-path), fall through
           to ``GitHubFetcher`` so behaviour matches the legacy README-mode
           plugin evaluation.
        2. All other entries → ``GitHubFetcher`` directly.

        Tries GitHubFetcher first (or after plugin fallback).  If that fails
        and interactive mode is enabled, falls back to InteractiveFetcher.
        If the entry has a description and no source_url, uses the
        description as content.

        For monorepo entries where the fetched README is the shared repo-level
        README (not specific to this entry), the description is prepended to
        give the LLM entry-specific context.
        """
        github_content: str | None = None

        # Plugin routing: try plugin bundle fetch first, fall through to
        # GitHubFetcher when no plugin.json is found at the target.
        if entry.source_url and getattr(entry, "type", None) == "plugin":
            plugin_result = self._plugin_fetcher.fetch(entry.source_url)
            if plugin_result is not None:
                content, _ = plugin_result
                # Apply same monorepo-description-prepend logic as the GitHub
                # branch so plugin entries from monorepos (50+ plugins per
                # marketplace repo) get entry-specific context too.
                if self._is_monorepo_entry(entry) and entry.description:
                    content = (
                        f"## Resource Description\n{entry.description}\n\n"
                        f"## Plugin Bundle\n{content}"
                    )
                    return content, EvalCache.content_hash(content)
                return plugin_result
            # else: layout detector returned is_plugin=False → fall through
            # to GitHubFetcher path below for README-mode evaluation.

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
            namespace=self._cache_namespace,
        )
        cached = self._cache.get(cache_key)
        if cached is None:
            return None

        try:
            result_data = json.loads(cached.result_json)
            result = EvalResult.model_validate(result_data)
            # Mark as cached. Critical: override entry_id with the CURRENT
            # query's entry_id, not the cached row's. Cache lookup is keyed
            # on content_hash, so multiple entries sharing the same content
            # (e.g. 1000+ MCP entries with install={"method": "manual"})
            # hit the same row. The downstream pipeline (eval_bridge) maps
            # results back to entries by entry_id, so a cached entry_id from
            # a different entry would orphan the result and the current
            # entry never gets its security block written.
            result = result.model_copy(
                update={"model_id": "__cached__", "entry_id": entry_id}
            )
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
            namespace=self._cache_namespace,
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
        if self._mcp_installability:
            install_metadata = self._build_install_metadata_block(entry)
            if install_metadata:
                parts.append("\n")
                parts.append(install_metadata)
                parts.append("\n")

        parts.append("\n---\n\n")
        parts.append("## README Content\n\n")
        parts.append(content)

        return "".join(parts)

    @staticmethod
    def _build_install_metadata_block(entry: EvalItem) -> str:
        """Build structured install metadata for MCP installability prompts."""
        if not entry.install:
            return "## Catalog Install Metadata\n\ninstall: null"

        install = entry.install
        method = install.get("method")
        config = install.get("config")
        placeholder_hints = install.get("placeholder_hints")

        parts = ["## Catalog Install Metadata\n\n"]
        parts.append(f"method: {method if method is not None else 'null'}\n")
        parts.append("config:\n")
        parts.append(json.dumps(config, ensure_ascii=False, indent=2, sort_keys=True))
        parts.append("\n")
        if placeholder_hints:
            parts.append("placeholder_hints:\n")
            parts.append(
                json.dumps(
                    placeholder_hints,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
            )
            parts.append("\n")
        return "".join(parts).rstrip()

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def _parse_metrics(
        self, judge_result: JudgeResult
    ) -> tuple[
        dict[str, MetricResult],
        EnrichmentData | None,
        McpInstallabilityData | None,
    ] | None:
        """Parse the LLM response into MetricResult objects and optional enrichment.

        Returns a (metrics, enrichment, mcp_installability) tuple, or None if metric parsing fails.
        Enrichment parse failure is non-fatal: returns (metrics, None).
        """
        if judge_result.structured is None:
            return None

        # health-only + enrichment 路径：metric_names 为空，跳过 metrics 解析，
        # 直接尝试解析 enrichment 字段。
        if not self._metric_names:
            metrics: dict[str, MetricResult] = {}
            enrichment: EnrichmentData | None = None
            mcp_installability = self._parse_mcp_installability(judge_result)
            if self._enrichment:
                raw_enrichment = judge_result.structured.get("enrichment")
                if raw_enrichment and isinstance(raw_enrichment, dict):
                    try:
                        enrichment = EnrichmentData.model_validate(raw_enrichment)
                    except Exception:
                        logger.debug(
                            "Failed to parse enrichment (health-only), continuing without it"
                        )
            return metrics, enrichment, mcp_installability

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

        mcp_installability = self._parse_mcp_installability(judge_result)

        return metrics, enrichment, mcp_installability

    def _parse_mcp_installability(
        self, judge_result: JudgeResult
    ) -> McpInstallabilityData | None:
        """Parse optional MCP installability output."""
        if not self._mcp_installability or judge_result.structured is None:
            return None
        raw = judge_result.structured.get("mcp_installability")
        if raw and isinstance(raw, dict):
            try:
                return McpInstallabilityData.model_validate(raw)
            except Exception:
                logger.debug(
                    "Failed to parse MCP installability, using unknown fallback"
                )
        else:
            logger.debug("Missing MCP installability, using unknown fallback")
        return McpInstallabilityData(
            mcp_schema_valid=False,
            mcp_install_state="unknown",
            mcp_validation_tags=["insufficient_evidence"],
            mcp_installability_reason="LLM 未返回有效的 MCP 可用性判断。",
        )
