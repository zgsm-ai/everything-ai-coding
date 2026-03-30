"""Shared utilities for sync scripts."""

import os
import re
import json
import time
import logging
from typing import Optional
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
_github_api_disabled_until = 0.0

CATEGORY_MAP = {
    # MCP categories (awesome-mcp-servers)
    "browser automation": "testing",
    "cloud platforms": "devops",
    "databases": "database",
    "developer tools": "tooling",
    "file systems": "tooling",
    "os automation": "devops",
    "security": "security",
    "monitoring": "devops",
    "version control": "tooling",
    "code execution": "tooling",
    "coding agents": "tooling",
    "command line": "tooling",
    "data science tools": "ai-ml",
    "data visualization": "frontend",
    "communication": "tooling",
    "research": "documentation",
    "search & data extraction": "tooling",
    "knowledge & memory": "ai-ml",
    # Cursorrules tech stack keywords
    "react": "frontend",
    "nextjs": "frontend",
    "next.js": "frontend",
    "vue": "frontend",
    "angular": "frontend",
    "svelte": "frontend",
    "tailwind": "frontend",
    "css": "frontend",
    "html": "frontend",
    "typescript": "frontend",
    "javascript": "frontend",
    "node": "backend",
    "express": "backend",
    "fastapi": "backend",
    "django": "backend",
    "flask": "backend",
    "python": "backend",
    "go": "backend",
    "golang": "backend",
    "rust": "backend",
    "java": "backend",
    "spring": "backend",
    "ruby": "backend",
    "rails": "backend",
    "elixir": "backend",
    "php": "backend",
    "laravel": "backend",
    "c#": "backend",
    "dotnet": "backend",
    ".net": "backend",
    "flutter": "mobile",
    "react native": "mobile",
    "swift": "mobile",
    "swiftui": "mobile",
    "kotlin": "mobile",
    "android": "mobile",
    "ios": "mobile",
    "docker": "devops",
    "kubernetes": "devops",
    "k8s": "devops",
    "terraform": "devops",
    "aws": "devops",
    "gcp": "devops",
    "azure": "devops",
    "ci/cd": "devops",
    "ci-cd": "devops",
    "sql": "database",
    "postgres": "database",
    "mysql": "database",
    "mongodb": "database",
    "redis": "database",
    "prisma": "database",
    "supabase": "database",
    "drizzle": "database",
    "test": "testing",
    "testing": "testing",
    "jest": "testing",
    "playwright": "testing",
    "cypress": "testing",
    "vitest": "testing",
    "auth": "security",
    "security": "security",
    "crypto": "security",
    "ai": "ai-ml",
    "ml": "ai-ml",
    "llm": "ai-ml",
    "machine learning": "ai-ml",
    "openai": "ai-ml",
    "langchain": "ai-ml",
    "documentation": "documentation",
    "docs": "documentation",
    "markdown": "documentation",
    "api": "backend",
    "graphql": "backend",
    "rest": "backend",
    "fullstack": "fullstack",
    "full-stack": "fullstack",
    "t3": "fullstack",
    "monorepo": "fullstack",
    "turborepo": "fullstack",
    "git": "tooling",
    "eslint": "tooling",
    "prettier": "tooling",
    "linting": "tooling",
    "cli": "tooling",
    "vscode": "tooling",
}

# Spam patterns for skill filtering (case-insensitive)
SPAM_PATTERNS = [
    "viral", "prompt-ready", "copy-paste", "click-bait",
    "get-rich", "make-money",
]

# Non-coding categories to exclude from skill registry
NON_CODING_CATEGORIES = [
    "marketing", "brand", "branding", "raffle", "invoice",
    "resume", "cover-letter", "social-media", "content-writing",
    "seo", "creative", "media", "communication", "writing",
]

# Coding-related keywords for skill registry Phase 1 filtering
SKILL_CODING_KEYWORDS = [
    "code", "develop", "engineer", "debug", "test", "deploy",
    "build", "compile", "lint", "refactor", "api", "database",
    "git", "docker", "ci", "cd", "terminal", "cli", "shell",
    "script", "framework", "library", "sdk", "mcp", "skill", "agent",
]

