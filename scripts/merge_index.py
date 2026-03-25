#!/usr/bin/env python3
"""Merge all type-specific indexes and curated files into catalog/index.json."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from utils import load_index, save_index, deduplicate, logger

CATALOG_DIR = os.path.join(os.path.dirname(__file__), "..", "catalog")
TYPES = ["mcp", "skills", "rules", "prompts"]


def merge():
    all_entries = []

    for resource_type in TYPES:
        type_dir = os.path.join(CATALOG_DIR, resource_type)

        # Load auto-synced index
        index_path = os.path.join(type_dir, "index.json")
        entries = load_index(index_path)
        logger.info(f"Loaded {len(entries)} entries from {resource_type}/index.json")
        all_entries.extend(entries)

        # Load curated entries (these take priority in dedup)
        curated_path = os.path.join(type_dir, "curated.json")
        curated = load_index(curated_path)
        logger.info(f"Loaded {len(curated)} entries from {resource_type}/curated.json")
        all_entries.extend(curated)

    # Deduplicate by source_url (later entries win, so curated overrides auto-synced)
    deduped = deduplicate(all_entries)

    # Sort by stars descending
    deduped.sort(key=lambda x: x.get("stars", 0), reverse=True)

    output_path = os.path.join(CATALOG_DIR, "index.json")
    save_index(deduped, output_path)

    # Print summary by type and category
    by_type = {}
    by_category = {}
    for entry in deduped:
        t = entry.get("type", "unknown")
        c = entry.get("category", "unknown")
        by_type[t] = by_type.get(t, 0) + 1
        by_category[c] = by_category.get(c, 0) + 1

    logger.info(f"\nTotal: {len(deduped)} entries")
    logger.info(f"By type: {by_type}")
    logger.info(f"By category: {by_category}")


if __name__ == "__main__":
    merge()
