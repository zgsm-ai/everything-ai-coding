#!/usr/bin/env python3
"""Sync skills from Tier 1 (anthropics/skills + Ai-Agent-Skills) + Tier 2 (Registry)."""

import os
import re
import sys
import json
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from utils import (
    fetch_raw_content, github_api, categorize, extract_tags,
    to_kebab_case, save_index, deduplicate, logger, list_repo_files,
)
from skill_registry import discover_skills, hard_filter, has_coding_keyword, parse_skill_content
from llm_evaluator import evaluate_skills, translate_descriptions

CATALOG_DIR = os.path.join(os.path.dirname(__file__), "..", "catalog", "skills")
TODAY = date.today().isoformat()

# OpenClaw: 10 coding-related category files from VoltAgent/awesome-openclaw-skills
OPENCLAW_CATEGORIES = {
    "coding-agents-and-ides": "tooling",
    "web-and-frontend-development": "frontend",
    "devops-and-cloud": "devops",
    "search-and-research": "tooling",
    "browser-and-automation": "testing",
    "cli-utilities": "tooling",
    "ai-and-llms": "ai-ml",
    "git-and-github": "tooling",
    "security-and-passwords": "security",
    "data-and-analytics": "database",
}


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
    """Parse skillcreatorai/Ai-Agent-Skills (house copy only).

    Uses Tree API to discover which skills actually have SKILL.md,
    avoiding blind 404 probes for catalog-only entries.
    """
    REPO = "skillcreatorai/Ai-Agent-Skills"

    # Step 1: Tree API — know exactly which SKILL.md files exist
    existing_files = list_repo_files(REPO, "main", pattern="SKILL.md")
    existing_skills = set()
    for path in existing_files:
        # e.g. "skills/playwright/SKILL.md" → "playwright"
        parts = path.split("/")
        if len(parts) >= 3 and parts[0] == "skills" and parts[-1].upper() == "SKILL.MD":
            existing_skills.add(parts[1])

    if not existing_skills:
        logger.warning(f"No SKILL.md files found in {REPO} via Tree API")

    # Step 2: Parse skills.json for metadata (description, workArea, etc.)
    content = fetch_raw_content(REPO, "skills.json")
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
    skipped = 0
    for skill in skills_data:
        if not isinstance(skill, dict):
            continue
        skill_name = skill.get("name", "")
        if not skill_name:
            continue

        # Skip catalog-only entries (no SKILL.md on disk)
        if skill_name not in existing_skills:
            skipped += 1
            continue

        # Fetch actual SKILL.md content
        skill_md = fetch_raw_content(REPO, f"skills/{skill_name}/SKILL.md")
        if not skill_md:
            continue

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

    logger.info(f"Parsed {len(entries)} skills from Ai-Agent-Skills ({skipped} catalog-only skipped)")
    return entries


def _get_openclaw_stars() -> int:
    """Fetch openclaw/skills repo stars. Returns fallback 100 on failure."""
    info = github_api("repos/openclaw/skills")
    if info and "stargazers_count" in info:
        stars = info["stargazers_count"]
        logger.info(f"openclaw/skills stars: {stars}")
        return stars
    logger.warning("Failed to fetch openclaw/skills stars, using fallback 100")
    return 100


def openclaw_extra_filter(name: str, description: str) -> str | None:
    """Extra quality filter for openclaw entries.
    Returns None if pass, or rejection reason.
    """
    if len(name) < 3:
        return "name too short"
    if len(name) > 60:
        return "name too long"
    # Repeating character pattern: e.g. "asdasd", "abcabc", "12312"
    if re.search(r'(.{2,})\1+', name):
        return "repeating pattern in name"
    if description.strip().lower() == name.strip().lower():
        return "description equals name"
    return None


