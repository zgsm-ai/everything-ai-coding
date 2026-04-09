#!/usr/bin/env python3
"""
Generate curated candidates from catalog/index.json using a three-layer strategy.

Layer 1 - Official sources (~20): source_url contains modelcontextprotocol or anthropics
Layer 2 - Community high-star (~25): stars > 500 AND final_score >= 70 AND health.score >= 60
Layer 3 - Category gap fill (~15): entries covering category×type combos not yet represented

Output: catalog/maintenance/curated_candidates.json
"""

import json
import os
import sys
from collections import defaultdict

CATALOG_DIR = os.path.join(os.path.dirname(__file__), "..", "catalog")
INDEX_PATH = os.path.join(CATALOG_DIR, "index.json")
MAINTENANCE_DIR = os.path.join(CATALOG_DIR, "maintenance")
OUTPUT_PATH = os.path.join(MAINTENANCE_DIR, "curated_candidates.json")

CURATED_PATHS = {
    "mcp":     os.path.join(CATALOG_DIR, "mcp", "curated.json"),
    "skill":   os.path.join(CATALOG_DIR, "skills", "curated.json"),
    "rule":    os.path.join(CATALOG_DIR, "rules", "curated.json"),
    "prompt":  os.path.join(CATALOG_DIR, "prompts", "curated.json"),
}

# Target counts per category×type
TARGETS = {
    "tooling":       {"mcp": 3, "skill": 2, "rule": 1, "prompt": 1},
    "backend":       {"mcp": 3, "skill": 2, "rule": 2, "prompt": 1},
    "frontend":      {"mcp": 2, "skill": 2, "rule": 2, "prompt": 1},
    "ai-ml":         {"mcp": 2, "skill": 2, "rule": 1, "prompt": 1},
    "database":      {"mcp": 3, "skill": 1, "rule": 1, "prompt": 1},
    "devops":        {"mcp": 2, "skill": 1, "rule": 1, "prompt": 1},
    "security":      {"mcp": 2, "skill": 1, "rule": 1, "prompt": 1},
    "testing":       {"mcp": 1, "skill": 1, "rule": 1, "prompt": 1},
    "mobile":        {"mcp": 1, "skill": 1, "rule": 1, "prompt": 1},
    "documentation": {"mcp": 1, "skill": 1, "rule": 1, "prompt": 1},
    "fullstack":     {"mcp": 1, "skill": 1, "rule": 1, "prompt": 1},
}

OFFICIAL_KEYWORDS = ["modelcontextprotocol", "anthropics"]


def normalize_url(url):
    """Normalize a source URL for comparison (lowercase, strip trailing slash)."""
    if not url:
        return ""
    return url.lower().rstrip("/")


def load_curated_lookups():
    """Load all curated.json files and return sets of ids and normalized source_urls."""
    curated_ids = set()
    curated_urls = set()
    for type_key, path in CURATED_PATHS.items():
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            entries = json.load(f)
        for entry in entries:
            if entry.get("id"):
                curated_ids.add(entry["id"])
            if entry.get("source_url"):
                curated_urls.add(normalize_url(entry["source_url"]))
    return curated_ids, curated_urls


def is_existing_in_curated(entry, curated_ids, curated_urls):
    """Return True if this entry is already in any curated.json."""
    if entry.get("id") in curated_ids:
        return True
    if normalize_url(entry.get("source_url")) in curated_urls:
        return True
    return False


def is_official(entry):
    """Return True if source_url contains official keywords."""
    url = (entry.get("source_url") or "").lower()
    return any(kw in url for kw in OFFICIAL_KEYWORDS)


def is_community_highstar(entry):
    """Return True if entry meets community high-star criteria."""
    stars = entry.get("stars") or 0
    final_score = (entry.get("evaluation") or {}).get("final_score") or 0
    health_score = (entry.get("health") or {}).get("score") or 0
    return stars > 500 and final_score >= 70 and health_score >= 60


def get_final_score(entry):
    return (entry.get("evaluation") or {}).get("final_score") or 0


def make_candidate(entry, tier, curated_ids, curated_urls):
    """Build a candidate object from an index entry."""
    return {
        "id": entry.get("id", ""),
        "name": entry.get("name", ""),
        "type": entry.get("type", ""),
        "category": entry.get("category", ""),
        "source_url": entry.get("source_url", ""),
        "stars": entry.get("stars") or 0,
        "final_score": get_final_score(entry),
        "health_score": (entry.get("health") or {}).get("score") or 0,
        "tier": tier,
        "existing_in_curated": is_existing_in_curated(entry, curated_ids, curated_urls),
    }


def apply_cap(candidates_by_cat_type):
    """Cap candidates per category×type to the target count, keeping top by final_score."""
    capped = []
    for (cat, typ), entries in candidates_by_cat_type.items():
        target = (TARGETS.get(cat) or {}).get(typ) or 1
        sorted_entries = sorted(entries, key=lambda c: c["final_score"], reverse=True)
        capped.extend(sorted_entries[:target])
    return capped


