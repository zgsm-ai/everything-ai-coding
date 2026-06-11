"""Per-type enrichment runner with budget enforcement and resume support.

This script is the **data-layer-aware** front door for incremental enrichment.
It is invoked once per resource type (``mcp`` / ``skill`` / ``rule`` / ``prompt``
/ ``plugin``) by the ``sync-test`` and ``sync`` workflows after
``merge_index.py --skip-enrichment`` has refreshed ``catalog/index.json``.

Responsibilities (see ``openspec/changes/harden-merge-pipeline/specs/
merge-pipeline-resilience/spec.md``):

* Read ``catalog/index.json`` (or a mock fixture) and filter to one type.
* Apply the persistent failure ledger: skip quarantined entries and entries
  whose ``next_retry_after`` has not yet elapsed.
* Apply the per-type checkpoint: resume from previously completed ids.
* Hand the remaining entries to :func:`scripts.eval_bridge.run_eval` in
  bounded mini-batches so a soft wall-clock budget can interrupt cleanly.
* Persist the partial enrichment artifact, the updated checkpoint and the
  updated failure ledger atomically.
* Never modify ``catalog/index.json`` itself — that is the merge layer's
  job during the next aggregation step.

The script exits 0 even when the budget triggers a graceful stop, so the CI
job can keep running other cells. Hard failures still raise.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Sibling-import pattern: works when invoked as ``python scripts/run_enrichment.py``
# from the repo root (puts ``scripts/`` on sys.path).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from enrichment_checkpoint import Checkpoint  # noqa: E402
from eval_bridge import (  # noqa: E402
    _compute_rubric_version_for_task,
    resolve_task_name,
    run_eval,
)
from eval_failure_log import FailureLog, _atomic_write_json  # noqa: E402
from utils import load_index  # noqa: E402

logger = logging.getLogger(__name__)

VALID_TYPES = ("mcp", "skill", "rule", "prompt", "plugin")
DEFAULT_BUDGET_BATCH_SIZE = 50
DEFAULT_PER_BATCH_ESTIMATE_SECONDS = 60.0


def _utcnow_iso() -> str:
    """Return current UTC time as an ISO 8601 string (Z suffix normalized)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scripts.run_enrichment",
        description=(
            "Per-type enrichment runner. Reads the data-layer catalog, "
            "applies failure-ledger + checkpoint filtering, runs the eval "
            "harness, and writes a partial enrichment artifact."
        ),
    )
    parser.add_argument(
        "--type",
        required=True,
        choices=VALID_TYPES,
        help="Resource type to evaluate.",
    )
    parser.add_argument(
        "--mock-mode",
        action="store_true",
        default=False,
        help="Read input from a fixture directory and write output under "
        "tests/_test_output/ instead of the real catalog.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Override output artifact path. Default: "
        "tests/_enrich_output/<type>.json (or tests/_test_output/<type>.json "
        "in mock mode).",
    )
    parser.add_argument(
        "--max-wall-seconds",
        type=int,
        default=0,
        help="Soft wall-clock budget in seconds. 0 = unlimited. When the "
        "remaining budget cannot safely fit another LLM batch, the script "
        "flushes state and exits 0.",
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path("catalog/index.json"),
        help="Catalog index path (ignored in --mock-mode).",
    )
    parser.add_argument(
        "--maintenance-dir",
        type=Path,
        default=None,
        help="Directory holding eval_failures.json and checkpoints/. Defaults "
        "to catalog/maintenance in normal mode and tests/_test_maintenance in "
        "--mock-mode (so mock runs never write under catalog/).",
    )
    parser.add_argument(
        "--mock-fixture-dir",
        type=Path,
        default=None,
        help="Mock fixture directory. Defaults to env MOCK_FIXTURE_DIR or "
        "tests/fixtures/enrichment_mock.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BUDGET_BATCH_SIZE,
        help=f"Mini-batch size for budget enforcement (default {DEFAULT_BUDGET_BATCH_SIZE}).",
    )
    parser.add_argument(
        "--remap-all",
        action="store_true",
        help="Ignore the checkpoint and treat ALL entries as pending. Every entry "
        "is re-emitted (served from the eval cache, so no new LLM calls) and "
        "re-mapped by aggregate_enrichment. Use this to backfill newly added "
        "map_result_to_entry fields (e.g. effective_score / content_quality) onto "
        "stable entries that would otherwise never be re-evaluated.",
    )
    return parser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_input_path(args: argparse.Namespace) -> Path:
    """Determine the input catalog/fixture path."""
    if args.mock_mode:
        if args.mock_fixture_dir is not None:
            base = Path(args.mock_fixture_dir)
        else:
            env = os.environ.get("MOCK_FIXTURE_DIR")
            base = Path(env) if env else Path("tests/fixtures/enrichment_mock")
        return base / f"{args.type}.json"
    return Path(args.catalog)


