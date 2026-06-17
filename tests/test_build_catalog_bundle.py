import pathlib
import sys

sys.path.insert(
    0,
    str(pathlib.Path(__file__).resolve().parent.parent / "scripts"),
)

import build_catalog_bundle  # noqa: E402


def test_prune_plugin_child_parent_consistency_drops_orphan_children_and_stale_refs():
    plugin = {
        "id": "kept-plugin",
        "type": "plugin",
        "bundle": {
            "bundled_skill_ids": ["kept-skill", "missing-skill"],
            "bundled_mcp_ids": ["kept-mcp", "missing-mcp"],
        },
    }
    kept_skill = {
        "id": "kept-skill",
        "type": "skill",
        "bundled_in": "kept-plugin",
    }
    kept_mcp = {
        "id": "kept-mcp",
        "type": "mcp",
        "bundled_in": "kept-plugin",
    }
    orphan_skill = {
        "id": "orphan-skill",
        "type": "skill",
        "bundled_in": "filtered-plugin",
    }
    standalone_skill = {
        "id": "standalone-skill",
        "type": "skill",
    }

    entries, missing_parent, stale_reverse = (
        build_catalog_bundle._prune_plugin_child_parent_consistency(
            [plugin, kept_skill, kept_mcp, orphan_skill, standalone_skill]
        )
    )

    assert {entry["id"] for entry in entries} == {
        "kept-plugin",
        "kept-skill",
        "kept-mcp",
        "standalone-skill",
    }
    assert missing_parent == 1
    assert stale_reverse == 2
    assert plugin["bundle"]["bundled_skill_ids"] == ["kept-skill", None]
    assert plugin["bundle"]["bundled_mcp_ids"] == ["kept-mcp", None]


def test_new_child_types_are_known_not_unknown_type():
    """command/subagent/template MUST be in TYPE_DIR_AND_FILE, else build()
    drops them as unknown_type even when their on-disk file exists."""
    for t in ("command", "subagent", "template"):
        assert t in build_catalog_bundle.TYPE_DIR_AND_FILE, (
            f"{t} missing from TYPE_DIR_AND_FILE → silently dropped from bundle"
        )


def test_entry_file_resolves_for_new_child_types():
    cases = {
        "command":  ("commands",  "COMMAND.md"),
        "subagent": ("subagents", "AGENT.md"),
        "template": ("templates", "TEMPLATE.md"),
        "rule":     ("rules",     "RULE.md"),
    }
    for type_, (type_dir, filename) in cases.items():
        entry = {"id": "the-id", "type": type_}
        resolved = build_catalog_bundle._entry_file(entry)
        assert resolved is not None, f"_entry_file returned None for {type_}"
        # path tail = catalog-download/<type-dir>/<id>/<filename>
        parts = resolved.parts[-3:]
        assert parts == (type_dir, "the-id", filename)


def test_schema_version_not_bumped():
    """Adding entry types rides inside the existing layout; the downstream
    catalog_ingest_service.go SupportedBundleSchemaVersion is a strict-equality
    gate, so SCHEMA_VERSION must stay 1 unless the tar layout changes."""
    assert build_catalog_bundle.SCHEMA_VERSION == 1
