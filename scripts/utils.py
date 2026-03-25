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
    url = f"https://api.github.com/{path.lstrip('/')}"
    headers = {"Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    req = Request(url, headers=headers)
    for attempt in range(3):
        try:
            with urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except HTTPError as e:
            if e.code == 403:  # Rate limit
                if GITHUB_TOKEN:
                    reset = e.headers.get("X-RateLimit-Reset")
                    if reset:
                        wait = max(int(reset) - int(time.time()), 1)
                        logger.warning(f"Rate limited, waiting {min(wait, 60)}s...")
                        time.sleep(min(wait, 60))
                        continue
                else:
                    logger.warning("Rate limited (no token). Skipping API call.")
                    return None
            elif e.code == 404:
                return None
            logger.error(f"GitHub API error {e.code}: {url}")
            return None
        except (URLError, TimeoutError) as e:
            logger.error(f"Network error (attempt {attempt+1}): {e}")
            if attempt < 2:
                time.sleep(2 ** attempt)
    return None


def get_stars(repo_url: str) -> int:
    """Get star count for a GitHub repo URL. Returns 0 on error."""
    match = re.search(r"github\.com/([^/]+/[^/]+?)(?:\.git)?(?:/|$|\?|#)", repo_url)
    if not match:
        return 0
    repo_path = match.group(1)
    data = github_api(f"repos/{repo_path}")
    if data and "stargazers_count" in data:
        return data["stargazers_count"]
    return 0


def fetch_raw_content(repo: str, path: str, branch: str = "main") -> Optional[str]:
    """Fetch raw file content from GitHub."""
    url = f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"
    req = Request(url)
    if GITHUB_TOKEN:
        req.add_header("Authorization", f"token {GITHUB_TOKEN}")
    try:
        with urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except (HTTPError, URLError, TimeoutError) as e:
        logger.error(f"Failed to fetch {url}: {e}")
        return None


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


def deduplicate(entries: list) -> list:
    """Deduplicate entries by id, preferring the entry with more stars."""
    seen = {}
    for entry in entries:
        eid = entry.get("id", "")
        if eid not in seen or entry.get("stars", 0) > seen[eid].get("stars", 0):
            seen[eid] = entry
    return list(seen.values())


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