# Coding-related keywords for prompt filtering
CODING_KEYWORDS = [
    "code", "coding", "developer", "development", "engineer", "engineering",
    "programmer", "programming", "terminal", "frontend", "backend", "devops",
    "debug", "debugging", "software", "api", "database", "algorithm",
    "compiler", "linux", "git", "deploy", "deployment", "architecture",
    "testing", "qa", "fullstack", "full-stack", "web developer",
    "javascript", "python", "typescript", "react", "node", "sql",
    "html", "css", "docker", "kubernetes", "aws", "cloud",
    "machine learning", "data scientist", "data engineer",
    "tech lead", "cto", "sre", "infrastructure",
]


def github_api(path: str) -> Optional[dict]:
    """Make a GitHub API request. Returns parsed JSON or None on error."""
    global _github_api_disabled_until

    if _github_api_disabled_until > time.time():
        return None

    url = f"https://api.github.com/{path.lstrip('/')}"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "coding-hub-sync",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    req = Request(url, headers=headers)
    for attempt in range(3):
        try:
            with urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except HTTPError as e:
            if e.code in (403, 429):  # Rate limit / abuse detection
                wait = _retry_delay_seconds(e.headers, min(2 ** attempt, 60))
                if GITHUB_TOKEN:
                    if attempt < 2:
                        logger.warning(f"GitHub API rate limited, waiting {wait}s...")
                        time.sleep(wait)
                        continue
                else:
                    _github_api_disabled_until = time.time() + wait
                    logger.warning(
                        "GitHub API rate limited without token; "
                        f"skipping repo metadata calls for {wait}s"
                    )
                return None
            elif e.code == 404:
                return None
            elif e.code >= 500 and attempt < 2:
                wait = _retry_delay_seconds(e.headers, min(2 ** attempt, 30))
                logger.warning(f"GitHub API temporary error {e.code}, retrying in {wait}s...")
                time.sleep(wait)
                continue
            logger.error(f"GitHub API error {e.code}: {url}")
            return None
        except (URLError, TimeoutError) as e:
            logger.error(f"Network error (attempt {attempt+1}): {e}")
            if attempt < 2:
                time.sleep(2 ** attempt)
    return None


# Process-level cache for repo metadata (avoids duplicate API calls within a single sync run)
_repo_meta_cache = {}
_repo_readme_cache = {}
_repo_languages_cache = {}


def get_repo_meta(repo_url: str) -> Optional[dict]:
    """Get comprehensive repo metadata from a GitHub URL. Returns None on error.

    Single API call returns: stars, pushed_at, default_branch, topics, license, open_issues, has_readme.
    Uses in-memory cache keyed by normalized owner/repo to avoid duplicate calls.
    """
    # Extract owner/repo from URL
    match = re.search(r"github\.com/([^/]+/[^/]+?)(?:\.git)?(?:/|$|\?|#)", repo_url)
    if not match:
        return None

    repo_slug = match.group(1).lower()  # Normalize to lowercase

    # Check cache
    if repo_slug in _repo_meta_cache:
        return _repo_meta_cache[repo_slug]

    # Fetch from API
    data = github_api(f"repos/{repo_slug}")
    if not data:
        _repo_meta_cache[repo_slug] = None
        return None

    result = {
        "stars": data.get("stargazers_count", 0),
        "pushed_at": data.get("pushed_at"),
        "default_branch": data.get("default_branch", "main"),
        "topics": data.get("topics", []),
        "has_readme": _probe_readme_exists(repo_slug, data.get("default_branch", "main"))
        if GITHUB_TOKEN else False,
        "license": data.get("license", {}).get("spdx_id") if data.get("license") else None,
        "open_issues": data.get("open_issues_count", 0),
    }

    _repo_meta_cache[repo_slug] = result
    return result


