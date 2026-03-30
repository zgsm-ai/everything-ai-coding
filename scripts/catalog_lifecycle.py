#!/usr/bin/env python3
"""Helpers for lifecycle metadata preservation and maintenance queues."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

try:
    from .utils import normalize_source_url
except ImportError:
    from utils import normalize_source_url


LIFECYCLE_TYPES = {"mcp", "skill"}
STALE_PRIORITY = {"abandoned": 0, "stale": 1, "active": 2}


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        if "T" in value:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            parsed = datetime.fromisoformat(f"{value}T00:00:00+00:00")
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _identity_keys(entry: dict[str, Any]) -> list[tuple[str, str]]:
    entry_type = str(entry.get("type", "")).strip().lower()
    keys: list[tuple[str, str]] = []
    entry_id = entry.get("id")
    if entry_id:
        keys.append((entry_type, f"id:{entry_id}"))
    source_url = entry.get("source_url")
    if source_url:
        keys.append((entry_type, f"url:{normalize_source_url(source_url)}"))
    return keys


def overlay_added_at(
    regenerated: list[dict[str, Any]],
    existing: list[dict[str, Any]],
    *,
    today: str,
) -> list[dict[str, Any]]:
    existing_map: dict[tuple[str, str], str] = {}
    for entry in existing:
        entry_type = str(entry.get("type", "")).strip().lower()
        if entry_type not in LIFECYCLE_TYPES:
            continue
        added_at = entry.get("added_at")
        if not added_at:
            continue
        for key in _identity_keys(entry):
            existing_map.setdefault(key, added_at)

    result: list[dict[str, Any]] = []
    for entry in regenerated:
        cloned = dict(entry)
        entry_type = str(cloned.get("type", "")).strip().lower()
        if entry_type in LIFECYCLE_TYPES:
            preserved = None
            for key in _identity_keys(cloned):
                preserved = existing_map.get(key)
                if preserved:
                    break
            cloned["added_at"] = preserved or today
        else:
            cloned.pop("added_at", None)
        result.append(cloned)
    return result


def backfill_missing_added_at(
    entries: list[dict[str, Any]],
    *,
    today: str,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for entry in entries:
        cloned = dict(entry)
        entry_type = str(cloned.get("type", "")).strip().lower()
        if entry_type in LIFECYCLE_TYPES and not cloned.get("added_at"):
            candidate_dates: list[str] = []
            pushed_at = cloned.get("pushed_at")
            if isinstance(pushed_at, str) and pushed_at:
                candidate_dates.append(pushed_at[:10])
            last_synced = cloned.get("last_synced")
            if isinstance(last_synced, str) and last_synced:
                candidate_dates.append(last_synced[:10])
            cloned["added_at"] = min(candidate_dates) if candidate_dates else today
        result.append(cloned)
    return result


def build_incremental_recrawl_candidates(
    entries: list[dict[str, Any]],
    existing_state: dict[str, Any] | None,
    *,
    now: datetime,
    threshold_days: int,
    cooldown_days: int,
    max_candidates: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if now.tzinfo is None:
        reference_now = now.replace(tzinfo=timezone.utc)
    else:
        reference_now = now.astimezone(timezone.utc)

    state = {"items": dict((existing_state or {}).get("items", {}))}
    threshold = timedelta(days=threshold_days)
    cooldown = timedelta(days=cooldown_days)
    candidates: list[dict[str, Any]] = []

    for entry in entries:
        entry_type = str(entry.get("type", "")).strip().lower()
        if entry_type not in LIFECYCLE_TYPES:
            continue

        added_at = _parse_date(entry.get("added_at"))
        if not added_at or reference_now - added_at < threshold:
            continue

        state_key = f"{entry.get('id')}::{entry_type}"
        item_state = state["items"].get(state_key, {})
        last_queued = _parse_date(item_state.get("last_queued_at"))
        if last_queued and reference_now - last_queued < cooldown:
            continue

        freshness_label = str(entry.get("health", {}).get("freshness_label", "active"))
        priority = STALE_PRIORITY.get(freshness_label, len(STALE_PRIORITY))
        candidates.append(
            {
                "id": entry.get("id"),
                "type": entry_type,
                "name": entry.get("name"),
                "source_url": entry.get("source_url"),
                "added_at": entry.get("added_at"),
                "enqueue_reason": "age-threshold",
                "enqueued_at": reference_now.date().isoformat(),
                "priority": priority,
                "freshness_label": freshness_label,
            }
        )
        state["items"][state_key] = {
            **item_state,
            "last_queued_at": reference_now.date().isoformat(),
            "last_enqueue_reason": "age-threshold",
        }

    candidates.sort(key=lambda item: (item["priority"], item.get("id") or ""))
    return candidates[:max_candidates], state
