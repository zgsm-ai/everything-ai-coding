#!/usr/bin/env python3
"""Sync skills from anthropics/skills + Ai-Agent-Skills."""

import os
import re
import sys
import json
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from utils import (
    fetch_raw_content, github_api, categorize, extract_tags,
    to_kebab_case, save_index, logger,
)

CATALOG_DIR = os.path.join(os.path.dirname(__file__), "..", "catalog", "skills")
TODAY = date.today().isoformat()


def parse_anthropic_skills() -> list:
    """Parse anthropics/skills repository."""
    data = github_api("repos/anthropics/skills/contents/skills")
    if not data:
        logger.error("Failed to fetch anthropics/skills directory")
        return []

    entries = []
    for item in data:
        if item.get("type") != "dir":
            continue

        skill_name = item["name"]
        skill_md = fetch_raw_content(
            "anthropics/skills", f"skills/{skill_name}/SKILL.md"
        )
        if not skill_md:
            continue

        # Parse YAML frontmatter
        name = skill_name
        description = f"Anthropic skill: {skill_name}"

        fm_match = re.match(r"^---\s*\n(.*?)\n---", skill_md, re.DOTALL)
        if fm_match:
            frontmatter = fm_match.group(1)
            name_match = re.search(r'name:\s*"?([^"\n]+)"?', frontmatter)
            desc_match = re.search(r'description:\s*"?([^"\n]+)"?', frontmatter)
            if name_match:
                name = name_match.group(1).strip()
            if desc_match:
                description = desc_match.group(1).strip()

        tags = extract_tags(name, description)
        category = categorize(name, description, tags)

        entries.append({
            "id": f"{to_kebab_case(skill_name)}-skill",
            "name": name,
            "type": "skill",
            "description": description,
            "source_url": f"https://github.com/anthropics/skills/tree/main/skills/{skill_name}",
            "stars": 500,
            "category": category,
            "tags": tags + ["anthropic", "official"],
            "tech_stack": [],
            "install": {
                "method": "git_clone",
                "repo": "https://github.com/anthropics/skills.git",
                "files": [f"skills/{skill_name}/"]
            },
            "source": "anthropics-skills",
            "last_synced": TODAY,
        })

    logger.info(f"Parsed {len(entries)} skills from anthropics/skills")
    return entries


def parse_ai_agent_skills() -> list:
    """Parse skillcreatorai/Ai-Agent-Skills (house copy only)."""
    content = fetch_raw_content("skillcreatorai/Ai-Agent-Skills", "skills.json")
    if not content:
        logger.error("Failed to fetch Ai-Agent-Skills skills.json")
        return []

    try:
        raw_data = json.loads(content)
        skills_data = raw_data.get("skills", raw_data) if isinstance(raw_data, dict) else raw_data
    except json.JSONDecodeError:
        logger.error("Failed to parse Ai-Agent-Skills skills.json")
        return []

    entries = []
    for skill in skills_data:
        if not isinstance(skill, dict):
            continue
        skill_name = skill.get("name", "")
        if not skill_name:
            continue

        # Check if house copy exists (has local SKILL.md)
        skill_md = fetch_raw_content(
            "skillcreatorai/Ai-Agent-Skills", f"skills/{skill_name}/SKILL.md"
        )
        if not skill_md:
            continue  # Skip catalog-only references

        work_area = skill.get("workArea", "")
        description = skill.get("description", "")
        if not description:
            description = f"Agent skill for {work_area}" if work_area else f"Agent skill: {skill_name}"

        # Try to get description from SKILL.md frontmatter
        fm_match = re.match(r"^---\s*\n(.*?)\n---", skill_md, re.DOTALL)
        if fm_match:
            desc_match = re.search(r'description:\s*"?([^"\n]+)"?', fm_match.group(1))
            if desc_match:
                description = desc_match.group(1).strip()

        tags = extract_tags(skill_name, description)
        category = categorize(skill_name, description, tags)

        entries.append({
            "id": f"{to_kebab_case(skill_name)}-aiskill",
            "name": skill_name,
            "type": "skill",
            "description": description,
            "source_url": f"https://github.com/skillcreatorai/Ai-Agent-Skills/tree/main/skills/{skill_name}",
            "stars": 30,
            "category": category,
            "tags": tags,
            "tech_stack": [],
            "install": {
                "method": "git_clone",
                "repo": "https://github.com/skillcreatorai/Ai-Agent-Skills.git",
                "files": [f"skills/{skill_name}/"]
            },
            "source": "ai-agent-skills",
            "last_synced": TODAY,
        })

    logger.info(f"Parsed {len(entries)} skills from Ai-Agent-Skills")
    return entries


def sync():
    all_entries = []
    all_entries.extend(parse_anthropic_skills())
    all_entries.extend(parse_ai_agent_skills())

    output_path = os.path.join(CATALOG_DIR, "index.json")
    save_index(all_entries, output_path)


if __name__ == "__main__":
    sync()
