#!/usr/bin/env python3
"""Validate curated.json files against catalog/schema.json constraints."""

import argparse
import json
import os
import re
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(__file__))
from utils import normalize_source_url

VALID_TYPES = ["mcp", "skill", "rule", "prompt"]
VALID_CATEGORIES = [
    "frontend",
    "backend",
    "fullstack",
    "mobile",
    "devops",
    "database",
    "testing",
    "security",
    "ai-ml",
    "tooling",
    "documentation",
]
VALID_INSTALL_METHODS = [
    "mcp_config",
    "mcp_config_template",
    "manual",
    "git_clone",
    "download_file",
]
ID_PATTERN = re.compile(r"^[a-z0-9-]+$")

# Re-export for backward compatibility with tests
normalize_url = normalize_source_url


def validate_entries(
    entries: list[dict[str, Any]], index_entries: list[dict[str, Any]] | None = None
) -> tuple[list[str], list[str]]:
    """Validate a list of curated entries.

    Returns (errors: list[str], warnings: list[str]).
    """
    errors = []
    warnings = []
    index_entries = index_entries or []

    required_fields = [
        "id",
        "name",
        "type",
        "description",
        "source_url",
        "stars",
        "category",
        "tags",
        "tech_stack",
        "install",
        "source",
        "last_synced",
    ]

    seen_ids: dict[str, bool] = {}
    seen_urls: dict[str, str] = {}

    # Build index lookups
    index_ids = {e.get("id") for e in index_entries if e.get("id")}
    index_urls = {
        normalize_url(e.get("source_url", ""))
        for e in index_entries
        if e.get("source_url")
    }

    for i, entry in enumerate(entries):
        eid = entry.get("id", f"<entry {i}>")

        # Required fields
        for field in required_fields:
            if field not in entry:
                errors.append(f'ERROR: entry "{eid}" missing required field: {field}')

        entry_type = entry.get("type")
        if entry_type in {"mcp", "skill"} and "added_at" not in entry:
            errors.append(f'ERROR: entry "{eid}" missing required field: added_at')

        # id format
        if "id" in entry and not ID_PATTERN.match(entry["id"]):
            errors.append(f'ERROR: entry "{eid}" has invalid id format')

        # type enum
        if "type" in entry and entry["type"] not in VALID_TYPES:
            errors.append(f'ERROR: entry "{eid}" has invalid type: {entry["type"]}')

        # category enum
        if "category" in entry and entry["category"] not in VALID_CATEGORIES:
            errors.append(
                f'ERROR: entry "{eid}" has invalid category: {entry["category"]}'
            )

        # install.method enum
        if "install" in entry and isinstance(entry["install"], dict):
            method = entry["install"].get("method")
            if method and method not in VALID_INSTALL_METHODS:
                errors.append(
                    f'ERROR: entry "{eid}" has invalid install.method: {method}'
                )

        # stars type
        if "stars" in entry:
            stars = entry["stars"]
            if stars is not None and not isinstance(stars, int):
                errors.append(
                    f'ERROR: entry "{eid}" has invalid stars type (must be integer or null)'
                )

        # source must be "curated"
        if "source" in entry and entry["source"] != "curated":
            errors.append(
                f'ERROR: entry "{eid}" has invalid source: {entry["source"]} (must be "curated")'
            )

        if "evaluation" in entry and not isinstance(entry["evaluation"], dict):
            errors.append(
                f'ERROR: entry "{eid}" has invalid evaluation type (must be object)'
            )

        # id dedup within curated
        if "id" in entry and entry["id"]:
            if entry["id"] in seen_ids:
                errors.append(f'ERROR: duplicate id "{entry["id"]}" in curated.json')
            else:
                seen_ids[entry["id"]] = True

        # id dedup against index
        if "id" in entry and entry["id"] in index_ids:
            warnings.append(
                f'WARNING: id "{entry["id"]}" already exists in index.json '
                f"(will be deduplicated at merge)"
            )

        # source_url dedup within curated (warn, not error — same repo may have multiple resources)
        if "source_url" in entry and entry["source_url"]:
            norm = normalize_url(entry["source_url"])
            if norm in seen_urls:
                warnings.append(
                    f'WARNING: duplicate source_url for entries "{seen_urls[norm]}" and "{eid}" '
                    f"(same repo, different resources?)"
                )
            else:
                seen_urls[norm] = eid

        # source_url dedup against index
        if "source_url" in entry and entry["source_url"]:
            norm = normalize_url(entry["source_url"])
            if norm in index_urls:
                warnings.append(
                    f'WARNING: source_url already exists in index.json for entry "{eid}"'
                )

    return errors, warnings


def main():
    parser = argparse.ArgumentParser(description="Validate curated.json files")
    parser.add_argument(
        "paths", nargs="+", help="Paths to curated.json files to validate"
    )
    parser.add_argument(
        "--index-path", help="Path to index.json for cross-file dedup checks"
    )
    args = parser.parse_args()

    index_entries = []
    if args.index_path:
        try:
            with open(args.index_path, "r", encoding="utf-8") as f:
                index_entries = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"WARNING: Failed to load index: {e}", file=sys.stderr)

    has_errors = False
    for path in args.paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                entries = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"ERROR: Failed to load {path}: {e}", file=sys.stderr)
            has_errors = True
            continue

        # Accept both single object and array (generate_curated_entry outputs a single object)
        if isinstance(entries, dict):
            entries = [entries]
        elif not isinstance(entries, list):
            print(f"ERROR: {path} is not a JSON array or object", file=sys.stderr)
            has_errors = True
            continue

        errors, warnings = validate_entries(entries, index_entries=index_entries)

        for w in warnings:
            print(f"[{path}] {w}", file=sys.stderr)
        for e in errors:
            print(f"[{path}] {e}", file=sys.stderr)

        if errors:
            has_errors = True

    sys.exit(1 if has_errors else 0)


if __name__ == "__main__":
    main()
