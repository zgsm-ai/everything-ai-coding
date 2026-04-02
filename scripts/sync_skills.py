#!/usr/bin/env python3
"""Sync skills from Tier 1 (anthropics/skills + Ai-Agent-Skills + antigravity-awesome-skills + vasilyu-skills) + Tier 2 (Registry)."""

import os
import re
import sys
import json
import math
from typing import Any
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
try:
    from .utils import (
        fetch_raw_content,
        github_api,
        categorize,
        extract_tags,
        merge_topics_into_tags,
        to_kebab_case,
        save_index,
        load_index,
        deduplicate,
        logger,
        list_repo_files,
    )
    from .skill_registry import (
        discover_skills,
        hard_filter,
        has_coding_keyword,
        parse_skill_content,
    )
    from .catalog_lifecycle import overlay_added_at, backfill_missing_added_at
except ImportError:
    from utils import (
        fetch_raw_content,
        github_api,
        categorize,
        extract_tags,
        merge_topics_into_tags,
        to_kebab_case,
        save_index,
        load_index,
        deduplicate,
        logger,
        list_repo_files,
    )
    from skill_registry import (
        discover_skills,
        hard_filter,
        has_coding_keyword,
        parse_skill_content,
    )
    from catalog_lifecycle import overlay_added_at, backfill_missing_added_at

CATALOG_DIR = os.path.join(os.path.dirname(__file__), "..", "catalog", "skills")
TODAY = date.today().isoformat()

# Antigravity: upstream categories to skip (non-technical)
ANTIGRAVITY_SKIP_CATEGORIES = {
    "business",
    "marketing",
    "health",
    "legal",
    "leiloeiro",  # Portuguese auction niche
    "andruia",  # Personal brand AI series
}

# Antigravity: map upstream 58 categories → project 11 categories
ANTIGRAVITY_CATEGORY_MAP = {
    # frontend
    "frontend": "frontend",
    "front-end": "frontend",
    "web-development": "frontend",
    "design": "frontend",
    # backend
    "backend": "backend",
    "api-integration": "backend",
    "framework": "backend",
    # database
    "database": "database",
    "data-engineering": "database",
    "data-science": "database",
    "data": "database",
    "database-processing": "database",
    "data-ai": "database",
    # devops
    "devops": "devops",
    "cloud": "devops",
    "reliability": "devops",
    # security
    "security": "security",
    # ai-ml
    "ai-ml": "ai-ml",
    "ai-agents": "ai-ml",
    "ai-research": "ai-ml",
    "ai-testing": "ai-ml",
    "voice-agents": "ai-ml",
    "memory": "ai-ml",
    # tooling
    "code": "tooling",
    "code-quality": "tooling",
    "tool-quality": "tooling",
    "development": "tooling",
    "app-builder": "tooling",
    "automation": "tooling",
    "workflow": "tooling",
    "workflow-bundle": "tooling",
    "granular-workflow-bundle": "tooling",
    "collaboration": "tooling",
    "productivity": "tooling",
    "project-management": "tooling",
    "planning": "tooling",
    "meta": "tooling",
    # testing
    "testing": "testing",
    "test-automation": "testing",
    "development-and-testing": "testing",
    # documentation
    "content": "documentation",
    "document-processing": "documentation",
    "presentation-processing": "documentation",
    "spreadsheet-processing": "documentation",
    "graphics-processing": "documentation",
    "media": "documentation",
    # mobile
    "mobile": "mobile",
    # misc — map to closest valid schema category instead of "other"
    "business": "tooling",
    "marketing": "documentation",
    "game-development": "frontend",
    "blockchain": "backend",
    "health": "ai-ml",
    "legal": "documentation",
    "science": "ai-ml",
    "architecture": "tooling",
    "uncategorized": "tooling",
}

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

# Vasilyu: prefix → category mapping for vasilyu1983/ai-agents-public skill dirs
VASILYU_CATEGORY_MAP = {
    "ai": "ai-ml",
    "agents": "ai-ml",
    "qa": "testing",
    "software": "backend",
    "dev": "tooling",
    "data": "database",
    "docs": "documentation",
    "document": "documentation",
    "ops": "devops",
    "product": "tooling",
}


