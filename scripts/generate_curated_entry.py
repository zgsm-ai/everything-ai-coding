#!/usr/bin/env python3
"""Generate a curated entry from a GitHub URL."""

import argparse
import json
import os
import re
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from utils import github_api, to_kebab_case, logger


def parse_github_url(url: str) -> tuple:
    """Parse owner and repo from a GitHub URL. Exits on invalid URL."""
    match = re.match(r"https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?(?:/.*)?$", url.rstrip("/"))
    if not match:
        logger.error(f"ERROR: only GitHub URLs are supported: {url}")
        sys.exit(1)
    return match.group(1), match.group(2)


def build_install(resource_type: str, url: str, repo_name: str,
                  owner: str = "") -> dict:
    """Build install field based on resource type."""
    if resource_type == "mcp":
        scope = f"@{owner}/" if owner else ""
        return {
            "method": "mcp_config",
            "config": {
                "command": "npx",
                "args": [f"{scope}{repo_name}"],
            },
        }
    elif resource_type == "skill":
        return {
            "method": "git_clone",
            "repo": url,
            "files": [],
        }
    else:  # rule, prompt
        return {
            "method": "download_file",
            "files": [],
        }


def generate_entry(url: str, resource_type: str, category: str) -> dict:
    """Generate a complete curated entry from a GitHub URL."""
    owner, repo_name = parse_github_url(url)

    # Fetch repo metadata
    repo_data = github_api(f"repos/{owner}/{repo_name}")
    if not repo_data:
        logger.error(f"ERROR: repository not found: {url}")
        sys.exit(1)

    # Fetch languages
    languages_data = github_api(f"repos/{owner}/{repo_name}/languages")
    tech_stack = []
    if languages_data:
        sorted_langs = sorted(languages_data.items(), key=lambda x: x[1], reverse=True)
        tech_stack = [lang.lower() for lang, _ in sorted_langs[:5]]

    description = repo_data.get("description") or ""
    if not description:
        logger.warning("WARNING: repository has no description, maintainer should add one")

    entry = {
        "id": to_kebab_case(repo_name),
        "name": repo_data.get("name", repo_name),
        "type": resource_type,
        "description": description,
        "source_url": f"https://github.com/{owner}/{repo_name}",
        "stars": repo_data.get("stargazers_count", 0),
        "category": category,
        "tags": repo_data.get("topics", []),
        "tech_stack": tech_stack,
        "install": build_install(resource_type, url, repo_name, owner=owner),
        "source": "curated",
        "last_synced": date.today().isoformat(),
    }

    pushed_at = repo_data.get("pushed_at")
    if pushed_at:
        entry["pushed_at"] = pushed_at

    return entry


def main():
    parser = argparse.ArgumentParser(description="Generate a curated entry from a GitHub URL")
    parser.add_argument("--url", required=True, help="GitHub repository URL")
    parser.add_argument("--type", required=True, choices=["mcp", "skill", "rule", "prompt"],
                        help="Resource type")
    parser.add_argument("--category", required=True,
                        choices=[
                            "frontend", "backend", "fullstack", "mobile", "devops",
                            "database", "testing", "security", "ai-ml", "tooling",
                            "documentation",
                        ],
                        help="Resource category")
    parser.add_argument("--reason", help="Recommendation reason (not saved in entry)")
    parser.add_argument("--output", help="Output file path (default: stdout)")
    args = parser.parse_args()

    entry = generate_entry(args.url, args.type, args.category)

    output = json.dumps(entry, indent=2, ensure_ascii=False)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output + "\n")
        logger.info(f"Saved entry to {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    main()