def _resolve_output_path(args: argparse.Namespace) -> Path:
    """Determine the output artifact path."""
    if args.output is not None:
        return Path(args.output)
    if args.mock_mode:
        return Path("tests/_test_output") / f"{args.type}.json"
    return Path("tests/_enrich_output") / f"{args.type}.json"


def _classify_skipped(
    entries: list[dict[str, Any]],
    failure_log: FailureLog,
    completed_ids: set[str],
) -> tuple[list[str], list[str]]:
    """Return (quarantined_ids, deferred_ids) for entries excluded from the run.

    quarantined: attempt_count >= QUARANTINE_THRESHOLD (terminal).
    deferred: ledger present, not quarantined, but next_retry_after still in the
    future (i.e. ``should_retry_now == False``).
    """
    quarantined: list[str] = []
    deferred: list[str] = []
    for entry in entries:
        eid = str(entry.get("id", ""))
        if not eid or eid in completed_ids:
            continue
        if failure_log.is_quarantined(eid):
            quarantined.append(eid)
            continue
        if eid in failure_log.failures and not failure_log.should_retry_now(eid):
            deferred.append(eid)
    return sorted(quarantined), sorted(deferred)


def _filter_deferred(
    pending: list[dict[str, Any]],
    failure_log: FailureLog,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Drop entries whose backoff window has not elapsed; return the deferred ids."""
    keep: list[dict[str, Any]] = []
    deferred: list[str] = []
    for entry in pending:
        eid = str(entry.get("id", ""))
        if eid in failure_log.failures and not failure_log.should_retry_now(eid):
            deferred.append(eid)
            continue
        keep.append(entry)
    return keep, sorted(deferred)


def _write_artifact(
    output_path: Path,
    type_: str,
    rubric_version: str,
    succeeded: list[dict[str, Any]],
    failed: list[str],
    skipped_quarantined: list[str],
    skipped_deferred: list[str],
) -> None:
    """Atomically write the partial enrichment artifact."""
    payload = {
        "type": type_,
        "rubric_version": rubric_version,
        "generated_at": _utcnow_iso(),
        "succeeded": succeeded,
        "failed": sorted(set(failed)),
        "skipped_quarantined": sorted(set(skipped_quarantined)),
        "skipped_deferred": sorted(set(skipped_deferred)),
    }
    _atomic_write_json(output_path, payload)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    type_ = args.type
    input_path = _resolve_input_path(args)
    output_path = _resolve_output_path(args)
    if args.maintenance_dir is not None:
        maintenance_dir = Path(args.maintenance_dir)
    elif args.mock_mode:
        # Keep mock runs entirely out of catalog/ — write ledger + checkpoints
        # to a sibling test-only directory.
        maintenance_dir = Path("tests/_test_maintenance")
    else:
        maintenance_dir = Path("catalog/maintenance")

    # ---- Load catalog / fixture ------------------------------------------------
    if not input_path.exists():
        if args.mock_mode:
            print(
                f"[type={type_}] mock fixture missing: {input_path}; nothing to do.",
                flush=True,
            )
            return 0
        print(
            f"[type={type_}] catalog input missing: {input_path}; nothing to do.",
            flush=True,
        )
        return 0

    entries_all = load_index(str(input_path))
    if not isinstance(entries_all, list):
        print(
            f"[type={type_}] catalog input has unexpected shape; nothing to do.",
            flush=True,
        )
        return 0

    # ---- Filter to type -------------------------------------------------------
    entries = [e for e in entries_all if isinstance(e, dict) and e.get("type") == type_]
    if not entries:
        print(
            f"[type={type_}] no entries for this type in {input_path}; exiting.",
            flush=True,
        )
        return 0

    # ---- Resolve rubric_version ------------------------------------------------
    task_name = resolve_task_name(type_)
    rubric_version = _compute_rubric_version_for_task(task_name) or "0"

    # ---- Initialize ledgers ----------------------------------------------------
    failure_log = FailureLog(
        maintenance_dir / "eval_failures.json",
        rubric_version=rubric_version,
    )
    checkpoint = Checkpoint(
        type_,
        maintenance_dir / "checkpoints" / f"{type_}.json",
        rubric_version=rubric_version,
    )

    all_ids = [str(e["id"]) for e in entries if e.get("id")]
    completed_ids, remaining_ids = checkpoint.load(
        all_entry_ids=all_ids,
        failure_log=failure_log,
    )
    completed_set = set(completed_ids)
    remaining_set = set(remaining_ids)

    # --remap-all backfill: re-process every entry (served from the eval cache,
    # no new LLM calls) so stable entries that are already "completed" still flow
    # through map_result_to_entry and gain newly-added fields. Quarantine/deferred
    # filtering below still applies; the checkpoint is rebuilt as entries
    # re-complete, so subsequent runs return to normal incremental behavior.
    if args.remap_all:
        remaining_set = set(all_ids)
        completed_set = set()

    # Classify what got dropped so we can surface it in the artifact.
    quarantined_ids, _deferred_at_load = _classify_skipped(
        entries, failure_log, completed_set
    )

    # Respect deferred entries (next_retry_after in the future). Checkpoint.load
    # drops only quarantined ids, so we still have to filter deferred here.
    pending_entries = [e for e in entries if str(e.get("id", "")) in remaining_set]
    pending_entries, deferred_ids = _filter_deferred(pending_entries, failure_log)

    total = len(entries)
    cached = len(completed_set)
    quarantined_count = len(quarantined_ids)
    to_evaluate = len(pending_entries)

    print(
        f"[type={type_}] starting: {total} total, {cached} cached, "
        f"{quarantined_count} quarantined, {to_evaluate} to evaluate",
        flush=True,
    )
    sys.stdout.flush()

    # ---- Run eval in mini-batches with budget enforcement ----------------------
    succeeded_records: list[dict[str, Any]] = []
    succeeded_ids: set[str] = set()
    skipped_quarantined = sorted(quarantined_ids)
    skipped_deferred = sorted(deferred_ids)
    budget_reached = False

    start_wall = time.monotonic()
    max_observed_batch_seconds: float = 0.0
    batch_size = max(1, int(args.batch_size))

    # CI sets EVAL_CONCURRENCY to tune throughput per-type; honor it here so
    # `run_eval` doesn't silently fall back to its built-in default of 4.
    try:
        eval_concurrency = int(os.environ.get("EVAL_CONCURRENCY", "0"))
    except ValueError:
        eval_concurrency = 0
    if eval_concurrency <= 0:
        eval_concurrency = 4  # eval_bridge.run_eval default; preserve explicit signal

    def _budget_remaining() -> float:
        if args.max_wall_seconds <= 0:
            return float("inf")
        return float(args.max_wall_seconds) - (time.monotonic() - start_wall)

    def _safe_to_start_batch() -> bool:
        if args.max_wall_seconds <= 0:
            return True
        # Without prior observations we have no basis to short-circuit, so
        # always allow the first batch through. Subsequent batches are gated
        # on the largest batch we've seen so far (a conservative estimate).
        if max_observed_batch_seconds <= 0:
            return _budget_remaining() > 0
        return _budget_remaining() >= max_observed_batch_seconds

    processed = 0
    batches = [
        pending_entries[i : i + batch_size]
        for i in range(0, len(pending_entries), batch_size)
    ]

    for batch_idx, batch in enumerate(batches):
        # Pre-flight: do we still have enough budget to safely run this batch?
        if not _safe_to_start_batch():
            elapsed = time.monotonic() - start_wall
            print(
                f"[type={type_}] budget reached: elapsed={elapsed:.0f}s, "
                f"budget={args.max_wall_seconds}s, "
                f"completed={processed}, remaining={len(pending_entries) - processed}",
                flush=True,
            )
            budget_reached = True
            break

        batch_start = time.monotonic()
        try:
            batch_results = run_eval(
                batch,
                concurrency=eval_concurrency,
                failure_log=failure_log,
                checkpoints_by_type={type_: checkpoint},
            )
        except Exception as exc:  # noqa: BLE001
            # Persist partial state so the next run can resume, then surface
            # the failure to the caller (CI / aggregate). Honor the spec
            # contract that only --max-wall-seconds budget exits return 0.
            logger.exception(
                "[type=%s] run_eval raised during batch %d: %s",
                type_,
                batch_idx,
                exc,
            )
            try:
                failure_log.save()
            except Exception:  # noqa: BLE001
                logger.warning("[type=%s] failure_log.save() failed during error recovery", type_)
            try:
                checkpoint.flush()
            except Exception:  # noqa: BLE001
                logger.warning("[type=%s] checkpoint.flush() failed during error recovery", type_)
            _write_artifact(
                output_path,
                type_=type_,
                rubric_version=rubric_version,
                succeeded=succeeded_records,
                failed=[
                    str(e["id"])
                    for e in pending_entries
                    if e.get("id") not in succeeded_ids and e.get("id") is not None
                ],
                skipped_quarantined=skipped_quarantined,
                skipped_deferred=skipped_deferred,
            )
            raise

        batch_seconds = time.monotonic() - batch_start
        if batch_seconds > max_observed_batch_seconds:
            max_observed_batch_seconds = batch_seconds

        for entry_id, result_dict in batch_results.items():
            if entry_id in succeeded_ids:
                continue
            succeeded_records.append(
                {"entry_id": entry_id, "evaluation": result_dict}
            )
            succeeded_ids.add(entry_id)
            # Cache short-circuit hits returned by run_eval bypass the chunk-1C
            # telemetry wrapper that normally calls Checkpoint.mark_completed.
            # Mark them here so subsequent runs resume past stable cached entries
            # rather than reprocessing them every cell.
            if entry_id in checkpoint.remaining_entry_ids:
                checkpoint.mark_completed(entry_id)

        processed += len(batch)

        if processed % 50 == 0 or batch_idx == len(batches) - 1:
            print(
                f"[type={type_}] progress: {processed}/{len(pending_entries)} processed, "
                f"{len(succeeded_ids)} succeeded so far",
                flush=True,
            )
            sys.stdout.flush()

        # Post-flight: if budget already exceeded, stop before the next batch.
        if args.max_wall_seconds > 0 and _budget_remaining() <= 0:
            elapsed = time.monotonic() - start_wall
            print(
                f"[type={type_}] budget reached: elapsed={elapsed:.0f}s, "
                f"budget={args.max_wall_seconds}s, "
                f"completed={processed}, remaining={len(pending_entries) - processed}",
                flush=True,
            )
            budget_reached = True
            break

    # ---- Compute "failed" set (pending but no result this run) -----------------
    pending_ids = {str(e.get("id", "")) for e in pending_entries if e.get("id")}
    failed_ids = sorted(pending_ids - succeeded_ids)

    # ---- Persist artifact + ledgers (always, even on budget short-circuit) -----
    _write_artifact(
        output_path,
        type_=type_,
        rubric_version=rubric_version,
        succeeded=succeeded_records,
        failed=failed_ids,
        skipped_quarantined=quarantined_ids,
        skipped_deferred=deferred_ids,
    )

    try:
        failure_log.save()
    except OSError as exc:
        logger.warning("[type=%s] failed to save failure ledger: %s", type_, exc)
    try:
        checkpoint.flush()
    except OSError as exc:
        logger.warning("[type=%s] failed to flush checkpoint: %s", type_, exc)

    elapsed_total = time.monotonic() - start_wall
    state = "budget_short_circuit" if budget_reached else "complete"
    print(
        f"[type={type_}] cell {state}: succeeded={len(succeeded_ids)} "
        f"failed={len(failed_ids)} wall_clock={elapsed_total:.0f}s "
        f"output={output_path}",
        flush=True,
    )
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