def parse_antigravity_skills() -> list[dict[str, Any]]:
    """Parse sickn33/antigravity-awesome-skills via skills_index.json.

    Tier 1 source — full inclusion, no LLM filtering.
    Single HTTP request fetches all 1300+ skill metadata entries.
    """
    REPO = "sickn33/antigravity-awesome-skills"

    # Fetch repo stars (single API call)
    repo_info = github_api(f"repos/{REPO}")
    stars = repo_info.get("stargazers_count", 0) if repo_info else 0

    # Fetch the structured index
    content = fetch_raw_content(REPO, "skills_index.json")
    if not content:
        logger.error(f"Failed to fetch {REPO}/skills_index.json")
        return []

    try:
        skills_data = json.loads(content)
    except json.JSONDecodeError:
        logger.error(f"Failed to parse {REPO}/skills_index.json")
        return []

    if not isinstance(skills_data, list):
        logger.error(f"{REPO}/skills_index.json is not a list")
        return []

    # Load supplementary tags (generated by supplement_tags.py via DeepSeek)
    tag_supplement = {}
    tag_file = os.path.join(CATALOG_DIR, "antigravity_tags.json")
    if os.path.exists(tag_file):
        try:
            with open(tag_file) as f:
                tag_supplement = json.load(f)
            logger.info(
                f"Loaded {len(tag_supplement)} supplementary tags from antigravity_tags.json"
            )
        except (json.JSONDecodeError, OSError):
            logger.warning(
                "Failed to load antigravity_tags.json, continuing without supplements"
            )

    entries = []
    skipped = 0
    cat_filtered = 0
    for skill in skills_data:
        if not isinstance(skill, dict):
            continue
        skill_id = skill.get("id", "")
        skill_name = skill.get("name", "")
        if not skill_id or not skill_name:
            skipped += 1
            continue

        upstream_category = skill.get("category", "")

        # Skip non-technical categories
        if upstream_category in ANTIGRAVITY_SKIP_CATEGORIES:
            cat_filtered += 1
            continue

        description = skill.get("description", "") or f"Agent skill: {skill_name}"
        skill_path = skill.get("path", f"skills/{skill_id}")
        upstream_category = skill.get("category", "")

        # Category mapping: ANTIGRAVITY_CATEGORY_MAP first, then categorize() fallback
        category = ANTIGRAVITY_CATEGORY_MAP.get(upstream_category)
        tags = extract_tags(skill_name, description)
        if not category:
            category = categorize(skill_name, description, tags)

        # Merge supplementary tags (from DeepSeek) for entries with empty tags
        entry_id = f"{to_kebab_case(skill_id)}-agskill"
        if not tags and entry_id in tag_supplement:
            tags = tag_supplement[entry_id]

        entries.append(
            {
                "id": f"{to_kebab_case(skill_id)}-agskill",
                "name": skill_name,
                "type": "skill",
                "description": description,
                "source_url": f"https://github.com/{REPO}/tree/main/{skill_path}",
                "stars": stars,
                "category": category,
                "tags": tags,
                "tech_stack": [],
                "install": {
                    "method": "git_clone",
                    "repo": f"https://github.com/{REPO}.git",
                    "files": [f"{skill_path}/"],
                },
                "source": "antigravity-skills",
                "last_synced": TODAY,
            }
        )

    logger.info(
        f"Parsed {len(entries)} skills from {REPO} "
        f"({skipped} skipped, {cat_filtered} non-tech filtered, stars={stars})"
    )
    return entries


