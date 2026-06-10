#!/usr/bin/env python3
"""Validate plugin-bundled skill/MCP materialization.

Reports declared plugin bundle slots, first-class child entries carrying
``bundled_in``, and whether each child entry has the primary file expected by
downstream catalog ingest.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_entries(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON array")
    return data


def _primary_file(download_dir: Path, entry: dict) -> Path | None:
    entry_id = entry.get("id")
    if not isinstance(entry_id, str) or not entry_id:
        return None
    if entry.get("type") == "skill":
        return download_dir / "skills" / entry_id / "SKILL.md"
    if entry.get("type") == "mcp":
        return download_dir / "mcp" / entry_id / ".mcp.json"
    return None


def validate(index_path: Path, download_dir: Path) -> int:
    entries = _load_entries(index_path)
    plugins = [e for e in entries if e.get("type") == "plugin"]

    plugin_declares_skills = 0
    declared_skill_slots = 0
    plugin_declares_mcp = 0
    declared_mcp_slots = 0
    for plugin in plugins:
        bundle = plugin.get("bundle") or {}
        skills = bundle.get("skills_namespaces")
        mcps = bundle.get("mcp_server_names")
        if isinstance(skills, list) and skills:
            plugin_declares_skills += 1
            declared_skill_slots += len(skills)
        if isinstance(mcps, list) and mcps:
            plugin_declares_mcp += 1
            declared_mcp_slots += len(mcps)

    child_skills = [
        e for e in entries
        if e.get("type") == "skill" and isinstance(e.get("bundled_in"), str) and e.get("bundled_in")
    ]
    child_mcps = [
        e for e in entries
        if e.get("type") == "mcp" and isinstance(e.get("bundled_in"), str) and e.get("bundled_in")
    ]

    missing: list[tuple[str, str, str]] = []
    present_skill_files = 0
    present_mcp_files = 0
    for entry in child_skills + child_mcps:
        target = _primary_file(download_dir, entry)
        if target is not None and target.is_file() and target.stat().st_size > 0:
            if entry.get("type") == "skill":
                present_skill_files += 1
            else:
                present_mcp_files += 1
            continue
        missing.append((entry.get("type", ""), entry.get("id", ""), str(target or "")))

    print(f"plugins_total={len(plugins)}")
    print(f"plugin_declares_skills={plugin_declares_skills}")
    print(f"declared_skill_slots={declared_skill_slots}")
    print(f"plugin_declares_mcp={plugin_declares_mcp}")
    print(f"declared_mcp_slots={declared_mcp_slots}")
    print(f"bundled_skill_entries={len(child_skills)}")
    print(f"bundled_mcp_entries={len(child_mcps)}")
    print(f"bundled_skill_files_present={present_skill_files}")
    print(f"bundled_mcp_files_present={present_mcp_files}")
    print(f"bundled_child_files_missing={len(missing)}")
    for item_type, entry_id, path in missing[:20]:
        print(f"missing {item_type} {entry_id}: {path}")
    if len(missing) > 20:
        print(f"missing_more={len(missing) - 20}")
    return 1 if missing else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--index",
        type=Path,
        default=REPO_ROOT / "catalog" / "index.json",
        help="Path to catalog/index.json",
    )
    parser.add_argument(
        "--download-dir",
        type=Path,
        default=REPO_ROOT / "catalog-download",
        help="Path to catalog-download/",
    )
    args = parser.parse_args()
    return validate(args.index, args.download_dir)


if __name__ == "__main__":
    raise SystemExit(main())
