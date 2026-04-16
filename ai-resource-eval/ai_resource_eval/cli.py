"""CLI entry point for ai-resource-eval.

Provides commands:
  run      — evaluate a catalog of AI coding resources
  review   — interactively review queued items
  ls       — list registered metrics or available tasks
  report   — generate summary statistics from results JSON
  cache    — cache management (stats, clear)
"""

from __future__ import annotations

import json
import os
import sys
from enum import Enum
from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv

load_dotenv()

app = typer.Typer(
    name="ai-resource-eval",
    help="LLM-as-judge evaluation harness for AI coding resources.",
)

# ---------------------------------------------------------------------------
# Subcommand groups
# ---------------------------------------------------------------------------

cache_app = typer.Typer(help="Cache management commands.")
app.add_typer(cache_app, name="cache")


# ---------------------------------------------------------------------------
# Enums for CLI options
# ---------------------------------------------------------------------------


class OnFailChoice(str, Enum):
    skip = "skip"
    queue = "queue"
    error = "error"


class ReportFormat(str, Enum):
    markdown = "markdown"
    json = "json"


class LsTarget(str, Enum):
    metrics = "metrics"
    tasks = "tasks"


# ---------------------------------------------------------------------------
# run command
# ---------------------------------------------------------------------------


@app.command()
def run(
    task: str = typer.Option(..., "--task", help="Task config name or path to YAML"),
    input: Path = typer.Option(  # noqa: A002
        ..., "--input", help="Path to input catalog JSON"
    ),
    output: Optional[Path] = typer.Option(
        None, "--output", help="Path to output results JSON (default: stdout)"
    ),
    judge: str = typer.Option("deepseek", "--judge", help="Judge backend name"),
    concurrency: Optional[int] = typer.Option(
        None, "--concurrency", help="Max concurrent evaluation threads"
    ),
    incremental: bool = typer.Option(
        False, "--incremental", help="Skip entries with cached results"
    ),
    no_interactive: bool = typer.Option(
        False, "--no-interactive", help="Disable interactive fetcher fallback"
    ),
    on_fail: OnFailChoice = typer.Option(
        OnFailChoice.skip,
        "--on-fail",
        help="Strategy for fetch failures: skip, queue, error",
    ),
    cache_dir: str = typer.Option(
        ".eval_cache", "--cache-dir", help="Directory for SQLite cache"
    ),
) -> None:
    """Run evaluation on a catalog of AI coding resources."""
    from rich.console import Console

    console = Console(stderr=True)

    # 1. Read input JSON
    if not input.exists():
        console.print(f"[red]Input file not found:[/red] {input}")
        raise typer.Exit(code=1)

    try:
        raw_items = json.loads(input.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        console.print(f"[red]Error reading input file:[/red] {exc}")
        raise typer.Exit(code=1)

    if not isinstance(raw_items, list):
        console.print("[red]Input JSON must be an array of catalog entries.[/red]")
        raise typer.Exit(code=1)

    from ai_resource_eval.api.types import EvalItem

    try:
        entries = [EvalItem.model_validate(item) for item in raw_items]
    except Exception as exc:
        console.print(f"[red]Error parsing catalog entries:[/red] {exc}")
        raise typer.Exit(code=1)

    # 2. Create judge from --judge flag + env vars
    #    LLM_* vars take precedence; JUDGE_* kept for backward compatibility.
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("JUDGE_API_KEY")
    if not api_key:
        console.print(
            "[red]LLM_API_KEY (or JUDGE_API_KEY) environment variable is required.[/red]"
        )
        raise typer.Exit(code=1)

    base_url = os.environ.get("LLM_BASE_URL") or os.environ.get("JUDGE_BASE_URL")
    model_override = os.environ.get("LLM_MODEL") or os.environ.get("JUDGE_MODEL")

    judge_instance = _create_judge(judge, api_key, base_url, model_override)

    # 3. Load task config(s) and run
    from ai_resource_eval.runner import EvalRunner
    from ai_resource_eval.tasks.loader import load_task_config, load_task_config_from_path

    # Type field → task config name mapping
    _TYPE_TO_TASK = {
        "mcp": "mcp_server",
        "skill": "skill",
        "rule": "rule",
        "prompt": "prompt",
    }

    all_results: list = []
    all_review_queue: list = []

    if task == "all":
        # Group entries by type, run each group with its own task config
        groups: dict[str, list[EvalItem]] = {}
        for entry in entries:
            entry_type = getattr(entry, "type", None) or "skill"
            groups.setdefault(entry_type, []).append(entry)

        for entry_type, group_entries in groups.items():
            task_name = _TYPE_TO_TASK.get(entry_type, "skill")
            try:
                task_config = load_task_config(task_name)
            except (FileNotFoundError, ValueError):
                console.print(
                    f"[yellow]No task config for type '{entry_type}', "
                    f"falling back to 'skill'[/yellow]"
                )
                task_config = load_task_config("skill")

            console.print(
                f"[bold]Running {task_name}[/bold] — "
                f"{len(group_entries)} entries"
            )

            runner = EvalRunner(
                task_config=task_config,
                judge=judge_instance,
                cache_dir=cache_dir,
                concurrency=concurrency,
                incremental=incremental,
                interactive=not no_interactive,
                on_fail=on_fail.value,
            )
            all_results.extend(runner.run(group_entries))
            all_review_queue.extend(runner.review_queue)
    else:
        # Single task config for all entries
        try:
            if task.endswith(".yaml") or task.endswith(".yml"):
                task_config = load_task_config_from_path(task)
            else:
                task_config = load_task_config(task)
        except (FileNotFoundError, ValueError) as exc:
            console.print(f"[red]Error loading task config:[/red] {exc}")
            raise typer.Exit(code=1)

        runner = EvalRunner(
            task_config=task_config,
            judge=judge_instance,
            cache_dir=cache_dir,
            concurrency=concurrency,
            incremental=incremental,
            interactive=not no_interactive,
            on_fail=on_fail.value,
        )
        all_results.extend(runner.run(entries))
        all_review_queue.extend(runner.review_queue)

    # 4. Write results to output (or stdout)
    results_data = [r.model_dump(mode="json") for r in all_results]
    results_json = json.dumps(results_data, indent=2, ensure_ascii=False, default=str)

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(results_json, encoding="utf-8")
        console.print(
            f"[green]Wrote {len(all_results)} results to {output}[/green]"
        )
    else:
        sys.stdout.write(results_json + "\n")

    # 5. Write review_queue.json if any queued entries
    if all_review_queue:
        queue_path = Path("review_queue.json")
        if output is not None:
            queue_path = output.parent / "review_queue.json"
        queue_path.write_text(
            json.dumps(all_review_queue, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        console.print(
            f"[yellow]{len(all_review_queue)} entries queued for review "
            f"-> {queue_path}[/yellow]"
        )

    console.print(
        f"[dim]Evaluated {len(all_results)}/{len(entries)} entries[/dim]"
    )


def _create_judge(
    judge_name: str,
    api_key: str,
    base_url: str | None = None,
    model: str | None = None,
) -> object:
    """Instantiate a judge backend by name."""
    from ai_resource_eval.judges.deepseek import DeepSeekJudge, judge_registry
    from ai_resource_eval.judges.openai_compat import OpenAICompatJudge

    if judge_name == "deepseek":
        kwargs: dict = {"api_key": api_key}
        if model:
            kwargs["model"] = model
        judge_obj = DeepSeekJudge(**kwargs)
        # Override base_url if explicitly provided via env
        if base_url:
            judge_obj.base_url = base_url.rstrip("/")
        return judge_obj

    if judge_name == "openai":
        if not base_url:
            base_url = "https://api.openai.com"
        return OpenAICompatJudge(
            base_url=base_url,
            api_key=api_key,
            model=model or "gpt-4o-mini",
        )

    # Try the judge registry for custom providers
    try:
        judge_cls = judge_registry.get(judge_name)
        return judge_cls(api_key=api_key)  # type: ignore[call-arg]
    except KeyError:
        pass

    # Fallback: treat judge_name as a generic OpenAI-compatible endpoint
    if base_url:
        return OpenAICompatJudge(
            base_url=base_url,
            api_key=api_key,
            model=model or judge_name,
        )

    raise typer.BadParameter(
        f"Unknown judge '{judge_name}'. Available: deepseek, openai, "
        f"or set JUDGE_BASE_URL for a custom endpoint."
    )


# ---------------------------------------------------------------------------
# review command
# ---------------------------------------------------------------------------


@app.command()
def review(
    queue: Path = typer.Option(..., "--queue", help="Path to review_queue.json"),
) -> None:
    """Interactively review queued items."""
    from rich.console import Console
    from rich.table import Table

    console = Console()

    if not queue.exists():
        console.print(f"[red]Queue file not found:[/red] {queue}")
        raise typer.Exit(code=1)

    try:
        items = json.loads(queue.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        console.print(f"[red]Error reading queue file:[/red] {exc}")
        raise typer.Exit(code=1)

    if not isinstance(items, list) or len(items) == 0:
        console.print("[yellow]No items in the review queue.[/yellow]")
        raise typer.Exit(code=0)

    console.print(f"\n[bold]Review Queue[/bold] — {len(items)} items\n")

    reviewed = []
    for i, item in enumerate(items, 1):
        console.print(f"\n[bold cyan]--- Item {i}/{len(items)} ---[/bold cyan]")

        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Field", style="bold")
        table.add_column("Value")

        table.add_row("ID", str(item.get("id", "N/A")))
        table.add_row("Name", str(item.get("name", "N/A")))
        table.add_row("Source", str(item.get("source_url", "N/A")))
        table.add_row("Description", str(item.get("description", "N/A")))
        table.add_row("Reason", str(item.get("_review_reason", "N/A")))

        console.print(table)

        try:
            decision = typer.prompt(
                "\nDecision (accept/reject/skip)",
                default="skip",
            )
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Review interrupted.[/yellow]")
            break

        item["_review_decision"] = decision
        reviewed.append(item)
        console.print(f"  -> {decision}")

    # Write reviewed items back
    if reviewed:
        out_path = queue.parent / f"reviewed_{queue.name}"
        out_path.write_text(
            json.dumps(reviewed, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        console.print(
            f"\n[green]Reviewed {len(reviewed)} items -> {out_path}[/green]"
        )


# ---------------------------------------------------------------------------
# ls command
# ---------------------------------------------------------------------------


@app.command(name="ls")
def ls_cmd(
    target: LsTarget = typer.Argument(..., help="What to list: 'metrics' or 'tasks'"),
) -> None:
    """List registered metrics or available task configurations."""
    from rich.console import Console
    from rich.table import Table

    console = Console()

    if target == LsTarget.metrics:
        from ai_resource_eval.metrics.prompt_builder import metric_registry

        all_metrics = metric_registry.list_all()

        table = Table(title="Registered Metrics")
        table.add_column("Name", style="bold")
        table.add_column("Requires Content")

        for name, metric in sorted(all_metrics.items()):
            table.add_row(name, str(metric.requires_content))

        console.print(table)
        console.print(f"\n[dim]{len(all_metrics)} metrics registered[/dim]")

    elif target == LsTarget.tasks:
        from ai_resource_eval.tasks.loader import list_available_tasks

        tasks = list_available_tasks()

        table = Table(title="Available Tasks")
        table.add_column("Task Name", style="bold")

        for task_name in tasks:
            table.add_row(task_name)

        console.print(table)
        console.print(f"\n[dim]{len(tasks)} tasks available[/dim]")


# ---------------------------------------------------------------------------
# report command
# ---------------------------------------------------------------------------


@app.command()
def report(
    input: Path = typer.Option(  # noqa: A002
        ..., "--input", help="Path to results JSON"
    ),
    format: ReportFormat = typer.Option(  # noqa: A002
        ReportFormat.markdown,
        "--format",
        help="Output format: markdown or json",
    ),
) -> None:
    """Generate summary statistics from evaluation results."""
    from rich.console import Console

    console = Console()

    if not input.exists():
        console.print(f"[red]Input file not found:[/red] {input}")
        raise typer.Exit(code=1)

    try:
        results_data = json.loads(input.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        console.print(f"[red]Error reading results file:[/red] {exc}")
        raise typer.Exit(code=1)

    if not isinstance(results_data, list):
        console.print("[red]Results JSON must be an array.[/red]")
        raise typer.Exit(code=1)

    stats = _compute_report_stats(results_data)

    if format == ReportFormat.json:
        sys.stdout.write(json.dumps(stats, indent=2, ensure_ascii=False) + "\n")
    else:
        _print_markdown_report(stats)


def _compute_report_stats(results: list[dict]) -> dict:
    """Compute summary statistics from a list of result dicts."""
    total = len(results)

    # Decision distribution
    decision_counts: dict[str, int] = {"accept": 0, "review": 0, "reject": 0}
    for r in results:
        decision = r.get("decision", "unknown")
        if decision in decision_counts:
            decision_counts[decision] += 1

    # Score histogram (buckets: 0-20, 20-40, 40-60, 60-80, 80-100)
    histogram: dict[str, int] = {
        "0-20": 0,
        "20-40": 0,
        "40-60": 0,
        "60-80": 0,
        "80-100": 0,
    }
    scores: list[float] = []
    for r in results:
        score = r.get("final_score")
        if score is not None:
            scores.append(float(score))
            if score < 20:
                histogram["0-20"] += 1
            elif score < 40:
                histogram["20-40"] += 1
            elif score < 60:
                histogram["40-60"] += 1
            elif score < 80:
                histogram["60-80"] += 1
            else:
                histogram["80-100"] += 1

    # Per-metric averages
    metric_scores: dict[str, list[float]] = {}
    for r in results:
        metrics = r.get("metrics", {})
        for metric_name, metric_data in metrics.items():
            if isinstance(metric_data, dict) and "score" in metric_data:
                metric_scores.setdefault(metric_name, []).append(
                    float(metric_data["score"])
                )

    metric_averages: dict[str, float] = {}
    for name, vals in sorted(metric_scores.items()):
        metric_averages[name] = round(sum(vals) / len(vals), 2) if vals else 0.0

    avg_score = round(sum(scores) / len(scores), 2) if scores else 0.0
    min_score = round(min(scores), 2) if scores else 0.0
    max_score = round(max(scores), 2) if scores else 0.0

    return {
        "total": total,
        "decisions": decision_counts,
        "score_histogram": histogram,
        "score_stats": {
            "mean": avg_score,
            "min": min_score,
            "max": max_score,
        },
        "metric_averages": metric_averages,
    }


def _print_markdown_report(stats: dict) -> None:
    """Print a Markdown-formatted report to stdout."""
    total = stats["total"]
    decisions = stats["decisions"]
    histogram = stats["score_histogram"]
    score_stats = stats["score_stats"]
    metric_avgs = stats["metric_averages"]

    lines = [
        "# Evaluation Report",
        "",
        f"**Total entries evaluated:** {total}",
        "",
        "## Decision Distribution",
        "",
        f"| Decision | Count | Percentage |",
        f"|----------|-------|------------|",
    ]

    for decision, count in decisions.items():
        pct = f"{count / total * 100:.1f}%" if total > 0 else "0.0%"
        lines.append(f"| {decision} | {count} | {pct} |")

    lines.extend([
        "",
        "## Score Statistics",
        "",
        f"- **Mean:** {score_stats['mean']}",
        f"- **Min:** {score_stats['min']}",
        f"- **Max:** {score_stats['max']}",
        "",
        "## Score Histogram",
        "",
        "| Range | Count |",
        "|-------|-------|",
    ])

    for bucket, count in histogram.items():
        lines.append(f"| {bucket} | {count} |")

    if metric_avgs:
        lines.extend([
            "",
            "## Metric Averages",
            "",
            "| Metric | Average Score |",
            "|--------|--------------|",
        ])
        for name, avg in metric_avgs.items():
            lines.append(f"| {name} | {avg} |")

    sys.stdout.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# cache stats command
# ---------------------------------------------------------------------------


@cache_app.command(name="stats")
def cache_stats(
    cache_dir: str = typer.Option(
        ".eval_cache", "--cache-dir", help="Directory for SQLite cache"
    ),
) -> None:
    """Display cache statistics."""
    from rich.console import Console
    from rich.table import Table

    from ai_resource_eval.cache import EvalCache

    console = Console()

    db_path = Path(cache_dir) / "eval_cache.db"
    if not db_path.exists():
        console.print(f"[yellow]No cache database found at {db_path}[/yellow]")
        raise typer.Exit(code=0)

    cache = EvalCache(db_path=db_path)
    try:
        stats = cache.stats()
    finally:
        cache.close()

    table = Table(title="Cache Statistics")
    table.add_column("Metric", style="bold")
    table.add_column("Value")

    table.add_row("Entries", str(stats["entries"]))
    table.add_row("Total Cost (USD)", f"${stats['total_cost_usd']:.4f}")
    table.add_row("Total Prompt Tokens", f"{stats['total_prompt_tokens']:,}")
    table.add_row("Total Completion Tokens", f"{stats['total_completion_tokens']:,}")
    table.add_row("Session Hits", str(stats["session_hits"]))
    table.add_row("Session Misses", str(stats["session_misses"]))
    table.add_row("Hit Rate", f"{stats['hit_rate']:.1%}")

    console.print(table)


# ---------------------------------------------------------------------------
# cache clear command
# ---------------------------------------------------------------------------


@cache_app.command(name="clear")
def cache_clear(
    expired: bool = typer.Option(
        False, "--expired", help="Only clear expired entries"
    ),
    cache_dir: str = typer.Option(
        ".eval_cache", "--cache-dir", help="Directory for SQLite cache"
    ),
) -> None:
    """Clear cache entries."""
    from rich.console import Console

    from ai_resource_eval.cache import EvalCache

    console = Console()

    db_path = Path(cache_dir) / "eval_cache.db"
    if not db_path.exists():
        console.print(f"[yellow]No cache database found at {db_path}[/yellow]")
        raise typer.Exit(code=0)

    cache = EvalCache(db_path=db_path)
    try:
        if expired:
            deleted = cache.cleanup_expired()
            console.print(
                f"[green]Cleared {deleted} expired cache entries.[/green]"
            )
        else:
            # Clear all: get count first, then delete
            stats = cache.stats()
            count = stats["entries"]
            conn = cache._conn()
            conn.execute("DELETE FROM eval_cache")
            conn.commit()
            console.print(
                f"[green]Cleared all {count} cache entries.[/green]"
            )
    finally:
        cache.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    app()
