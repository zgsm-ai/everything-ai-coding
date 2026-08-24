import pathlib
import sys

import pytest

sys.path.insert(
    0,
    str(pathlib.Path(__file__).resolve().parent.parent / "scripts"),
)

import build_registry_manifest  # noqa: E402


def _skill_entry(catalog_id, repo, *, evaluated_at="2026-08-20T10:30:00Z", path="SKILL.md"):
    """A catalog item whose repository root carries a skill identity.

    Only the fields the grouper reads are set; everything else the real
    catalog writes is irrelevant to these assertions.
    """
    entry = {
        "id": catalog_id,
        "type": "skill",
        "slug": catalog_id,
        "source_url": f"https://github.com/{repo}/tree/main/{path}",
        "final_score": 50,
    }
    if evaluated_at is not None:
        entry["evaluation"] = {"evaluated_at": evaluated_at}
    return entry


def test_representative_without_evaluated_at_drops_the_whole_repository():
    # costrict-web declares source.evaluated_at as a non-pointer time.Time and
    # fails the entire delivery when it is missing, so a repository that cannot
    # prove an evaluation time must not reach the manifest at all.
    entries, reconciliation = build_registry_manifest._group_catalog(
        [_skill_entry("no-eval", "acme/no-eval", evaluated_at=None)]
    )

    assert entries == []
    assert reconciliation["included_repositories"] == 0
    assert reconciliation["gate_evaluated_at_dropped_groups"] == 1
    assert reconciliation["gate_evaluated_at_dropped_items"] == 1
    assert reconciliation["gate_evaluated_at_dropped_ids"] == ("no-eval",)


def test_gate_drops_only_the_offending_repository():
    entries, reconciliation = build_registry_manifest._group_catalog(
        [
            _skill_entry("kept", "acme/kept"),
            _skill_entry("dropped", "acme/dropped", evaluated_at=None),
        ]
    )

    assert [entry["catalog_id"] for entry in entries] == ["kept"]
    assert reconciliation["included_repositories"] == 1
    assert reconciliation["gate_evaluated_at_dropped_groups"] == 1


def test_gate_counts_collapsed_children_of_the_dropped_repository():
    # The gate is repository-granular: children folded into the dropped
    # repository disappear with it and must still be accounted for.
    entries, reconciliation = build_registry_manifest._group_catalog(
        [
            _skill_entry("root", "acme/repo", evaluated_at=None),
            _skill_entry("child", "acme/repo", evaluated_at=None, path="skills/child/SKILL.md"),
        ]
    )

    assert entries == []
    assert reconciliation["gate_evaluated_at_dropped_groups"] == 1
    assert reconciliation["gate_evaluated_at_dropped_items"] == 2
    # Only root candidates are named; a nested child never had an identity to
    # report under.
    assert reconciliation["gate_evaluated_at_dropped_ids"] == ("root",)


def test_gate_reads_the_elected_representative_not_any_sibling():
    # A repository whose winning root manifest has an evaluation time is kept
    # even when a lower-precedence sibling in the same repository lacks one.
    plugin_root = {
        "id": "plugin-root",
        "type": "plugin",
        "slug": "plugin-root",
        # The repository root itself; the plugin identity comes from bundle
        # metadata, not from a path in the URL (a path would read as a subdir).
        "source_url": "https://github.com/acme/dual/tree/main/",
        "final_score": 60,
        "evaluation": {"evaluated_at": "2026-08-20T10:30:00Z"},
        "bundle": {"plugin_json_path": ".claude-plugin/plugin.json", "plugin_root": ""},
    }
    skill_root = _skill_entry("skill-root", "acme/dual", evaluated_at=None)

    entries, reconciliation = build_registry_manifest._group_catalog([plugin_root, skill_root])

    assert [entry["catalog_id"] for entry in entries] == ["plugin-root"]
    assert reconciliation["gate_evaluated_at_dropped_groups"] == 0
    assert reconciliation["collapsed_catalog_items"] == 1


def test_dropped_repository_stays_in_the_coverage_denominator():
    # It has a root identity; excluding it would inflate the reported rate.
    _, reconciliation = build_registry_manifest._group_catalog(
        [
            _skill_entry("kept", "acme/kept"),
            _skill_entry("dropped", "acme/dropped", evaluated_at=None),
        ]
    )

    assert reconciliation["repository_coverage"] == pytest.approx(50.0)


def test_reconciliation_identity_holds_across_every_bucket():
    catalog = [
        _skill_entry("kept", "acme/kept"),
        _skill_entry("kept-child", "acme/kept", path="skills/child/SKILL.md"),
        _skill_entry("no-eval", "acme/no-eval", evaluated_at=None),
        # No root identity: an aggregation repository, discarded as group K.
        _skill_entry("nested-only", "acme/awesome", path="docs/nested/SKILL.md"),
        # Excluded by the type gate.
        {"id": "a-rule", "type": "rule", "slug": "a-rule"},
        # mcp without installable coordinates.
        {"id": "an-mcp", "type": "mcp", "slug": "an-mcp", "install": {"method": "manual"}},
    ]

    _, reconciliation = build_registry_manifest._group_catalog(catalog)

    accounted = (
        sum(reconciliation["gate_type_dropped"].values())
        + sum(reconciliation["gate_mcp_method_dropped"].values())
        + reconciliation["included_repositories"]
        + reconciliation["collapsed_catalog_items"]
        + reconciliation["discarded_catalog_items"]
        + reconciliation["gate_evaluated_at_dropped_items"]
        + reconciliation["ungroupable_catalog_items"]
    )
    assert accounted == len(catalog)


def test_reconciliation_identity_fails_closed_when_a_bucket_leaks(monkeypatch):
    # The identity is asserted, not merely printed. Simulate a bucket that
    # forgets its items and the build must stop rather than ship a manifest
    # whose reconciliation no longer adds up.
    original = build_registry_manifest.Counter

    class _LeakyCounter(original):
        def values(self):  # under-report the type gate by one
            values = list(super().values())
            return values[:-1] if values else values

    monkeypatch.setattr(build_registry_manifest, "Counter", _LeakyCounter)

    with pytest.raises(ValueError, match="reconciliation identity broken"):
        build_registry_manifest._group_catalog(
            [
                _skill_entry("kept", "acme/kept"),
                {"id": "a-rule", "type": "rule", "slug": "a-rule"},
            ]
        )