def parse_openclaw_skills(tier1_entries: list) -> list[dict]:
    """Parse coding-related skills from VoltAgent/awesome-openclaw-skills.

    Returns candidates ready for Tier 2 pipeline (hard_filter applied).
    """
    AWESOME_REPO = "VoltAgent/awesome-openclaw-skills"
    SKILLS_REPO = "openclaw/skills"

    stars = _get_openclaw_stars()

    tier1_urls = {e.get("source_url", "") for e in tier1_entries if e.get("source_url")}
    tier1_ids = {e.get("id", "") for e in tier1_entries if e.get("id")}

    # Regex for awesome list entry: - [name](url) - description
    entry_re = re.compile(r'^-\s+\[([^\]]+)\]\(([^)]+)\)\s*[-–—]\s*(.+)$', re.MULTILINE)

    candidates = []
    total_parsed = 0
    extra_filtered = 0

    for cat_file, default_category in OPENCLAW_CATEGORIES.items():
        content = fetch_raw_content(
            AWESOME_REPO, f"categories/{cat_file}.md", quiet_404=True
        )
        if not content:
            logger.warning(f"openclaw: failed to fetch category {cat_file}")
            continue

        for match in entry_re.finditer(content):
            name = match.group(1).strip()
            url = match.group(2).strip()
            description = match.group(3).strip()
            total_parsed += 1

            # Extract slug from URL: https://clawskills.sh/skills/author-skillname
            slug_match = re.search(r'/skills/([^/?#]+)$', url)
            if not slug_match:
                continue
            slug = slug_match.group(1)

            # openclaw extra filter
            rejection = openclaw_extra_filter(name, description)
            if rejection:
                extra_filtered += 1
                continue

            # Build install path from slug: author-skillname -> skills/author/skillname/
            parts = slug.split("-", 1)
            if len(parts) == 2:
                author, skill_name = parts
                install_path = f"skills/{author}/{skill_name}/"
            else:
                install_path = f"skills/{slug}/"

            skill_id = f"{to_kebab_case(name)}-ocskill"
            tags = extract_tags(name, description)
            category = categorize(name, description, tags, default_category)

            candidate = {
                "id": skill_id,
                "name": name,
                "type": "skill",
                "description": description,
                "source_url": url,
                "stars": stars,
                "category": category,
                "tags": tags,
                "tech_stack": [],
                "install": {
                    "method": "git_clone",
                    "repo": SKILLS_REPO,
                    "files": [install_path],
                },
                "source": "openclaw-skills",
                "last_synced": TODAY,
                "_openclaw_slug": slug,
                "_openclaw_install_path": install_path,
            }

            # Apply hard_filter (reuses existing Tier 2 filter)
            rejection = hard_filter(candidate, stars, tier1_urls, tier1_ids)
            if rejection:
                continue

            candidate["_keyword_match"] = has_coding_keyword(candidate)
            candidates.append(candidate)

    logger.info(
        f"openclaw: parsed {total_parsed} entries, "
        f"{extra_filtered} extra-filtered, "
        f"{len(candidates)} candidates after hard_filter"
    )
    return candidates


def _supplement_openclaw_descriptions(candidates: list[dict]):
    """Fetch SKILL.md from openclaw/skills to replace truncated descriptions.

    Modifies candidates in-place. Only fetches for candidates that passed hard_filter.
    """
    SKILLS_REPO = "openclaw/skills"
    updated = 0
    for c in candidates:
        if c.get("source") != "openclaw-skills":
            continue
        install_path = c.get("_openclaw_install_path", "")
        if not install_path:
            continue
        skill_md = fetch_raw_content(
            SKILLS_REPO, f"{install_path}SKILL.md", quiet_404=True
        )
        if not skill_md:
            continue
        parsed = parse_skill_content(skill_md, install_path)
        if parsed and parsed.get("description") and len(parsed["description"]) > len(c["description"]):
            c["description"] = parsed["description"]
            updated += 1
    logger.info(f"openclaw: supplemented {updated}/{sum(1 for c in candidates if c.get('source') == 'openclaw-skills')} descriptions from SKILL.md")


def sync():
    # === Tier 1: Full inclusion, no filtering ===
    tier1_entries = []
    tier1_entries.extend(parse_anthropic_skills())
    tier1_entries.extend(parse_ai_agent_skills())
    logger.info(f"Tier 1 total: {len(tier1_entries)} skills")

    # Translate Tier 1 descriptions to Chinese
    translate_descriptions(tier1_entries)

    # === Tier 2: Registry discovery + OpenClaw + two-phase filtering ===
    tier2_entries = []

    # Registry candidates
    candidates = []
    try:
        candidates = discover_skills(tier1_entries)
        logger.info(f"Tier 2 registry candidates: {len(candidates)}")
    except Exception as e:
        logger.error(f"Tier 2 registry discovery failed: {e}")

    # OpenClaw candidates (isolated so a failure here doesn't lose registry results)
    try:
        openclaw_candidates = parse_openclaw_skills(tier1_entries)
        _supplement_openclaw_descriptions(openclaw_candidates)
        candidates = candidates + openclaw_candidates
        logger.info(f"Tier 2 total candidates (registry + openclaw): {len(candidates)}")
    except Exception as e:
        logger.error(f"OpenClaw sync failed: {e}")
        logger.info("OpenClaw sync skipped, continuing with registry candidates only")

    try:
        if candidates:
            tier2_entries = evaluate_skills(candidates)
            logger.info(f"Tier 2 total: {len(tier2_entries)} skills (after LLM evaluation)")
    except Exception as e:
        logger.error(f"Tier 2 evaluation failed: {e}")
        logger.info("Tier 2 evaluation skipped, continuing with Tier 1 only")

    # === Merge: Tier 1 takes priority ===
    all_entries = tier1_entries + tier2_entries
    all_entries = deduplicate(all_entries)

    output_path = os.path.join(CATALOG_DIR, "index.json")
    save_index(all_entries, output_path)
    logger.info(f"Final skills count: {len(all_entries)} (Tier 1: {len(tier1_entries)}, Tier 2: {len(tier2_entries)})")


if __name__ == "__main__":
    sync()