def get_repo_languages(repo_url: str) -> list[str]:
    """Get programming languages for a GitHub repo. Returns list of language names.

    Calls GET /repos/{owner}/{repo}/languages. Returns [] for non-GitHub URLs,
    API errors, or repos with no detected languages. Uses in-memory cache.
    """
    match = re.search(r"github\.com/([^/]+/[^/]+?)(?:\.git)?(?:/|$|\?|#)", repo_url)
    if not match:
        return []

    repo_slug = match.group(1).lower()

    if repo_slug in _repo_languages_cache:
        return _repo_languages_cache[repo_slug]

    data = github_api(f"repos/{repo_slug}/languages")
    if not data:
        _repo_languages_cache[repo_slug] = []
        return []

    languages = list(data.keys())
    _repo_languages_cache[repo_slug] = languages
    return languages


def get_repo_info(repo_slug: str) -> Optional[dict]:
    """Get repo metadata (stars, pushed_at, default_branch). Returns None on error.

    DEPRECATED: Use get_repo_meta() instead. Kept for backward compatibility.
    """
    # Convert slug to URL format for get_repo_meta
    meta = get_repo_meta(f"https://github.com/{repo_slug}")
    if not meta:
        return None
    return {
        "stars": meta["stars"],
        "pushed_at": meta["pushed_at"] or "",
        "default_branch": meta["default_branch"],
    }


def list_repo_files(repo_slug: str, branch: str = "main",
                    pattern: str = "") -> list[str]:
    """List files in a repo using Git Tree API (recursive). Optionally filter by pattern.
    Returns list of file paths. Much faster than cloning.
    """
    data = github_api(f"repos/{repo_slug}/git/trees/{branch}?recursive=1")
    if not data or "tree" not in data:
        return []
    paths = [item["path"] for item in data["tree"] if item.get("type") == "blob"]
    if pattern:
        paths = [p for p in paths if pattern.lower() in p.lower()]
    return paths


def get_stars(repo_url: str) -> int:
    """Get star count for a GitHub repo URL. Returns 0 on error.

    DEPRECATED: Use get_repo_meta() instead. Kept for backward compatibility.
    """
    meta = get_repo_meta(repo_url)
    if meta and meta.get("stars") is not None:
        return meta["stars"]
    return 0


def fetch_raw_content(repo: str, path: str, branch: str = "main",
                      quiet_404: bool = False) -> Optional[str]:
    """Fetch raw file content from GitHub.

    Args:
        quiet_404: If True, log 404 at DEBUG level (for expected probes).
                   If False (default), log at WARNING level.
    """
    url = f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"
    req = Request(url, headers={"User-Agent": "coding-hub-sync"})
    if GITHUB_TOKEN:
        req.add_header("Authorization", f"token {GITHUB_TOKEN}")

    for attempt in range(3):
        try:
            with urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except HTTPError as e:
            if e.code == 404:
                if quiet_404:
                    logger.debug(f"Not found (404): {url}")
                else:
                    logger.warning(f"Not found (404): {url}")
                return None
            if e.code in (429, 500, 502, 503, 504) and attempt < 2:
                wait = _retry_delay_seconds(e.headers, min(2 ** attempt, 30))
                logger.warning(f"Fetch failed {e.code} for {url}, retrying in {wait}s...")
                time.sleep(wait)
                continue
            logger.error(f"Failed to fetch {url}: {e}")
            return None
        except (URLError, TimeoutError) as e:
            logger.error(f"Failed to fetch {url}: {e}")
            if attempt < 2:
                time.sleep(2 ** attempt)
                continue
            return None

    return None


def _retry_delay_seconds(headers, default_wait: int) -> int:
    """Best-effort retry delay from HTTP headers."""
    if headers:
        retry_after = headers.get("Retry-After")
        if retry_after:
            try:
                return max(int(retry_after), 1)
            except (TypeError, ValueError):
                pass

        reset = headers.get("X-RateLimit-Reset")
        if reset:
            try:
                return max(int(reset) - int(time.time()), 1)
            except (TypeError, ValueError):
                pass

    return max(default_wait, 1)


def _probe_readme_exists(repo_slug: str, branch: str) -> bool:
    """Probe common README paths once per repo to avoid misusing unrelated repo flags."""
    cache_key = f"{repo_slug}@{branch}"
    if cache_key in _repo_readme_cache:
        return _repo_readme_cache[cache_key]

    for candidate in ("README.md", "README", "readme.md", "Readme.md"):
        if fetch_raw_content(repo_slug, candidate, branch, quiet_404=True) is not None:
            _repo_readme_cache[cache_key] = True
            return True

    _repo_readme_cache[cache_key] = False
    return False


