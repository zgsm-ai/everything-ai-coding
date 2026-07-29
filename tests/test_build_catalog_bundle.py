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


# --- frontmatter defect detection -------------------------------------------
#
# Regression fixture is the real entry that broke a production ingest:
# github-trending-claude-bughunter-hunt-file-upload. Its description documents
# a null-byte upload bypass, and because the scalar is DOUBLE-quoted, YAML
# decodes the two source characters \0 into a real U+0000. The file's raw bytes
# are clean, so byte-level scans (and costrict-web's pre-parse
# sanitizeSyncContent) see nothing — the insert then dies on Postgres
# SQLSTATE 22P05 "unsupported Unicode escape sequence".

NUL_ESCAPES = ["\\0", "\\x00", "\\u0000"]


def _write_skill(tmp_path, frontmatter: str):
    p = tmp_path / "SKILL.md"
    p.write_text(f"---\n{frontmatter}\n---\n\n# body\n", encoding="utf-8")
    return p


def test_frontmatter_defect_none_for_clean_file(tmp_path):
    path = _write_skill(tmp_path, 'name: fine\ndescription: "all good here"')
    assert build_catalog_bundle._md_frontmatter_defect(path) is None


def test_frontmatter_defect_broken_for_unparseable_yaml(tmp_path):
    path = _write_skill(tmp_path, "description: text: with: colons")
    assert build_catalog_bundle._md_frontmatter_defect(path) == "broken"


def test_frontmatter_defect_nul_for_every_escape_spelling(tmp_path):
    """All three YAML double-quoted spellings decode to U+0000 and must be caught."""
    for esc in NUL_ESCAPES:
        path = _write_skill(
            tmp_path, f'name: hunt-file-upload\ndescription: "null byte (shell.php{esc}.jpg)"'
        )
        raw = path.read_bytes()
        assert b"\x00" not in raw, f"fixture for {esc} must be clean at byte level"
        assert build_catalog_bundle._md_frontmatter_defect(path) == "nul", esc


def test_frontmatter_defect_nul_found_in_nested_values(tmp_path):
    """The NUL may sit in a list item or nested mapping, not just a top-level scalar."""
    path = _write_skill(tmp_path, 'name: x\ntags:\n  - "safe"\n  - "bad\\0tag"')
    assert build_catalog_bundle._md_frontmatter_defect(path) == "nul"


def test_single_quoted_backslash_zero_is_not_a_nul(tmp_path):
    """YAML only expands escapes in DOUBLE quotes; single-quoted \\0 stays literal
    and must NOT be dropped."""
    path = _write_skill(tmp_path, "name: x\ndescription: 'literal shell.php\\0.jpg'")
    assert build_catalog_bundle._md_frontmatter_defect(path) is None