def parse_vasilyu_skills() -> list[dict[str, Any]]:
    """Parse vasilyu1983/ai-agents-public shared skills via Tree API.

    Tier 1 source — discovers SKILL.md under frameworks/shared-skills/skills/*/,
    parses YAML frontmatter for name/description, falls back to dir name.
    """
    REPO = "vasilyu1983/ai-agents-public"
    SKILL_PREFIX = "frameworks/shared-skills/skills/"

    # Step 1: Tree API — discover all SKILL.md files
    existing_files = list_repo_files(REPO, "main", pattern="SKILL.md")
    skill_dirs = {}
    for path in existing_files:
        # e.g. "frameworks/shared-skills/skills/ai-code-review/SKILL.md" → "ai-code-review"
        if path.startswith(SKILL_PREFIX) and path.endswith("/SKILL.md"):
            remainder = path[len(SKILL_PREFIX):]
            parts = remainder.split("/")
            if len(parts) == 2:
                skill_dirs[parts[0]] = path

    if not skill_dirs:
        logger.warning(f"No SKILL.md files found in {REPO} under {SKILL_PREFIX}")
        return []

    # Fetch repo stars (single API call)
    repo_info = github_api(f"repos/{REPO}")
    stars = repo_info.get("stargazers_count", 0) if repo_info else 0

    entries = []
    fetch_failures = 0
    for skill_dir_name, skill_path in sorted(skill_dirs.items()):
        skill_md = fetch_raw_content(REPO, skill_path, quiet_404=True)

        name = skill_dir_name
        description = f"Agent skill: {skill_dir_name}"

        if skill_md:
            # Parse YAML frontmatter
            fm_match = re.match(r"^---\s*\n(.*?)\n---", skill_md, re.DOTALL)
            if fm_match:
                frontmatter = fm_match.group(1)
                name_match = re.search(r'name:\s*"?([^"\n]+)"?', frontmatter)
                desc_match = re.search(r'description:\s*"?([^"\n]+)"?', frontmatter)
                if name_match:
                    name = name_match.group(1).strip()
                if desc_match:
                    description = desc_match.group(1).strip()
        else:
            fetch_failures += 1
            continue

        # Prefix-based category: split dir name by "-", take first segment
        prefix = skill_dir_name.split("-")[0]
        tags = extract_tags(name, description)
        category = VASILYU_CATEGORY_MAP.get(prefix)
        if not category:
            category = categorize(name, description, tags)

        entries.append(
            {
                "id": f"{to_kebab_case(skill_dir_name)}-vyskill",
                "name": name,
                "type": "skill",
                "description": description,
                "source_url": f"https://github.com/{REPO}/tree/main/{SKILL_PREFIX}{skill_dir_name}",
                "stars": stars,
                "category": category,
                "tags": tags,
                "tech_stack": [],
                "install": {
                    "method": "git_clone",
                    "repo": f"https://github.com/{REPO}.git",
                    "files": [f"{SKILL_PREFIX}{skill_dir_name}/"],
                },
                "source": "vasilyu-skills",
                "last_synced": TODAY,
            }
        )

    logger.info(
        f"Parsed {len(entries)} skills from {REPO} "
        f"({fetch_failures} fetch failures, stars={stars})"
    )
    return entries


def parse_anthropic_skills() -> list[dict[str, Any]]:
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

        entries.append(
            {
                "id": f"{to_kebab_case(skill_name)}-skill",
                "name": name,
                "type": "skill",
                "description": description,
                "source_url": f"https://github.com/anthropics/skills/tree/main/skills/{skill_name}",
                "stars": None,
                "category": category,
                "tags": tags + ["anthropic", "official"],
                "tech_stack": [],
                "install": {
                    "method": "git_clone",
                    "repo": "https://github.com/anthropics/skills.git",
                    "files": [f"skills/{skill_name}/"],
                },
                "source": "anthropics-skills",
                "last_synced": TODAY,
            }
        )

    logger.info(f"Parsed {len(entries)} skills from anthropics/skills")
    return entries


def parse_ai_agent_skills() -> list[dict[str, Any]]:
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
        skills_data = (
            raw_data.get("skills", raw_data) if isinstance(raw_data, dict) else raw_data
        )
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
            description = (
                f"Agent skill for {work_area}"
                if work_area
                else f"Agent skill: {skill_name}"
            )

        # Try to get description from SKILL.md frontmatter
        fm_match = re.match(r"^---\s*\n(.*?)\n---", skill_md, re.DOTALL)
        if fm_match:
            desc_match = re.search(r'description:\s*"?([^"\n]+)"?', fm_match.group(1))
            if desc_match:
                description = desc_match.group(1).strip()

        tags = extract_tags(skill_name, description)
        category = categorize(skill_name, description, tags)

        entries.append(
            {
                "id": f"{to_kebab_case(skill_name)}-aiskill",
                "name": skill_name,
                "type": "skill",
                "description": description,
                "source_url": f"https://github.com/skillcreatorai/Ai-Agent-Skills/tree/main/skills/{skill_name}",
                "stars": None,
                "category": category,
                "tags": tags,
                "tech_stack": [],
                "install": {
                    "method": "git_clone",
                    "repo": "https://github.com/skillcreatorai/Ai-Agent-Skills.git",
                    "files": [f"skills/{skill_name}/"],
                },
                "source": "ai-agent-skills",
                "last_synced": TODAY,
            }
        )

    logger.info(
        f"Parsed {len(entries)} skills from Ai-Agent-Skills ({skipped} catalog-only skipped)"
    )
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
    if re.search(r"(.{2,})\1+", name):
        return "repeating pattern in name"
    if description.strip().lower() == name.strip().lower():
        return "description equals name"
    return None


