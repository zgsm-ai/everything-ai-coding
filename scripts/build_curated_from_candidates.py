#!/usr/bin/env python3
"""Build curated.json files from curated_candidates.json.

Reads catalog/maintenance/curated_candidates.json, looks up full entry data
from catalog/index.json, builds properly-shaped curated entries, merges with
existing curated files, and writes to catalog/{mcp,skills,rules,prompts}/curated.json.
"""

import json
import os
from datetime import date
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CANDIDATES_PATH = os.path.join(REPO_ROOT, "catalog/maintenance/curated_candidates.json")
INDEX_PATH = os.path.join(REPO_ROOT, "catalog/index.json")
CURATED_PATHS = {
    "mcp": os.path.join(REPO_ROOT, "catalog/mcp/curated.json"),
    "skill": os.path.join(REPO_ROOT, "catalog/skills/curated.json"),
    "rule": os.path.join(REPO_ROOT, "catalog/rules/curated.json"),
    "prompt": os.path.join(REPO_ROOT, "catalog/prompts/curated.json"),
}

TODAY = date.today().isoformat()

# Tech stack heuristics: keyword → tech_stack list
# Keys are lowercased substrings to search in name+description+tags combined text
TECH_STACK_HEURISTICS = [
    # MCP official servers
    (["server-github", "github-mcp", "github mcp"], ["git"]),
    (["server-postgres", "postgres", "postgresql"], ["postgres"]),
    (["server-sqlite", "sqlite"], ["sqlite"]),
    (["server-redis", "redis"], ["redis"]),
    (["server-puppeteer", "puppeteer"], ["typescript"]),
    (["server-filesystem", "filesystem"], []),
    (["server-fetch", "server-memory", "server-google-drive", "google-drive"], []),
    (["server-slack", "slack"], []),
    (["server-git", " git "], ["git"]),
    (["server-gitlab", "gitlab"], ["git"]),
    (["server-google-maps", "google-maps"], []),
    # Rules
    (["fastapi", "fast-api"], ["python", "fastapi"]),
    (["react", "nextjs", "next.js", "next js"], ["react", "typescript", "nextjs"]),
    (["django"], ["python", "django"]),
    (["flutter", "dart"], ["flutter", "dart"]),
    # General tech
    (["kubernetes", "k8s"], ["kubernetes"]),
    (["typescript", "ts"], ["typescript"]),
    (["python"], ["python"]),
    (["golang", " go "], ["go"]),
    (["rust"], ["rust"]),
    (["java"], ["java"]),
    (["swift", "ios"], ["swift"]),
    (["kotlin", "android"], ["kotlin"]),
    (["docker", "dockerfile"], ["docker"]),
    (["graphql"], ["graphql"]),
    (["sql", "database", "db"], ["sql"]),
    (["aws", "cdk"], ["aws"]),
    (["neo4j", "graph database", "cypher"], ["neo4j"]),
    (["clojure", "repl"], ["clojure"]),
    (["unity", "unity3d"], ["csharp"]),
    (["playwright"], ["typescript"]),
    (["airflow", "dag"], ["python", "airflow"]),
    (["drizzle", "orm"], ["typescript"]),
    (["bullmq", "bull mq"], ["typescript", "redis"]),
    (["expo", "react native", "nativewind"], ["react", "typescript"]),
    (["godot", "gdscript"], ["gdscript"]),
    (["monorepo", "nx", "turborepo"], ["typescript"]),
]


def assign_tech_stack(entry: dict) -> list:
    """Heuristically assign tech_stack based on name, description, tags."""
    name = (entry.get("name") or "").lower()
    desc = (entry.get("description") or "").lower()
    tags = " ".join(entry.get("tags") or []).lower()
    combined = f"{name} {desc} {tags}"

    for keywords, stack in TECH_STACK_HEURISTICS:
        for kw in keywords:
            if kw in combined:
                return stack

    return []


def load_json(path: str) -> list:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data: list) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def build_curated_entry(candidate: dict, index_entry: dict) -> dict:
    """Build a curated entry from candidate + index data."""
    entry_type = candidate["type"]
    # Ensure singular type
    type_map = {"skills": "skill", "rules": "rule", "prompts": "prompt", "mcps": "mcp"}
    entry_type = type_map.get(entry_type, entry_type)

    entry = {
        "id": candidate["id"],
        "name": index_entry.get("name") or candidate["name"],
        "type": entry_type,
        "description": index_entry.get("description") or "",
        "source_url": candidate["source_url"],
        "stars": candidate.get("stars"),
        "category": candidate["category"],
        "tags": index_entry.get("tags") or [],
        "tech_stack": index_entry.get("tech_stack") or assign_tech_stack(index_entry),
        "install": index_entry.get("install") or {"method": "manual"},
        "source": "curated",
        "last_synced": TODAY,
    }

    # added_at required for mcp and skill types
    if entry_type in ("mcp", "skill"):
        entry["added_at"] = TODAY

    return entry


def main():
    candidates = load_json(CANDIDATES_PATH)
    index = load_json(INDEX_PATH)
    index_by_id = {e["id"]: e for e in index}

    # Load existing curated files, keyed by type
    existing: dict[str, list] = {}
    existing_ids: dict[str, set] = {}
    for type_key, path in CURATED_PATHS.items():
        entries = load_json(path)
        existing[type_key] = entries
        existing_ids[type_key] = {e["id"] for e in entries}

    # Track what gets added
    added: dict[str, list] = {k: [] for k in CURATED_PATHS}
    skipped_already_curated = []
    skipped_not_in_index = []

    for candidate in candidates:
        cid = candidate["id"]
        ctype_raw = candidate["type"]
        # Normalize type to singular
        type_map = {"skills": "skill", "rules": "rule", "prompts": "prompt", "mcps": "mcp"}
        ctype = type_map.get(ctype_raw, ctype_raw)

        type_key = ctype  # matches CURATED_PATHS keys

        # Skip if already in curated
        if cid in existing_ids.get(type_key, set()):
            skipped_already_curated.append(cid)
            continue

        # Look up in index
        index_entry = index_by_id.get(cid)
        if not index_entry:
            skipped_not_in_index.append(cid)
            print(f"  WARNING: {cid} not found in index.json, skipping")
            continue

        # Build entry
        entry = build_curated_entry(candidate, index_entry)

        # If tech_stack is still empty, try heuristic again on candidate data
        if not entry["tech_stack"]:
            entry["tech_stack"] = assign_tech_stack({
                "name": candidate.get("name", ""),
                "description": index_entry.get("description", ""),
                "tags": index_entry.get("tags", []),
            })

        existing[type_key].append(entry)
        added[type_key].append(cid)

    # Write all curated files
    for type_key, path in CURATED_PATHS.items():
        save_json(path, existing[type_key])

    # Summary
    print("\n=== Build Summary ===")
    total_added = sum(len(v) for v in added.values())
    print(f"Total new entries added: {total_added}")
    for type_key, ids in added.items():
        if ids:
            print(f"  {type_key}: +{len(ids)} new")
            for cid in ids:
                print(f"    - {cid}")
    if skipped_already_curated:
        print(f"\nSkipped (already curated): {len(skipped_already_curated)}")
        for cid in skipped_already_curated:
            print(f"  - {cid}")
    if skipped_not_in_index:
        print(f"\nSkipped (not in index): {len(skipped_not_in_index)}")
        for cid in skipped_not_in_index:
            print(f"  - {cid}")


if __name__ == "__main__":
    main()