def print_summary(candidates):
    """Print a summary table to stdout."""
    categories = sorted(TARGETS.keys())
    types = ["mcp", "skill", "rule", "prompt"]

    # Build counts
    counts = defaultdict(lambda: defaultdict(int))
    for c in candidates:
        counts[c["category"]][c["type"]] += 1

    col_w = 13
    type_w = 7

    # Header
    header = f"{'Category':<{col_w}} | {'MCP':^{type_w}} | {'Skill':^{type_w}} | {'Rule':^{type_w}} | {'Prompt':^{type_w}} | {'Total':^6}"
    sep = "-" * len(header)
    print(sep)
    print(header)
    print(sep)

    grand_total = 0
    for cat in categories:
        row_total = sum(counts[cat][t] for t in types)
        grand_total += row_total
        row = (
            f"{cat:<{col_w}} | "
            f"{counts[cat]['mcp']:^{type_w}} | "
            f"{counts[cat]['skill']:^{type_w}} | "
            f"{counts[cat]['rule']:^{type_w}} | "
            f"{counts[cat]['prompt']:^{type_w}} | "
            f"{row_total:^6}"
        )
        print(row)

    print(sep)
    total_row = (
        f"{'TOTAL':<{col_w}} | "
        f"{sum(counts[c]['mcp'] for c in categories):^{type_w}} | "
        f"{sum(counts[c]['skill'] for c in categories):^{type_w}} | "
        f"{sum(counts[c]['rule'] for c in categories):^{type_w}} | "
        f"{sum(counts[c]['prompt'] for c in categories):^{type_w}} | "
        f"{grand_total:^6}"
    )
    print(total_row)
    print(sep)

    # New vs existing breakdown
    new_count = sum(1 for c in candidates if not c["existing_in_curated"])
    existing_count = sum(1 for c in candidates if c["existing_in_curated"])
    print(f"\nNew candidates: {new_count}  |  Already in curated: {existing_count}  |  Total: {len(candidates)}")

    # Tier breakdown
    tier_counts = defaultdict(int)
    for c in candidates:
        tier_counts[c["tier"]] += 1
    print(f"Tiers: official={tier_counts['official']}  community={tier_counts['community']}  gap_fill={tier_counts['gap_fill']}")


def main():
    # Load index
    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        index = json.load(f)

    print(f"Loaded {len(index)} entries from catalog/index.json")

    # Load curated lookups
    curated_ids, curated_urls = load_curated_lookups()
    print(f"Curated lookups: {len(curated_ids)} ids, {len(curated_urls)} urls")

    # Track seen ids to avoid duplicates across layers
    seen_ids = set()

    # Layer 1: Official sources
    layer1 = []
    for entry in index:
        if is_official(entry) and entry.get("id") not in seen_ids:
            layer1.append(make_candidate(entry, "official", curated_ids, curated_urls))
            seen_ids.add(entry["id"])

    print(f"Layer 1 (official): {len(layer1)} candidates")

    # Layer 2: Community high-star
    layer2 = []
    for entry in index:
        if is_community_highstar(entry) and entry.get("id") not in seen_ids:
            layer2.append(make_candidate(entry, "community", curated_ids, curated_urls))
            seen_ids.add(entry["id"])

    print(f"Layer 2 (community high-star): {len(layer2)} candidates (before cap)")

    # Build category×type index of layers 1+2 for gap detection
    covered = defaultdict(set)  # (cat, type) -> set of ids
    for c in layer1 + layer2:
        covered[(c["category"], c["type"])].add(c["id"])

    # Layer 3: Gap fill - one entry per uncovered category×type combo
    # Index entries by (category, type) for efficient lookup
    by_cat_type = defaultdict(list)
    for entry in index:
        cat = entry.get("category", "")
        typ = entry.get("type", "")
        if cat in TARGETS and typ in TARGETS.get(cat, {}):
            by_cat_type[(cat, typ)].append(entry)

    layer3 = []
    for cat, type_targets in TARGETS.items():
        for typ in type_targets:
            if len(covered[(cat, typ)]) == 0:
                # Find best entry not yet seen
                candidates_for_slot = [
                    e for e in by_cat_type[(cat, typ)]
                    if e.get("id") not in seen_ids
                ]
                if candidates_for_slot:
                    best = max(candidates_for_slot, key=get_final_score)
                    layer3.append(make_candidate(best, "gap_fill", curated_ids, curated_urls))
                    seen_ids.add(best["id"])

    print(f"Layer 3 (gap fill): {len(layer3)} candidates")

    # Combine all candidates
    all_candidates = layer1 + layer2 + layer3

    # Apply per-category×type cap, keeping top by final_score
    # Group into category×type buckets
    buckets = defaultdict(list)
    for c in all_candidates:
        cat = c["category"]
        typ = c["type"]
        if cat in TARGETS and typ in (TARGETS.get(cat) or {}):
            buckets[(cat, typ)].append(c)
        # Entries outside TARGETS categories still get included (no cap)

    capped = apply_cap(buckets)

    # Re-add entries from categories not in TARGETS (passthrough)
    known_cats = set(TARGETS.keys())
    extra = [c for c in all_candidates if c["category"] not in known_cats]
    final_candidates = capped + extra

    # Sort for deterministic output: by category, type, final_score desc
    final_candidates.sort(key=lambda c: (c["category"], c["type"], -c["final_score"]))

    # Write output
    os.makedirs(MAINTENANCE_DIR, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(final_candidates, f, ensure_ascii=False, indent=2)

    print(f"\nWrote {len(final_candidates)} candidates to catalog/maintenance/curated_candidates.json\n")
    print_summary(final_candidates)


if __name__ == "__main__":
    main()
