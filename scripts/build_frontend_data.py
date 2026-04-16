#!/usr/bin/env python3
"""Build frontend data files from catalog/index.json and catalog/featured.md."""

import json
import os
import re
import shutil
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG = os.path.join(ROOT, "catalog")
OUT = os.path.join(ROOT, "frontend", "public", "api")


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))


def build_stats(items):
    by_type = Counter(i["type"] for i in items)
    by_category = Counter(i.get("category", "other") for i in items)
    return {
        "total": len(items),
        "byType": dict(by_type),
        "byCategory": dict(sorted(by_category.items(), key=lambda x: -x[1])),
    }


def build_type_files(items):
    """Split items into per-type JSON files with fields needed for browse cards."""
    type_map = {}
    for item in items:
        t = item["type"]
        type_map.setdefault(t, []).append(slim_item(item))
    for t, arr in type_map.items():
        arr.sort(key=lambda x: -(x.get("final_score") or 0))
        fname = f"{t}s.json" if t in ("skill", "rule", "prompt") else f"{t}.json"
        save_json(os.path.join(OUT, fname), arr)
        print(f"  {fname}: {len(arr)} items")


def slim_item(item):
    """Keep only fields needed for browse cards to reduce file size."""
    return {
        "id": item["id"],
        "name": item["name"],
        "type": item["type"],
        "description": item.get("description", ""),
        "description_zh": item.get("description_zh", ""),
        "source_url": item.get("source_url", ""),
        "stars": item.get("stars"),
        "category": item.get("category", "other"),
        "tags": item.get("tags", []),
        "tech_stack": item.get("tech_stack", []),
        "source": item.get("source", ""),
        "final_score": item.get("final_score", 0),
        "decision": item.get("decision", ""),
        "health": item.get("health"),
        "evaluation": item.get("evaluation"),
        "install": item.get("install"),
        "added_at": item.get("added_at"),
        "pushed_at": item.get("pushed_at"),
        "highlights": item.get("highlights"),
    }


EMOJI_TYPE = {"🔌": "mcp", "🎯": "skill", "📋": "rule", "💡": "prompt"}


def parse_featured(md_path, items_by_id):
    """Parse featured.md into structured sections."""
    with open(md_path, encoding="utf-8") as f:
        text = f.read()

    sections = []
    current_section = None

    for line in text.splitlines():
        # Section header: ### 🌐 Browser & Automation
        m = re.match(r"^###\s+\S+\s+(.+)", line)
        if m:
            if current_section:
                sections.append(current_section)
            current_section = {"title": m.group(1).strip(), "items": []}
            continue

        # Item: - 🔌 **[name](url)** — description ⭐ 30.5k  OR  `source`
        m = re.match(
            r"^-\s+(\S+)\s+\*\*\[(.+?)\]\((.+?)\)\*\*\s+—\s+(.+)", line
        )
        if m and current_section is not None:
            emoji, name, url, rest = m.groups()
            item_type = EMOJI_TYPE.get(emoji, "mcp")

            # Extract stars if present
            stars = None
            sm = re.search(r"⭐\s*([\d.]+)k", rest)
            if sm:
                stars = int(float(sm.group(1)) * 1000)

            # Find matching catalog item for enrichment
            catalog_item = None
            for item in items_by_id.values():
                if item.get("source_url") == url or item.get("name") == name:
                    catalog_item = item
                    break

            featured_item = {
                "id": catalog_item["id"] if catalog_item else name.replace("/", "-").lower(),
                "name": name,
                "type": item_type,
                "description": catalog_item.get("description", rest.split("⭐")[0].strip().rstrip("…").strip()) if catalog_item else rest.split("⭐")[0].strip().rstrip("…").strip(),
                "description_zh": catalog_item.get("description_zh", "") if catalog_item else "",
                "stars": catalog_item.get("stars", stars) if catalog_item else stars,
                "source_url": url,
                "source": catalog_item.get("source", "") if catalog_item else "",
                "final_score": catalog_item.get("final_score", 0) if catalog_item else 0,
            }
            current_section["items"].append(featured_item)

    if current_section:
        sections.append(current_section)

    return sections


def main():
    index_path = os.path.join(CATALOG, "index.json")
    featured_path = os.path.join(CATALOG, "featured.md")
    search_index_path = os.path.join(CATALOG, "search-index.json")

    print("Loading catalog/index.json...")
    items = load_json(index_path)
    items_by_id = {i["id"]: i for i in items}
    print(f"  {len(items)} items loaded")

    os.makedirs(OUT, exist_ok=True)

    # 1. Stats
    stats = build_stats(items)
    save_json(os.path.join(OUT, "stats.json"), stats)
    print(f"stats.json: total={stats['total']}")

    # 2. Featured
    if os.path.exists(featured_path):
        sections = parse_featured(featured_path, items_by_id)
        save_json(os.path.join(OUT, "featured.json"), sections)
        total_items = sum(len(s["items"]) for s in sections)
        print(f"featured.json: {len(sections)} sections, {total_items} items")
    else:
        print("WARNING: catalog/featured.md not found, skipping featured.json")

    # 3. Type-specific files
    build_type_files(items)

    # 4. Copy search index
    if os.path.exists(search_index_path):
        shutil.copy2(search_index_path, os.path.join(OUT, "search-index.json"))
        size_mb = os.path.getsize(search_index_path) / 1024 / 1024
        print(f"search-index.json: copied ({size_mb:.1f}MB)")
    else:
        print("WARNING: catalog/search-index.json not found")

    print("\nDone! Files written to frontend/public/api/")


if __name__ == "__main__":
    main()
