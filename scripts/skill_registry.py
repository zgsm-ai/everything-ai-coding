#!/usr/bin/env python3
"""Skill Registry: discover skills from community repos via skill_repos.json.

Uses GitHub API (Tree + Raw) instead of git clone for speed.
Supports incremental sync via .repo_cache.json — skips repos with no new pushes.
"""

import os
import re
import json
from datetime import date
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

import sys
sys.path.insert(0, os.path.dirname(__file__))
from utils import (
    categorize, extract_tags, to_kebab_case, logger, github_api,
    get_repo_info, list_repo_files, fetch_raw_content,
    SPAM_PATTERNS, NON_CODING_CATEGORIES, SKILL_CODING_KEYWORDS,
)

SCRIPTS_DIR = os.path.dirname(__file__)
CATALOG_DIR = os.path.join(SCRIPTS_DIR, "..", "catalog", "skills")
SKILL_REPOS_URL = "https://raw.githubusercontent.com/Chat2AnyLLM/awesome-repo-configs/main/skill_repos.json"
FALLBACK_PATH = os.path.join(SCRIPTS_DIR, "fallback_skill_repos.json")
BLACKLIST_PATH = os.path.join(SCRIPTS_DIR, "repo_blacklist.json")
REPO_CACHE_PATH = os.path.join(CATALOG_DIR, ".repo_cache.json")
AGGREGATOR_THRESHOLD = 1000
TODAY = date.today().isoformat()


def load_blacklist() -> set:
    """Load repo blacklist from repo_blacklist.json."""
    try:
        with open(BLACKLIST_PATH, "r") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"moltbot/skills"}


