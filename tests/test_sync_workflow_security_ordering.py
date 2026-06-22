"""Structural assertions on .github/workflows/sync.yml step ordering (B1 + B2).

``fix-security-scan-rescan-timeout`` item B1 moves README generation + commit +
push + bundle trigger to run BEFORE the security scan, so a security timeout
that cancels the aggregate job no longer blocks the catalog commit. Item B2 adds
a SECOND commit AFTER the security scan so this round's freshly computed security
blocks actually get committed (B1 alone left them written to catalog but never
committed). These tests parse the workflow YAML and assert the resulting step
order + commit gating survive future edits.
"""

from __future__ import annotations

import os

import pytest

yaml = pytest.importorskip("yaml")

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SYNC_YML = os.path.join(REPO_ROOT, ".github", "workflows", "sync.yml")


def _load_workflow() -> dict:
    with open(SYNC_YML, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _aggregate_steps() -> list[dict]:
    return _load_workflow()["jobs"]["aggregate"]["steps"]


def _aggregate_step_names() -> list[str]:
    return [s.get("name") for s in _aggregate_steps() if s.get("name")]


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


class TestSecondCommitAfterSecurity:
    """B2: a second commit AFTER the security scan captures the new blocks."""

    def _security_commit_step(self) -> dict:
        for s in _aggregate_steps():
            if s.get("id") == "commit_security":
                return s
        raise AssertionError("no aggregate step with id=commit_security (B2 commit #2)")

    def test_second_commit_runs_after_security_scan(self):
        names = _aggregate_step_names()
        security_i = _index_of(names, "Run security scan")
        commit2_i = _index_of(names, "Commit and push security results")
        assert commit2_i > security_i, (
            "commit #2 must run AFTER the security scan so it captures the "
            "security blocks the scan wrote into catalog/index.json"
        )

    def test_first_commit_runs_before_second_commit(self):
        names = _aggregate_step_names()
        commit1_i = _index_of(names, "Commit and push if changed")
        commit2_i = _index_of(names, "Commit and push security results")
        assert commit1_i < commit2_i

    def test_second_commit_only_when_security_succeeded(self):
        # Gated on success(): if the security scan runs out the clock and the
        # job is cancelled, GitHub never runs subsequent steps, so #2 is skipped
        # and #1's pre-security commit is the durable fallback (no data loss).
        step = self._security_commit_step()
        cond = step.get("if", "")
        assert "success()" in cond, (
            "commit #2 must be gated on success() so a cancelled / failed run "
            "does not attempt the post-security commit"
        )
        # Respect the security_scan_enabled toggle — no point committing when
        # the scan was disabled.
        assert "security_scan_enabled" in cond

    def test_second_commit_emits_catalog_changed_output(self):
        # #2 must still detect whether the security write actually changed
        # catalog/index.json, so an all-skipped / all-cache-hit round produces
        # no empty commit and the bundle is not needlessly re-triggered.
        step = self._security_commit_step()
        run = step.get("run", "")
        assert "catalog_changed=true" in run
        assert "catalog_changed=false" in run
        # Same conflict-safe rebase strategy as #1.
        assert "--strategy-option=theirs" in run

    def test_save_security_cache_still_present_after_security_scan(self):
        # B2 must not displace the cache-save step; it still runs after the scan.
        names = _aggregate_step_names()
        security_i = _index_of(names, "Run security scan")
        save_i = _index_of(names, "Save security eval cache")
        assert save_i > security_i


class TestAggregateOutputsCombineBothCommits:
    """The job-level catalog_changed output must OR both commits (B2)."""

    def test_catalog_changed_output_references_both_commits(self):
        out = _load_workflow()["jobs"]["aggregate"]["outputs"]
        changed = out["catalog_changed"]
        # commit #2 (commit_security) takes precedence so the bundle re-sends
        # with the freshest security-enriched catalog; commit #1 (commit) is the
        # fallback when security is cancelled.
        assert "commit_security.outputs.catalog_changed" in changed
        assert "steps.commit.outputs.catalog_changed" in changed


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

    def test_bundle_uses_latest_main_so_second_commit_is_not_missed(self):
        # The bundle dispatches release-catalog-bundle.yaml against `main`, which
        # always re-downloads the freshest catalog — so commit #2's security
        # update is shipped even though the bundle fires once per aggregate.
        steps = _load_workflow()["jobs"]["trigger-catalog-bundle-release"]["steps"]
        trigger = next(
            s for s in steps if s.get("name", "").startswith("Trigger catalog bundle")
        )
        assert "--ref main" in trigger.get("run", "")
