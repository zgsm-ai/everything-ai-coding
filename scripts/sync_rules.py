#!/usr/bin/env python3
"""Sync rules from awesome-cursorrules + rules-2.1-optimized."""

import os
import re
import sys
import json
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from utils import (
    fetch_raw_content, github_api, categorize, extract_tags,
    merge_topics_into_tags,
    to_kebab_case, save_index, logger,
)

CATALOG_DIR = os.path.join(os.path.dirname(__file__), "..", "catalog", "rules")
TODAY = date.today().isoformat()


def parse_awesome_cursorrules() -> list:
    """Parse PatrickJS/awesome-cursorrules by listing the rules/ directory."""
    REPO = "PatrickJS/awesome-cursorrules"
    # Get directory listing via GitHub API
    data = github_api(f"repos/{REPO}/contents/rules")
    if not data:
        logger.error("Failed to fetch awesome-cursorrules rules/ directory")
        return []

    # Fetch repo-level pushed_at
    repo_info = github_api(f"repos/{REPO}")
    pushed_at = repo_info.get("pushed_at") if repo_info else None

    entries = []
    for item in data:
        if item.get("type") != "dir":
            continue

        name = item["name"]
        rule_url = f"https://github.com/PatrickJS/awesome-cursorrules/tree/main/rules/{name}"
        raw_url = f"https://raw.githubusercontent.com/PatrickJS/awesome-cursorrules/main/rules/{name}/.cursorrules"

        # Try to get README for description
        readme = fetch_raw_content(
            "PatrickJS/awesome-cursorrules", f"rules/{name}/README.md"
        )
        description = ""
        if readme:
            # Extract first meaningful line
            for line in readme.split("\n"):
                line = line.strip().strip("#").strip()
                if line and not line.startswith("!") and not line.startswith("["):
                    description = line[:200]
                    break

        if not description:
            description = f"Cursor rules for {name.replace('-', ' ')} development"

        tags = extract_tags(name, description)
        category = categorize(name, description, tags)

        entries.append({
            "id": f"{to_kebab_case(name)}-cursorrule",
            "name": f"{name.replace('-', ' ').title()} Rules",
            "type": "rule",
            "description": description,
            "source_url": rule_url,
            "stars": None,
            "pushed_at": pushed_at,
            "category": category,
            "tags": tags,
            "tech_stack": [],
            "install": {
                "method": "download_file",
                "files": [raw_url]
            },
            "source": "awesome-cursorrules",
            "last_synced": TODAY,
        })

    logger.info(f"Parsed {len(entries)} rules from awesome-cursorrules")
    return entries


def parse_rules_optimized() -> list:
    """Parse Mr-chen-05/rules-2.1-optimized .mdc files."""
    REPO = "Mr-chen-05/rules-2.1-optimized"
    repo_info = github_api(f"repos/{REPO}")
    pushed_at = repo_info.get("pushed_at") if repo_info else None

    entries = []

    for subdir in ["project-rules", "global-rules"]:
        data = github_api(
            f"repos/Mr-chen-05/rules-2.1-optimized/contents/{subdir}"
        )
        if not data:
            logger.error(f"Failed to fetch rules-2.1-optimized/{subdir}")
            continue

        for item in data:
            if not item["name"].endswith(".mdc"):
                continue

            filename = item["name"]
            raw_url = f"https://raw.githubusercontent.com/Mr-chen-05/rules-2.1-optimized/master/{subdir}/{filename}"

            content = fetch_raw_content(
                "Mr-chen-05/rules-2.1-optimized", f"{subdir}/{filename}",
                branch="master"
            )
            if not content:
                continue

            # Parse YAML frontmatter
            description = filename.replace(".mdc", "").replace("-", " ").title()
            fm_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
            if fm_match:
                frontmatter = fm_match.group(1)
                desc_match = re.search(r'description:\s*"?([^"\n]+)"?', frontmatter)
                if desc_match:
                    description = desc_match.group(1).strip()

            name_base = filename.replace(".mdc", "")
            tags = extract_tags(name_base, description)
            category = categorize(name_base, description, tags)

            entries.append({
                "id": f"{to_kebab_case(name_base)}-rule21",
                "name": f"{name_base.replace('-', ' ').title()} (Rules 2.1)",
                "type": "rule",
                "description": description,
                "source_url": f"https://github.com/Mr-chen-05/rules-2.1-optimized/tree/master/{subdir}",
                "stars": None,
                "pushed_at": pushed_at,
                "category": category,
                "tags": tags + [subdir.replace("-", " ")],
                "tech_stack": [],
                "install": {
                    "method": "download_file",
                    "files": [raw_url]
                },
                "source": "rules-2.1-optimized",
                "last_synced": TODAY,
            })

    logger.info(f"Parsed {len(entries)} rules from rules-2.1-optimized")
    return entries


def sync():
    all_entries = []
    all_entries.extend(parse_awesome_cursorrules())
    all_entries.extend(parse_rules_optimized())

    output_path = os.path.join(CATALOG_DIR, "index.json")
    save_index(all_entries, output_path)


if __name__ == "__main__":
    sync()