def load_repo_cache() -> dict:
    """Load incremental sync cache. Maps repo_slug -> {pushed_at, skills: [...]}."""
    if not os.path.exists(REPO_CACHE_PATH):
        return {}
    try:
        with open(REPO_CACHE_PATH, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def save_repo_cache(cache: dict):
    """Save incremental sync cache."""
    os.makedirs(os.path.dirname(REPO_CACHE_PATH), exist_ok=True)
    with open(REPO_CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def fetch_skill_repos() -> dict:
    """Fetch skill_repos.json from remote, fallback to local cache."""
    try:
        req = Request(SKILL_REPOS_URL, headers={"User-Agent": "coding-hub-sync"})
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
            with open(FALLBACK_PATH, "w") as f:
                json.dump(data, f, indent=2)
            logger.info(f"Fetched skill_repos.json: {len(data)} repos")
            return data
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as e:
        logger.warning(f"Failed to fetch skill_repos.json: {e}")

    if os.path.exists(FALLBACK_PATH):
        try:
            with open(FALLBACK_PATH, "r") as f:
                data = json.load(f)
            logger.info(f"Using fallback skill_repos.json: {len(data)} repos")
            return data
        except (json.JSONDecodeError, IOError):
            pass

    logger.warning("No skill_repos.json available, skipping Tier 2 sync")
    return {}


def parse_skill_content(content: str, skill_dir: str) -> dict | None:
    """Parse SKILL.md content and extract frontmatter fields."""
    name = ""
    description = ""
    category = ""
    tags = []

    fm_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if fm_match:
        frontmatter = fm_match.group(1)
        name_m = re.search(r'name:\s*"?([^"\n]+)"?', frontmatter)
        desc_m = re.search(r'description:\s*[>|]?\s*\n?\s*"?([^"\n]+)"?', frontmatter)
        cat_m = re.search(r'category:\s*"?([^"\n]+)"?', frontmatter)
        tags_m = re.search(r'tags:\s*\[([^\]]*)\]', frontmatter)

        if name_m:
            name = name_m.group(1).strip()
        if desc_m:
            description = desc_m.group(1).strip()
        if cat_m:
            category = cat_m.group(1).strip()
        if tags_m:
            tags = [t.strip().strip('"').strip("'") for t in tags_m.group(1).split(",") if t.strip()]

    if not name:
        name = os.path.basename(skill_dir) if skill_dir and skill_dir != "." else ""
    if not name or not description:
        return None

    return {
        "name": name,
        "description": description,
        "category": category,
        "tags": tags,
        "skill_dir": skill_dir,
    }


def scan_repo_via_api(repo_slug: str, branch: str) -> list[dict]:
    """Discover SKILL.md files in a repo using Tree API + raw fetch. No clone needed."""
    skill_paths = list_repo_files(repo_slug, branch, pattern="SKILL.md")
    if not skill_paths:
        return []

    # Filter to actual SKILL.md files (case-insensitive match on filename)
    skill_paths = [p for p in skill_paths if os.path.basename(p).upper() == "SKILL.MD"]

    if len(skill_paths) > AGGREGATOR_THRESHOLD:
        logger.warning(
            f"Repo {repo_slug} has {len(skill_paths)} SKILL.md files, "
            f"exceeds threshold {AGGREGATOR_THRESHOLD}, skipped as suspected aggregator"
        )
        return []

    entries = []
    for path in skill_paths:
        content = fetch_raw_content(repo_slug, path, branch)
        if not content:
            continue
        skill_dir = os.path.dirname(path)
        entry = parse_skill_content(content, skill_dir)
        if entry:
            entries.append(entry)

    return entries


def hard_filter(candidate: dict, stars: int, tier1_urls: set, tier1_ids: set) -> str | None:
    """Apply Phase 1 hard rules. Returns None if pass, or rejection reason."""
    name = candidate["name"].lower()
    desc = candidate["description"].lower()
    cat = candidate.get("category", "").lower()

    if stars <= 50:
        return "stars <= 50"
    if len(candidate["description"]) <= 20:
        return "description too short"

    text = f"{name} {desc}"
    for pattern in SPAM_PATTERNS:
        if pattern in text:
            return f"spam: {pattern}"

    if cat in NON_CODING_CATEGORIES:
        return f"non-coding category: {cat}"

    source_url = candidate.get("source_url", "")
    skill_id = candidate.get("id", "")
    if source_url in tier1_urls or skill_id in tier1_ids:
        return "duplicate with Tier 1"

    return None


def has_coding_keyword(candidate: dict) -> bool:
    """Check if candidate matches coding keywords using word boundaries."""
    text = f"{candidate['name']} {candidate['description']}".lower()
    return any(re.search(r'\b' + re.escape(kw) + r'\b', text) for kw in SKILL_CODING_KEYWORDS)


def discover_skills(tier1_entries: list) -> list[dict]:
    """
    Main entry: discover Tier 2 skills from skill_repos.json.

    Uses GitHub API instead of git clone. Supports incremental sync:
    - Checks pushed_at via repo API (1 call per repo)
    - If repo hasn't changed since last sync, uses cached skill data
    - If repo changed, uses Tree API to find SKILL.md files (1 call)
      then fetches each SKILL.md via raw content API
    """
    repos_data = fetch_skill_repos()
    if not repos_data:
        return []

    blacklist = load_blacklist()
    repo_cache = load_repo_cache()

    tier1_urls = {e.get("source_url", "") for e in tier1_entries if e.get("source_url")}
    tier1_ids = {e.get("id", "") for e in tier1_entries if e.get("id")}

    candidates = []
    new_cache = {}
    skipped = 0

    for repo_key, repo_info in repos_data.items():
        if not isinstance(repo_info, dict):
            continue
        if not repo_info.get("enabled", False):
            continue

        owner = repo_info.get("owner", "")
        name = repo_info.get("name", "")
        branch = repo_info.get("branch", "main")
        repo_slug = f"{owner}/{name}"

        if repo_slug in blacklist:
            logger.info(f"Skipping blacklisted repo: {repo_slug}")
            continue

        # --- Incremental check: has repo changed since last sync? ---
        info = get_repo_info(repo_slug)
        if not info:
            logger.warning(f"Cannot access repo: {repo_slug}, skipping")
            continue

        stars = info["stars"]
        pushed_at = info["pushed_at"]

        cached = repo_cache.get(repo_slug)
        if cached and cached.get("pushed_at") == pushed_at:
            # Repo unchanged — reuse cached skills
            skipped += 1
            new_cache[repo_slug] = cached
            skill_entries = cached.get("skills", [])
            logger.debug(f"Cache hit: {repo_slug} ({len(skill_entries)} skills)")
        else:
            # Repo changed or first time — scan via API
            logger.info(f"Scanning repo: {repo_slug} (branch: {branch})")
            skill_entries = scan_repo_via_api(repo_slug, branch)
            # Serialize skill entries for cache (list of dicts)
            new_cache[repo_slug] = {
                "pushed_at": pushed_at,
                "stars": stars,
                "skills": skill_entries,
            }

        for entry in skill_entries:
            skill_id = f"{to_kebab_case(entry['name'])}-skill"
            source_url = f"https://github.com/{repo_slug}/tree/{branch}/{entry['skill_dir']}"

            candidate = {
                "id": skill_id,
                "name": entry["name"],
                "type": "skill",
                "description": entry["description"],
                "source_url": source_url,
                "stars": stars,
                "category": categorize(
                    entry["name"], entry["description"],
                    entry["tags"], entry.get("category", "")
                ),
                "tags": entry["tags"] if entry["tags"] else extract_tags(entry["name"], entry["description"]),
                "tech_stack": [],
                "install": {
                    "method": "git_clone",
                    "repo": f"{owner}/{name}",
                    "branch": branch,
                    "path": entry["skill_dir"],
                },
                "source": repo_slug,
                "last_synced": TODAY,
            }

            rejection = hard_filter(candidate, stars, tier1_urls, tier1_ids)
            if rejection:
                continue

            candidate["_keyword_match"] = has_coding_keyword(candidate)
            candidates.append(candidate)

    # Save updated cache
    save_repo_cache(new_cache)

    logger.info(
        f"Phase 1 passed: {len(candidates)} candidates from {len(repos_data)} repos "
        f"({skipped} repos unchanged, skipped scan)"
    )

    return candidates


if __name__ == "__main__":
    results = discover_skills([])
    print(f"Discovered {len(results)} candidates")
    for r in results[:5]:
        print(f"  {r['name']} ({r['source']}) stars={r['stars']} kw={r.get('_keyword_match')}")
