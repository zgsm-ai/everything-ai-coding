"""A single transient network error must not crash a whole download batch.

Regression coverage for the ``Release Catalog Bundle`` CI failure where one
``http.client.RemoteDisconnected`` out of ~12k skill downloads propagated
through ``future.result()`` and killed the entire job (exit 1).

R1: ``utils.fetch_raw_content`` treats ``RemoteDisconnected`` as a retryable
    transient failure — retries, then degrades to ``None`` instead of raising.
R2: ``download_catalog._download_batch`` downgrades any per-entry exception to
    a recorded error instead of letting ``future.result()`` re-raise.
"""

from __future__ import annotations

import http.client
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import utils  # noqa: E402
import download_catalog as dc  # noqa: E402


class _FakeResp:
    """Minimal urlopen context-manager stand-in returning fixed bytes."""

    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


# --- R1: fetch_raw_content ------------------------------------------------


def test_fetch_raw_content_swallows_remote_disconnected(monkeypatch):
    """Persistent RemoteDisconnected → None after exhausting retries, no raise."""
    calls = {"n": 0}

    def _boom(*_args, **_kwargs):
        calls["n"] += 1
        raise http.client.RemoteDisconnected(
            "Remote end closed connection without response"
        )

    monkeypatch.setattr(utils, "urlopen", _boom)
    monkeypatch.setattr(utils.time, "sleep", lambda *_: None)

    result = utils.fetch_raw_content("owner/repo", "SKILL.md", "main")

    assert result is None          # degraded, did not raise
    assert calls["n"] == 3         # retried across all 3 attempts


def test_fetch_raw_content_recovers_after_transient_disconnect(monkeypatch):
    """Disconnect on attempt 1, success on attempt 2 → content returned."""
    calls = {"n": 0}

    def _flaky(*_args, **_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise http.client.RemoteDisconnected("transient")
        return _FakeResp(b"ok-content")

    monkeypatch.setattr(utils, "urlopen", _flaky)
    monkeypatch.setattr(utils.time, "sleep", lambda *_: None)

    result = utils.fetch_raw_content("owner/repo", "SKILL.md", "main")

    assert result == "ok-content"
    assert calls["n"] == 2


# --- R2: _download_batch backstop -----------------------------------------


def test_download_batch_survives_downloader_exception(monkeypatch):
    """One entry whose downloader raises must not sink the whole batch."""
    monkeypatch.setattr(dc.time, "sleep", lambda *_: None)

    good_entry = {"type": "good", "id": "good-1", "name": "good-1"}
    bad_entry = {"type": "bad", "id": "bad-1", "name": "bad-1"}

    def _good(entry, _output_dir, _force=False):
        return dc._kebab_name(entry), True, None

    def _bad(_entry, _output_dir, _force=False):
        raise http.client.RemoteDisconnected("boom")

    monkeypatch.setitem(dc.DOWNLOADERS, "good", _good)
    monkeypatch.setitem(dc.DOWNLOADERS, "bad", _bad)

    successes, errors = dc._download_batch(
        [good_entry, bad_entry], output_dir="/tmp/does-not-exist", max_workers=2
    )

    assert successes == [dc._kebab_name(good_entry)]
    assert len(errors) == 1
    assert dc._kebab_name(bad_entry) in errors[0]
