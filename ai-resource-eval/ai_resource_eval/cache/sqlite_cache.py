"""SQLite-based evaluation cache with content-hash keys.

Provides ``EvalCache`` — a WAL-mode SQLite cache that stores per-entry
evaluation results keyed by ``SHA-256(metric + ":" + content_hash + ":" +
rubric_version)``.  Content changes or rubric version bumps automatically
produce a different key, so stale entries are never served.

Design decisions (see ``openspec/changes/initial-harness/design.md`` D2):

* **WITHOUT ROWID** table — optimised for hash primary keys.
* **WAL journal mode** + ``busy_timeout=5000`` — concurrent readers with
  serialised writes, sufficient for the LLM-call throughput ceiling.
* **Connection-per-thread** via ``threading.local()`` — avoids SQLite's
  "objects created in a thread can only be used in that same thread" limitation.
* **INSERT OR REPLACE** for upserts — idempotent writes.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_TTL_DAYS = 30

_CREATE_TABLE_SQL = """\
CREATE TABLE IF NOT EXISTS eval_cache (
    cache_key         TEXT PRIMARY KEY,
    entry_id          TEXT    NOT NULL,
    content_hash      TEXT    NOT NULL,
    rubric_version    TEXT    NOT NULL,
    result_json       TEXT    NOT NULL,
    evaluated_at      TEXT    NOT NULL,
    expires_at        TEXT    NOT NULL,
    model_id          TEXT,
    prompt_tokens     INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    cost_usd          REAL    DEFAULT 0.0,
    latency_ms        INTEGER DEFAULT 0
) WITHOUT ROWID;
"""


# ---------------------------------------------------------------------------
# CacheEntry dataclass
# ---------------------------------------------------------------------------


@dataclass
class CacheEntry:
    """A single evaluation-cache entry.

    Mirrors the ``eval_cache`` table schema.  ``result_json`` stores the full
    ``EvalResult`` serialised as JSON text; the caller is responsible for
    deserialising it back into a Pydantic model.
    """

    cache_key: str
    entry_id: str
    content_hash: str
    rubric_version: str
    result_json: str
    evaluated_at: str
    expires_at: str
    model_id: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0


# ---------------------------------------------------------------------------
# EvalCache
# ---------------------------------------------------------------------------


class EvalCache:
    """Thread-safe SQLite evaluation cache.

    Parameters
    ----------
    db_path:
        File system path for the SQLite database.  Accepts ``str`` or
        ``pathlib.Path``.  Use ``":memory:"`` for in-memory databases (useful
        in tests, but obviously not persistent and not truly shareable across
        threads — each thread would get its own in-memory DB).
    ttl_days:
        Default time-to-live in days for new entries.
    """

    def __init__(
        self,
        db_path: str | Path = "eval_cache.db",
        ttl_days: int = _DEFAULT_TTL_DAYS,
    ) -> None:
        self._db_path = str(db_path)
        self._ttl_days = ttl_days
        self._local = threading.local()

        # Session-level hit/miss counters (not persisted).
        self._lock = threading.Lock()
        self._session_hits = 0
        self._session_misses = 0

        # Ensure the table exists on the creating thread.
        self._init_db(self._conn())

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def _conn(self) -> sqlite3.Connection:
        """Return a per-thread connection, creating one if necessary."""
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            self._set_pragmas(conn)
            self._local.conn = conn
        return conn

    @staticmethod
    def _set_pragmas(conn: sqlite3.Connection) -> None:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        conn.execute("PRAGMA synchronous=NORMAL;")

    @staticmethod
    def _init_db(conn: sqlite3.Connection) -> None:
        conn.execute(_CREATE_TABLE_SQL)
        conn.commit()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_iso(s: str) -> datetime:
        """Parse ISO-8601 timestamp, handling ``Z`` suffix for Python 3.10 compat."""
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, cache_key: str) -> CacheEntry | None:
        """Retrieve a cache entry by *cache_key*, returning ``None`` on miss.

        An entry whose ``expires_at`` is in the past is treated as a miss.
        """
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM eval_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()

        if row is None:
            with self._lock:
                self._session_misses += 1
            return None

        expires_at = self._parse_iso(row["expires_at"])
        now = datetime.now(timezone.utc)
        # Handle naive datetimes stored without tz info — treat as UTC.
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if expires_at < now:
            with self._lock:
                self._session_misses += 1
            return None

        with self._lock:
            self._session_hits += 1

        return CacheEntry(
            cache_key=row["cache_key"],
            entry_id=row["entry_id"],
            content_hash=row["content_hash"],
            rubric_version=row["rubric_version"],
            result_json=row["result_json"],
            evaluated_at=row["evaluated_at"],
            expires_at=row["expires_at"],
            model_id=row["model_id"],
            prompt_tokens=row["prompt_tokens"],
            completion_tokens=row["completion_tokens"],
            cost_usd=row["cost_usd"],
            latency_ms=row["latency_ms"],
        )

    def put(self, cache_key: str, entry: CacheEntry) -> None:
        """Insert or replace a cache entry (upsert).

        ``entry.cache_key`` is overridden by the explicit *cache_key*
        argument to enforce consistency.
        """
        conn = self._conn()
        conn.execute(
            """\
            INSERT OR REPLACE INTO eval_cache
                (cache_key, entry_id, content_hash, rubric_version,
                 result_json, evaluated_at, expires_at,
                 model_id, prompt_tokens, completion_tokens,
                 cost_usd, latency_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cache_key,
                entry.entry_id,
                entry.content_hash,
                entry.rubric_version,
                entry.result_json,
                entry.evaluated_at,
                entry.expires_at,
                entry.model_id,
                entry.prompt_tokens,
                entry.completion_tokens,
                entry.cost_usd,
                entry.latency_ms,
            ),
        )
        conn.commit()

    def cleanup_expired(self) -> int:
        """Delete all entries whose ``expires_at`` is in the past.

        Returns the number of rows deleted.
        """
        conn = self._conn()
        now_iso = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "DELETE FROM eval_cache WHERE expires_at < ?",
            (now_iso,),
        )
        deleted = conn.execute("SELECT changes()").fetchone()[0]
        conn.commit()
        return deleted

    def stats(self) -> dict[str, Any]:
        """Return aggregate statistics for the cache database and session.

        Keys returned:
        * ``entries`` — total number of rows in ``eval_cache``.
        * ``total_cost_usd`` — sum of ``cost_usd`` across all entries.
        * ``total_prompt_tokens`` — sum of ``prompt_tokens``.
        * ``total_completion_tokens`` — sum of ``completion_tokens``.
        * ``session_hits`` — cache hits in the current process session.
        * ``session_misses`` — cache misses in the current process session.
        * ``hit_rate`` — ``hits / (hits + misses)`` for the session, or 0.0.
        """
        conn = self._conn()
        row = conn.execute(
            """\
            SELECT
                COUNT(*)              AS entries,
                COALESCE(SUM(cost_usd), 0.0)            AS total_cost_usd,
                COALESCE(SUM(prompt_tokens), 0)          AS total_prompt_tokens,
                COALESCE(SUM(completion_tokens), 0)      AS total_completion_tokens
            FROM eval_cache
            """
        ).fetchone()

        with self._lock:
            hits = self._session_hits
            misses = self._session_misses

        total = hits + misses
        hit_rate = hits / total if total > 0 else 0.0

        return {
            "entries": row["entries"],
            "total_cost_usd": row["total_cost_usd"],
            "total_prompt_tokens": row["total_prompt_tokens"],
            "total_completion_tokens": row["total_completion_tokens"],
            "session_hits": hits,
            "session_misses": misses,
            "hit_rate": hit_rate,
        }

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def make_key(
        metric: str,
        content_hash: str,
        rubric_version: str,
        config_hash: str | None = None,
    ) -> str:
        """Derive a deterministic cache key.

        Default format (per-metric caching):
            ``SHA-256(metric + ":" + content_hash + ":" + rubric_version)``

        When *config_hash* is provided (full-result caching where
        ``result_json`` includes computed fields like ``final_score`` and
        ``decision``), the scoring configuration is folded into the key so
        that weight/threshold changes automatically invalidate the entry:
            ``SHA-256(metric + ":" + content_hash + ":" + rubric_version + ":" + config_hash)``
        """
        raw = f"{metric}:{content_hash}:{rubric_version}"
        if config_hash is not None:
            raw = f"{raw}:{config_hash}"
        return hashlib.sha256(raw.encode()).hexdigest()

    @staticmethod
    def content_hash(text: str) -> str:
        """Return the SHA-256 hex digest of *text*."""
        return hashlib.sha256(text.encode()).hexdigest()

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def make_expires_at(self, ttl_days: int | None = None) -> str:
        """Return an ISO-8601 UTC timestamp *ttl_days* from now."""
        days = ttl_days if ttl_days is not None else self._ttl_days
        return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()

    def close(self) -> None:
        """Close the current thread's connection (if any)."""
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None
