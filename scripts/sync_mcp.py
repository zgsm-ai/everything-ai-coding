#!/usr/bin/env python3
"""Sync MCP servers from awesome-mcp-servers + Awesome-MCP-ZH."""

import os
import re
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from utils import (
    fetch_raw_content, get_stars, categorize, extract_tags,
    deduplicate, to_kebab_case, save_index, logger,
)

CATALOG_DIR = os.path.join(os.path.dirname(__file__), "..", "catalog", "mcp")
MIN_STARS = 10
TODAY = date.today().isoformat()


def parse_awesome_mcp_servers() -> list:
    """Parse punkpeye/awesome-mcp-servers README.md."""
    content = fetch_raw_content("punkpeye/awesome-mcp-servers", "README.md")
    if not content:
        logger.error("Failed to fetch awesome-mcp-servers README")
        return []

    entries = []
    current_category = ""

    for line in content.split("\n"):
        # Detect category headers (## or ### headings)
        cat_match = re.match(r"^#{2,3}\s+(.+)", line)
        if cat_match:
            current_category = cat_match.group(1).strip()
            continue

        # Parse list entries: - [Name](url) - Description
        entry_match = re.match(
            r"^-\s+\[([^\]]+)\]\(([^)]+)\)\s*[-–—]\s*(.+)", line
        )
        if not entry_match:
            continue

        name = entry_match.group(1).strip()
        url = entry_match.group(2).strip()
        description = entry_match.group(3).strip()

        if "github.com" not in url:
            continue

        stars = get_stars(url)
        if stars == 0:
            # Could be rate limited or genuinely 0 stars; include with default
            stars = -1  # -1 means "unknown", will be updated on next sync with token
        if stars > 0 and stars < MIN_STARS:
            continue

        tags = extract_tags(name, description)
        category = categorize(name, description, tags, current_category)

        entries.append({
            "id": to_kebab_case(name),
            "name": name,
            "type": "mcp",
            "description": description,
            "source_url": url,
            "stars": stars,
            "category": category,
            "tags": tags,
            "tech_stack": [],
            "install": {
                "method": "mcp_config",
                "config": {"command": "npx", "args": [f"@{to_kebab_case(name)}/mcp"]}
            },
            "source": "awesome-mcp-servers",
            "last_synced": TODAY,
        })

    logger.info(f"Parsed {len(entries)} MCP entries from awesome-mcp-servers")
    return entries


def parse_awesome_mcp_zh() -> list:
    """Parse yzfly/Awesome-MCP-ZH README.md (Markdown tables)."""
    content = fetch_raw_content("yzfly/Awesome-MCP-ZH", "README.md")
    if not content:
        logger.error("Failed to fetch Awesome-MCP-ZH README")
        return []

    entries = []
    # Match table rows: | [Name](url) | description | notes |
    row_pattern = re.compile(
        r"\|\s*\[([^\]]+)\]\(([^)]+)\)\s*\|\s*([^|]+)\|\s*([^|]*)\|"
    )

    for match in row_pattern.finditer(content):
        name = match.group(1).strip()
        url = match.group(2).strip()
        description = match.group(3).strip()

        if "github.com" not in url:
            continue

        stars = get_stars(url)
        if stars == 0:
            # Could be rate limited or genuinely 0 stars; include with default
            stars = -1  # -1 means "unknown", will be updated on next sync with token
        if stars > 0 and stars < MIN_STARS:
            continue

        tags = extract_tags(name, description)
        category = categorize(name, description, tags)

        entries.append({
            "id": to_kebab_case(name),
            "name": name,
            "type": "mcp",
            "description": description,
            "source_url": url,
            "stars": stars,
            "category": category,
            "tags": tags,
            "tech_stack": [],
            "install": {
                "method": "mcp_config",
                "config": {"command": "npx", "args": [f"@{to_kebab_case(name)}/mcp"]}
            },
            "source": "awesome-mcp-zh",
            "last_synced": TODAY,
        })

    logger.info(f"Parsed {len(entries)} MCP entries from Awesome-MCP-ZH")
    return entries


def sync():
    all_entries = []
    all_entries.extend(parse_awesome_mcp_servers())
    all_entries.extend(parse_awesome_mcp_zh())

    deduped = deduplicate(all_entries)
    logger.info(f"After dedup: {len(deduped)} MCP entries")

    output_path = os.path.join(CATALOG_DIR, "index.json")
    save_index(deduped, output_path)


if __name__ == "__main__":
    sync()