def categorize(name: str, description: str = "", tags: list = None,
               upstream_category: str = "") -> str:
    """Map a resource to one of the 11 unified categories."""
    tags = tags or []
    search_text = f"{name} {description} {' '.join(tags)} {upstream_category}".lower()

    # Try upstream category first
    if upstream_category:
        cat_lower = upstream_category.lower()
        if cat_lower in CATEGORY_MAP:
            return CATEGORY_MAP[cat_lower]

    # Try matching against all keywords
    for keyword, category in CATEGORY_MAP.items():
        if keyword in search_text:
            return category

    return "tooling"  # default


def extract_tags(name: str, description: str = "") -> list:
    """Extract tech stack tags from name and description."""
    text = f"{name} {description}".lower()
    found = []
    tag_keywords = {
        "react": "react", "next.js": "nextjs", "nextjs": "nextjs",
        "vue": "vue", "angular": "angular", "svelte": "svelte",
        "typescript": "typescript", "javascript": "javascript",
        "python": "python", "go": "go", "rust": "rust",
        "java": "java", "ruby": "ruby", "php": "php",
        "swift": "swift", "kotlin": "kotlin", "flutter": "flutter",
        "docker": "docker", "kubernetes": "kubernetes",
        "postgres": "postgres", "mysql": "mysql", "mongodb": "mongodb",
        "redis": "redis", "graphql": "graphql", "rest": "rest-api",
        "fastapi": "fastapi", "django": "django", "flask": "flask",
        "express": "express", "node": "nodejs",
        "tailwind": "tailwind", "css": "css",
        "aws": "aws", "gcp": "gcp", "azure": "azure",
        "terraform": "terraform",
        "jest": "jest", "playwright": "playwright", "cypress": "cypress",
        "prisma": "prisma", "supabase": "supabase",
        "openai": "openai", "langchain": "langchain",
        "git": "git", "eslint": "eslint",
    }
    for keyword, tag in tag_keywords.items():
        if keyword in text and tag not in found:
            found.append(tag)
    return found


def merge_topics_into_tags(tags: list[str], topics: list[str]) -> list[str]:
    """Merge GitHub repo topics into existing tags, deduplicated and lowercased."""
    seen = set()
    result = []
    for t in tags + [t.lower() for t in topics]:
        t_lower = t.lower().strip()
        if t_lower and t_lower not in seen:
            seen.add(t_lower)
            result.append(t_lower)
    return result


def normalize_source_url(url: str) -> str:
    """Normalize a source URL for dedup comparison."""
    url = url.lower().rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    return url


def deduplicate(entries: list) -> list:
    """Deduplicate entries by id and source_url. Earlier entries take priority."""
    seen_ids = {}    # id -> entry
    seen_urls = {}   # normalized_url -> entry
    result = []
    for entry in entries:
        eid = entry.get("id", "")
        if eid and eid in seen_ids:
            continue

        source_url = entry.get("source_url", "")
        if source_url:
            norm = normalize_source_url(source_url)
            if norm in seen_urls:
                continue
            seen_urls[norm] = entry

        if eid:
            seen_ids[eid] = entry
        result.append(entry)
    return result


def to_kebab_case(name: str) -> str:
    """Convert a name to kebab-case id."""
    s = re.sub(r"[^\w\s-]", "", name.lower())
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s


def save_index(entries: list, output_path: str):
    """Save entries to a JSON index file."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved {len(entries)} entries to {output_path}")


def load_index(path: str) -> list:
    """Load entries from a JSON index file. Returns empty list if not found."""
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Failed to load {path}: {e}")
        return []


def is_coding_related(act: str, prompt_text: str) -> bool:
    """Check if a prompt is coding/development related."""
    text = f"{act} {prompt_text}".lower()
    return any(re.search(r'\b' + re.escape(kw) + r'\b', text) for kw in CODING_KEYWORDS)
