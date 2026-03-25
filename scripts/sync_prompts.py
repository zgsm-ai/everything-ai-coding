#!/usr/bin/env python3
"""Sync prompts from prompts.chat + wonderful-prompts."""

import os
import re
import csv
import sys
import io
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from utils import (
    fetch_raw_content, categorize, extract_tags, is_coding_related,
    to_kebab_case, save_index, logger,
)

CATALOG_DIR = os.path.join(os.path.dirname(__file__), "..", "catalog", "prompts")
TODAY = date.today().isoformat()


def parse_prompts_chat() -> list:
    """Parse f/prompts.chat prompts.csv - coding-related entries."""
    content = fetch_raw_content("f/prompts.chat", "prompts.csv")
    if not content:
        logger.error("Failed to fetch prompts.chat prompts.csv")
        return []

    entries = []
    csv.field_size_limit(500000)  # Some prompts are very large

    reader = csv.DictReader(io.StringIO(content))
    for row in reader:
        act = row.get("act", "").strip()
        prompt_text = row.get("prompt", "").strip()
        for_devs = row.get("for_devs", "").strip().upper() == "TRUE"

        if not act:
            continue

        # Include if for_devs=true OR matches coding keywords
        if not for_devs and not is_coding_related(act, prompt_text[:500]):
            continue

        tags = extract_tags(act, prompt_text[:300])
        category = categorize(act, prompt_text[:300], tags)

        entry_id = to_kebab_case(act)
        if not entry_id:
            continue

        entries.append({
            "id": f"{entry_id}-prompt",
            "name": act,
            "type": "prompt",
            "description": prompt_text[:200].replace("\n", " ").strip(),
            "source_url": "https://github.com/f/prompts.chat",
            "stars": 143000,
            "category": category,
            "tags": tags + (["for-devs"] if for_devs else []),
            "tech_stack": [],
            "install": {
                "method": "download_file",
                "files": [f"https://raw.githubusercontent.com/f/prompts.chat/main/prompts.csv"]
            },
            "source": "prompts-chat",
            "last_synced": TODAY,
        })

    logger.info(f"Parsed {len(entries)} coding prompts from prompts.chat")
    return entries


def parse_wonderful_prompts() -> list:
    """Parse langgptai/wonderful-prompts - programming section only."""
    content = fetch_raw_content("langgptai/wonderful-prompts", "README.md")
    if not content:
        logger.error("Failed to fetch wonderful-prompts README")
        return []

    entries = []
    in_programming_section = False
    current_name = ""
    current_content = []

    for line in content.split("\n"):
        # Detect programming section
        if re.match(r"^##\s+.*编程", line):
            in_programming_section = True
            continue
        elif re.match(r"^##\s+", line) and in_programming_section:
            # Save last entry before leaving section
            if current_name and current_content:
                _add_wonderful_entry(entries, current_name, current_content)
            in_programming_section = False
            current_name = ""
            current_content = []
            continue

        if not in_programming_section:
            continue

        # Detect individual prompt headings
        heading_match = re.match(r"^###\s+(.+)", line)
        if heading_match:
            # Save previous entry
            if current_name and current_content:
                _add_wonderful_entry(entries, current_name, current_content)
            current_name = heading_match.group(1).strip()
            current_content = []
        elif current_name:
            current_content.append(line)

    # Save last entry
    if current_name and current_content:
        _add_wonderful_entry(entries, current_name, current_content)

    logger.info(f"Parsed {len(entries)} programming prompts from wonderful-prompts")
    return entries


def _add_wonderful_entry(entries: list, name: str, content_lines: list):
    content = "\n".join(content_lines).strip()
    description = content[:200].replace("\n", " ").strip() if content else name

    tags = extract_tags(name, description)
    category = categorize(name, description, tags)

    entries.append({
        "id": f"{to_kebab_case(name)}-wprompt",
        "name": name,
        "type": "prompt",
        "description": description,
        "source_url": "https://github.com/langgptai/wonderful-prompts",
        "stars": 2000,
        "category": category,
        "tags": tags + ["chinese"],
        "tech_stack": [],
        "install": {
            "method": "download_file",
            "files": ["https://raw.githubusercontent.com/langgptai/wonderful-prompts/main/README.md"]
        },
        "source": "wonderful-prompts",
        "last_synced": TODAY,
    })


def sync():
    all_entries = []
    all_entries.extend(parse_prompts_chat())
    all_entries.extend(parse_wonderful_prompts())

    output_path = os.path.join(CATALOG_DIR, "index.json")
    save_index(all_entries, output_path)


if __name__ == "__main__":
    sync()