def parse_openclaw_skills(tier1_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Parse coding-related skills from VoltAgent/awesome-openclaw-skills.

    Returns candidates ready for Tier 2 pipeline (hard_filter applied).
    """
    AWESOME_REPO = "VoltAgent/awesome-openclaw-skills"
    SKILLS_REPO = "openclaw/skills"

    stars = _get_openclaw_stars()

    # Get pushed_at for openclaw/skills repo
    from utils import get_repo_meta

    meta = get_repo_meta(f"https://github.com/{SKILLS_REPO}")
    pushed_at = meta["pushed_at"] if meta else None

    tier1_urls = {e.get("source_url", "") for e in tier1_entries if e.get("source_url")}
    tier1_ids = {e.get("id", "") for e in tier1_entries if e.get("id")}

    # Regex for awesome list entry: - [name](url) - description
    entry_re = re.compile(r"^-\s+\[([^\]]+)\]\(([^)]+)\)\s*[-–—]\s*(.+)$", re.MULTILINE)

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
            slug_match = re.search(r"/skills/([^/?#]+)$", url)
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
                "stars": 0,
                "pushed_at": pushed_at,
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
    attempted = 0
    consecutive_failures = 0
    for c in candidates:
        if c.get("source") != "openclaw-skills":
            continue
        install_path = c.get("_openclaw_install_path", "")
        if not install_path:
            continue
        if not _needs_openclaw_description_refresh(c.get("description", "")):
            continue
        attempted += 1
        skill_md = fetch_raw_content(
            SKILLS_REPO, f"{install_path}SKILL.md", quiet_404=True
        )
        if not skill_md:
            consecutive_failures += 1
            if consecutive_failures >= 8:
                logger.warning(
                    "openclaw: stopping description supplementation after repeated fetch failures"
                )
                break
            continue
        consecutive_failures = 0
        parsed = parse_skill_content(skill_md, install_path)
        if (
            parsed
            and parsed.get("description")
            and len(parsed["description"]) > len(c["description"])
        ):
            c["description"] = parsed["description"]
            updated += 1
    logger.info(
        f"openclaw: supplemented {updated}/{attempted} targeted descriptions "
        f"from SKILL.md"
    )


def _needs_openclaw_description_refresh(description: str) -> bool:
    """Only fetch SKILL.md when the list description looks truncated or thin."""
    desc = (description or "").strip()
    if not desc:
        return True
    if desc.endswith(("...", "…")):
        return True
    return len(desc) < 80


TOP_N = 300


def deterministic_tier2_filter(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter Tier 2 candidates using deterministic signals (no LLM).

    Score = log10(stars) * 10 + (50 if keyword_match else 0)
    Returns top 300 by score.
    """
    for c in candidates:
        stars = max(c.get("stars", 0) or 0, 1)
        keyword_bonus = 50 if c.get("_keyword_match", False) else 0
        c["_score"] = math.log10(stars) * 10 + keyword_bonus

    candidates.sort(key=lambda x: x.get("_score", 0), reverse=True)
    result = candidates[:TOP_N]

    for r in result:
        r.pop("_score", None)
        r.pop("_keyword_match", None)
        r.pop("_openclaw_slug", None)
        r.pop("_openclaw_install_path", None)

    return result


def sync():
    # === Tier 1: Full inclusion, no filtering ===
    tier1_entries = []
    tier1_entries.extend(parse_anthropic_skills())
    tier1_entries.extend(parse_ai_agent_skills())
    tier1_entries.extend(parse_antigravity_skills())
    tier1_entries.extend(parse_vasilyu_skills())
    logger.info(f"Tier 1 total: {len(tier1_entries)} skills")

    # === Tier 2: Registry discovery + OpenClaw + deterministic filtering ===
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
            tier2_entries = deterministic_tier2_filter(candidates)
            logger.info(
                f"Tier 2 total: {len(tier2_entries)} skills (after deterministic filtering)"
            )
    except Exception as e:
        logger.error(f"Tier 2 filtering failed: {e}")
        logger.info("Tier 2 filtering skipped, continuing with Tier 1 only")

    # === Merge: Tier 1 takes priority ===
    all_entries = tier1_entries + tier2_entries
    all_entries = deduplicate(all_entries)

    output_path = os.path.join(CATALOG_DIR, "index.json")
    existing_entries = load_index(output_path)
    if not all_entries and existing_entries:
        logger.warning(
            "Skill sync produced 0 entries; keeping existing index to avoid clobbering "
            "the last successful sync"
        )
        logger.info(f"Retained {len(existing_entries)} skills from existing index")
        return
    all_entries = overlay_added_at(all_entries, existing_entries, today=TODAY)
    save_index(all_entries, output_path)
    logger.info(
        f"Final skills count: {len(all_entries)} (Tier 1: {len(tier1_entries)}, Tier 2: {len(tier2_entries)})"
    )


def backfill_index_added_at():
    output_path = os.path.join(CATALOG_DIR, "index.json")
    entries = load_index(output_path)
    if not entries:
        return
    entries = backfill_missing_added_at(entries, today=TODAY)
    save_index(entries, output_path)


if __name__ == "__main__":
    sync()
