"""Structural assertions on .github/workflows/sync.yml step ordering (B1).

``fix-security-scan-rescan-timeout`` item B1 moves README generation + commit +
push + bundle trigger to run BEFORE the security scan, so a security timeout
that cancels the aggregate job no longer blocks the catalog commit. These tests
parse the workflow YAML and assert the resulting step order survives future
edits.
"""

from __future__ import annotations

import os

import pytest

yaml = pytest.importorskip("yaml")

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SYNC_YML = os.path.join(REPO_ROOT, ".github", "workflows", "sync.yml")


def _aggregate_step_names() -> list[str]:
    with open(SYNC_YML, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    steps = data["jobs"]["aggregate"]["steps"]
    return [s.get("name") for s in steps if s.get("name")]


def _index_of(names: list[str], needle: str) -> int:
    for i, n in enumerate(names):
        if needle.lower() in n.lower():
            return i
    raise AssertionError(f"step matching {needle!r} not found in {names}")


class TestAggregateStepOrdering:
    def test_commit_runs_before_security_scan(self):
        names = _aggregate_step_names()
        commit_i = _index_of(names, "Commit and push")
        security_i = _index_of(names, "Run security scan")
        assert commit_i < security_i, (
            "commit must run BEFORE the security scan so a security timeout "
            "never blocks the catalog commit"
        )

    def test_readme_runs_before_commit(self):
        names = _aggregate_step_names()
        readme_i = _index_of(names, "Update bilingual README")
        commit_i = _index_of(names, "Commit and push")
        assert readme_i < commit_i

    def test_save_security_cache_runs_after_security_scan(self):
        names = _aggregate_step_names()
        security_i = _index_of(names, "Run security scan")
        save_i = _index_of(names, "Save security eval cache")
        assert save_i > security_i

    def test_no_duplicate_step_names(self):
        names = _aggregate_step_names()
        dups = {n for n in names if names.count(n) > 1}
        assert not dups, f"duplicate aggregate step names after refactor: {dups}"

    def test_security_scan_is_continue_on_error(self):
        with open(SYNC_YML, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        steps = data["jobs"]["aggregate"]["steps"]
        sec = next(
            s for s in steps if s.get("name", "").lower().startswith("run security scan")
        )
        assert sec.get("continue-on-error") is True


class TestBundleTriggerCondition:
    def test_bundle_triggers_on_success_or_cancelled_when_catalog_changed(self):
        with open(SYNC_YML, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        cond = data["jobs"]["trigger-catalog-bundle-release"]["if"]
        # The authoritative signal is catalog_changed=='true'; the aggregate
        # result may be 'cancelled' when a security timeout cancels the job
        # AFTER the commit already succeeded.
        assert "catalog_changed == 'true'" in cond
        assert "success" in cond
        assert "cancelled" in cond
