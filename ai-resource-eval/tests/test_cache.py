"""Tests for ai_resource_eval.cache.sqlite_cache — EvalCache and CacheEntry."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone

import pytest

from ai_resource_eval.cache.sqlite_cache import CacheEntry, EvalCache


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def cache(tmp_path):
    """Return an EvalCache backed by a temporary database file."""
    db = tmp_path / "test_cache.db"
    c = EvalCache(db_path=db)
    yield c
    c.close()


def _make_entry(
    cache_key: str = "k",
    entry_id: str = "test-entry",
    content_hash: str = "abc123",
    rubric_version: str = "1.abcd1234",
    result_json: str = '{"score": 4}',
    evaluated_at: str | None = None,
    expires_at: str | None = None,
    model_id: str = "deepseek-chat",
    prompt_tokens: int = 100,
    completion_tokens: int = 50,
    cost_usd: float = 0.01,
    latency_ms: int = 350,
) -> CacheEntry:
    now = datetime.now(timezone.utc)
    return CacheEntry(
        cache_key=cache_key,
        entry_id=entry_id,
        content_hash=content_hash,
        rubric_version=rubric_version,
        result_json=result_json,
        evaluated_at=evaluated_at or now.isoformat(),
        expires_at=expires_at or (now + timedelta(days=30)).isoformat(),
        model_id=model_id,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost_usd,
        latency_ms=latency_ms,
    )


# ===================================================================
# CacheEntry dataclass
# ===================================================================


class TestCacheEntry:
    """Tests for the CacheEntry dataclass."""

    def test_create_with_defaults(self):
        e = CacheEntry(
            cache_key="k",
            entry_id="eid",
            content_hash="ch",
            rubric_version="1.0",
            result_json="{}",
            evaluated_at="2026-01-01T00:00:00+00:00",
            expires_at="2026-02-01T00:00:00+00:00",
        )
        assert e.model_id is None
        assert e.prompt_tokens == 0
        assert e.completion_tokens == 0
        assert e.cost_usd == 0.0
        assert e.latency_ms == 0

    def test_create_with_all_fields(self):
        e = _make_entry()
        assert e.entry_id == "test-entry"
        assert e.model_id == "deepseek-chat"
        assert e.prompt_tokens == 100
        assert e.cost_usd == 0.01


# ===================================================================
# Static helpers
# ===================================================================


class TestStaticHelpers:
    """Tests for EvalCache.make_key and EvalCache.content_hash."""

    def test_content_hash_deterministic(self):
        h1 = EvalCache.content_hash("hello world")
        h2 = EvalCache.content_hash("hello world")
        assert h1 == h2

    def test_content_hash_is_sha256_hex(self):
        h = EvalCache.content_hash("test")
        assert len(h) == 64  # SHA-256 hex = 64 chars
        assert all(c in "0123456789abcdef" for c in h)

    def test_content_hash_changes_on_different_input(self):
        h1 = EvalCache.content_hash("README v1")
        h2 = EvalCache.content_hash("README v2")
        assert h1 != h2

    def test_make_key_deterministic(self):
        k1 = EvalCache.make_key("coding_relevance", "abc", "1.deadbeef")
        k2 = EvalCache.make_key("coding_relevance", "abc", "1.deadbeef")
        assert k1 == k2

    def test_make_key_is_sha256_hex(self):
        k = EvalCache.make_key("m", "c", "v")
        assert len(k) == 64
        assert all(c in "0123456789abcdef" for c in k)

    def test_make_key_format(self):
        """make_key should hash 'metric:content_hash:rubric_version'."""
        import hashlib

        expected = hashlib.sha256(b"m:c:v").hexdigest()
        assert EvalCache.make_key("m", "c", "v") == expected

    def test_make_key_different_metric(self):
        k1 = EvalCache.make_key("coding_relevance", "hash1", "1.0")
        k2 = EvalCache.make_key("doc_completeness", "hash1", "1.0")
        assert k1 != k2

    def test_make_key_different_content_hash(self):
        """Content change produces a different cache key (auto-invalidation)."""
        k1 = EvalCache.make_key("m", "hash_old", "1.0")
        k2 = EvalCache.make_key("m", "hash_new", "1.0")
        assert k1 != k2

    def test_make_key_different_rubric_version(self):
        """Rubric version change produces a different cache key."""
        k1 = EvalCache.make_key("m", "hash", "1.aaa")
        k2 = EvalCache.make_key("m", "hash", "2.bbb")
        assert k1 != k2

    # -- config_hash parameter -------------------------------------------

    def test_make_key_without_config_hash_unchanged(self):
        """Omitting config_hash produces the same key as the original spec."""
        import hashlib

        expected = hashlib.sha256(b"m:c:v").hexdigest()
        assert EvalCache.make_key("m", "c", "v") == expected
        assert EvalCache.make_key("m", "c", "v", config_hash=None) == expected

    def test_make_key_with_config_hash_differs(self):
        """Providing config_hash produces a different key than without."""
        k_without = EvalCache.make_key("m", "c", "v")
        k_with = EvalCache.make_key("m", "c", "v", config_hash="cfghash1")
        assert k_without != k_with

    def test_make_key_config_hash_format(self):
        """config_hash is appended as a fourth colon-separated segment."""
        import hashlib

        expected = hashlib.sha256(b"m:c:v:cfghash1").hexdigest()
        assert EvalCache.make_key("m", "c", "v", config_hash="cfghash1") == expected

    def test_make_key_different_config_hash(self):
        """Different scoring configs produce different cache keys."""
        k1 = EvalCache.make_key("m", "c", "v", config_hash="cfg_a")
        k2 = EvalCache.make_key("m", "c", "v", config_hash="cfg_b")
        assert k1 != k2

    def test_make_key_config_hash_deterministic(self):
        """Same config_hash always produces the same key."""
        k1 = EvalCache.make_key("m", "c", "v", config_hash="cfg_x")
        k2 = EvalCache.make_key("m", "c", "v", config_hash="cfg_x")
        assert k1 == k2


# ===================================================================
# Database initialisation & PRAGMAs
# ===================================================================


class TestDatabaseInit:
    """Tests for database initialisation and PRAGMA settings."""

    def test_wal_mode(self, cache):
        conn = cache._conn()
        mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        assert mode == "wal"

    def test_busy_timeout(self, cache):
        conn = cache._conn()
        timeout = conn.execute("PRAGMA busy_timeout;").fetchone()[0]
        assert timeout == 5000

    def test_synchronous_normal(self, cache):
        conn = cache._conn()
        # synchronous=NORMAL → 1
        sync = conn.execute("PRAGMA synchronous;").fetchone()[0]
        assert sync == 1

    def test_table_exists(self, cache):
        conn = cache._conn()
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='eval_cache'"
        ).fetchone()
        assert row is not None

    def test_in_memory_db(self):
        """An in-memory cache should work for single-thread tests."""
        c = EvalCache(db_path=":memory:")
        entry = _make_entry()
        c.put("k1", entry)
        assert c.get("k1") is not None
        c.close()


# ===================================================================
# get / put round-trip
# ===================================================================


class TestGetPut:
    """Tests for get() and put() operations."""

    def test_put_and_get(self, cache):
        entry = _make_entry(cache_key="k1", entry_id="e1")
        cache.put("k1", entry)
        result = cache.get("k1")
        assert result is not None
        assert result.entry_id == "e1"
        assert result.content_hash == "abc123"
        assert result.model_id == "deepseek-chat"
        assert result.prompt_tokens == 100
        assert result.completion_tokens == 50
        assert result.cost_usd == 0.01
        assert result.latency_ms == 350

    def test_get_miss(self, cache):
        result = cache.get("nonexistent")
        assert result is None

    def test_upsert_replaces(self, cache):
        entry1 = _make_entry(entry_id="old")
        cache.put("k1", entry1)

        entry2 = _make_entry(entry_id="new")
        cache.put("k1", entry2)

        result = cache.get("k1")
        assert result is not None
        assert result.entry_id == "new"

    def test_result_json_round_trip(self, cache):
        payload = {"metrics": {"coding_relevance": {"score": 4}}}
        entry = _make_entry(result_json=json.dumps(payload))
        cache.put("k1", entry)

        result = cache.get("k1")
        assert result is not None
        parsed = json.loads(result.result_json)
        assert parsed["metrics"]["coding_relevance"]["score"] == 4

    def test_multiple_entries(self, cache):
        for i in range(5):
            entry = _make_entry(entry_id=f"e{i}")
            cache.put(f"k{i}", entry)

        for i in range(5):
            result = cache.get(f"k{i}")
            assert result is not None
            assert result.entry_id == f"e{i}"


# ===================================================================
# TTL / expiration
# ===================================================================


class TestExpiration:
    """Tests for TTL-based expiration."""

    def test_expired_entry_returns_none(self, cache):
        """An entry with expires_at in the past should be treated as a miss."""
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        entry = _make_entry(expires_at=past)
        cache.put("k1", entry)

        result = cache.get("k1")
        assert result is None

    def test_non_expired_entry_returns_entry(self, cache):
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        entry = _make_entry(expires_at=future)
        cache.put("k1", entry)

        result = cache.get("k1")
        assert result is not None

    def test_cleanup_expired(self, cache):
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

        cache.put("expired1", _make_entry(expires_at=past))
        cache.put("expired2", _make_entry(expires_at=past))
        cache.put("valid", _make_entry(expires_at=future))

        deleted = cache.cleanup_expired()
        assert deleted == 2

        # Valid entry survives cleanup.
        assert cache.get("valid") is not None

    def test_cleanup_no_expired(self, cache):
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        cache.put("k1", _make_entry(expires_at=future))
        deleted = cache.cleanup_expired()
        assert deleted == 0

    def test_make_expires_at_default_ttl(self):
        c = EvalCache(db_path=":memory:", ttl_days=30)
        before = datetime.now(timezone.utc)
        expires = c.make_expires_at()
        after = datetime.now(timezone.utc)

        dt = datetime.fromisoformat(expires)
        assert dt >= before + timedelta(days=30)
        assert dt <= after + timedelta(days=30)
        c.close()

    def test_z_suffix_timestamp_parsed_correctly(self, cache):
        """Timestamps ending with 'Z' (common UTC form) must not break get()."""
        future_z = "2099-12-31T23:59:59Z"
        entry = _make_entry(expires_at=future_z)
        cache.put("z_key", entry)

        result = cache.get("z_key")
        assert result is not None
        assert result.expires_at == future_z

    def test_z_suffix_expired_entry_returns_none(self, cache):
        """An expired entry with 'Z' suffix should be treated as a miss."""
        past_z = "2020-01-01T00:00:00Z"
        entry = _make_entry(expires_at=past_z)
        cache.put("z_expired", entry)

        result = cache.get("z_expired")
        assert result is None

    def test_make_expires_at_custom_ttl(self):
        c = EvalCache(db_path=":memory:")
        before = datetime.now(timezone.utc)
        expires = c.make_expires_at(ttl_days=7)
        after = datetime.now(timezone.utc)

        dt = datetime.fromisoformat(expires)
        assert dt >= before + timedelta(days=7)
        assert dt <= after + timedelta(days=7)
        c.close()


# ===================================================================
# Session stats
# ===================================================================


class TestStats:
    """Tests for stats() session and aggregate statistics."""

    def test_empty_cache(self, cache):
        s = cache.stats()
        assert s["entries"] == 0
        assert s["total_cost_usd"] == 0.0
        assert s["total_prompt_tokens"] == 0
        assert s["total_completion_tokens"] == 0
        assert s["session_hits"] == 0
        assert s["session_misses"] == 0
        assert s["hit_rate"] == 0.0

    def test_session_hits_and_misses(self, cache):
        entry = _make_entry()
        cache.put("k1", entry)

        cache.get("k1")  # hit
        cache.get("k1")  # hit
        cache.get("miss")  # miss

        s = cache.stats()
        assert s["session_hits"] == 2
        assert s["session_misses"] == 1
        assert s["hit_rate"] == pytest.approx(2 / 3)

    def test_expired_counts_as_miss(self, cache):
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        cache.put("k1", _make_entry(expires_at=past))

        cache.get("k1")  # expired → miss

        s = cache.stats()
        assert s["session_hits"] == 0
        assert s["session_misses"] == 1

    def test_cost_aggregation(self, cache):
        cache.put("k1", _make_entry(cost_usd=0.01, prompt_tokens=100, completion_tokens=50))
        cache.put("k2", _make_entry(cost_usd=0.02, prompt_tokens=200, completion_tokens=100))

        s = cache.stats()
        assert s["entries"] == 2
        assert s["total_cost_usd"] == pytest.approx(0.03)
        assert s["total_prompt_tokens"] == 300
        assert s["total_completion_tokens"] == 150

    def test_hit_rate_all_hits(self, cache):
        cache.put("k1", _make_entry())
        cache.get("k1")

        s = cache.stats()
        assert s["hit_rate"] == pytest.approx(1.0)

    def test_hit_rate_all_misses(self, cache):
        cache.get("nope")

        s = cache.stats()
        assert s["hit_rate"] == pytest.approx(0.0)


# ===================================================================
# Content-hash cache invalidation
# ===================================================================


class TestContentHashInvalidation:
    """Tests that content changes automatically produce cache misses."""

    def test_different_content_different_key(self):
        h1 = EvalCache.content_hash("README v1 content")
        h2 = EvalCache.content_hash("README v2 content")
        k1 = EvalCache.make_key("metric", h1, "1.0")
        k2 = EvalCache.make_key("metric", h2, "1.0")
        assert k1 != k2

    def test_same_content_same_key(self):
        h1 = EvalCache.content_hash("same text")
        h2 = EvalCache.content_hash("same text")
        k1 = EvalCache.make_key("metric", h1, "1.0")
        k2 = EvalCache.make_key("metric", h2, "1.0")
        assert k1 == k2

    def test_content_change_causes_miss(self, cache):
        """Simulate a real workflow: content change → automatic cache miss."""
        h_old = EvalCache.content_hash("Old README")
        key_old = EvalCache.make_key("coding_relevance", h_old, "1.abcd1234")
        cache.put(key_old, _make_entry(content_hash=h_old))

        # Content changes → new hash → different key → miss
        h_new = EvalCache.content_hash("New README")
        key_new = EvalCache.make_key("coding_relevance", h_new, "1.abcd1234")
        assert cache.get(key_new) is None

    def test_rubric_change_causes_miss(self, cache):
        h = EvalCache.content_hash("README")
        key_v1 = EvalCache.make_key("metric", h, "1.aaaa1111")
        cache.put(key_v1, _make_entry(content_hash=h))

        key_v2 = EvalCache.make_key("metric", h, "2.bbbb2222")
        assert cache.get(key_v2) is None


# ===================================================================
# Thread safety
# ===================================================================


class TestThreadSafety:
    """Basic tests for connection-per-thread behaviour."""

    def test_concurrent_writes(self, tmp_path):
        """Multiple threads can write concurrently without errors."""
        db = tmp_path / "mt_cache.db"
        cache = EvalCache(db_path=db)

        errors: list[Exception] = []

        def writer(thread_id: int) -> None:
            try:
                for i in range(20):
                    key = f"t{thread_id}_k{i}"
                    entry = _make_entry(entry_id=f"t{thread_id}_e{i}")
                    cache.put(key, entry)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(t,)) for t in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread errors: {errors}"

        s = cache.stats()
        assert s["entries"] == 80  # 4 threads * 20 entries
        cache.close()

    def test_concurrent_reads_and_writes(self, tmp_path):
        """Reads and writes from multiple threads should not deadlock or error."""
        db = tmp_path / "rw_cache.db"
        cache = EvalCache(db_path=db)

        # Pre-populate some entries.
        for i in range(10):
            cache.put(f"k{i}", _make_entry(entry_id=f"e{i}"))

        errors: list[Exception] = []

        def reader() -> None:
            try:
                for i in range(10):
                    cache.get(f"k{i}")
            except Exception as exc:
                errors.append(exc)

        def writer() -> None:
            try:
                for i in range(10, 20):
                    cache.put(f"k{i}", _make_entry(entry_id=f"e{i}"))
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=reader),
            threading.Thread(target=reader),
            threading.Thread(target=writer),
            threading.Thread(target=writer),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        cache.close()


# ===================================================================
# close()
# ===================================================================


class TestClose:
    """Tests for close() connection cleanup."""

    def test_close_clears_connection(self, cache):
        # Ensure connection exists
        cache._conn()
        cache.close()
        assert getattr(cache._local, "conn", None) is None

    def test_close_idempotent(self, cache):
        cache.close()
        cache.close()  # should not raise
