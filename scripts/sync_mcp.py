#!/usr/bin/env python3
"""Sync MCP servers from mcp.so seed + wong2/awesome-mcp-servers + Awesome-MCP-ZH."""

import html
import json
import os
import re
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from utils import (
    GITHUB_TOKEN,
    fetch_raw_content,
    get_repo_meta,
    categorize,
    extract_tags,
    to_kebab_case,
    save_index,
    logger,
)

CATALOG_DIR = os.path.join(os.path.dirname(__file__), "..", "catalog", "mcp")
SEED_PATH = os.path.join(CATALOG_DIR, "mcp_so_seed.json")
MIN_STARS = 10
TODAY = date.today().isoformat()
README_ENRICH_LIMIT = int(
    os.environ.get("MCP_README_ENRICH_LIMIT", "100" if not GITHUB_TOKEN else "1200")
)


def _load_repo_meta(repo_url: str) -> dict | None:
    return get_repo_meta(repo_url)


def normalize_github_url(url: str) -> str:
    """Normalize a GitHub URL for dedup comparison.
    Strips trailing slashes, .git suffix, tree/blob paths for monorepo sub-dirs."""
    url = url.strip().rstrip("/")
    url = re.sub(r"\.git$", "", url)
    # Remove query/fragment
    url = re.sub(r"[?#].*$", "", url)
    return url.lower()


def load_seed() -> list:
    """Load mcp.so seed data as highest priority source."""
    if not os.path.exists(SEED_PATH):
        logger.warning(f"Seed file not found: {SEED_PATH}")
        return []
    try:
        with open(SEED_PATH, "r") as f:
            data = json.load(f)
        # Normalize stars: -1 (API failure sentinel) → None
        for entry in data:
            if entry.get("stars") is not None and entry["stars"] < 0:
                entry["stars"] = None
        logger.info(f"Loaded {len(data)} entries from mcp.so seed")
        return data
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Failed to load seed: {e}")
        return []


def parse_awesome_mcp_servers_wong2() -> list:
    """Parse wong2/awesome-mcp-servers README.md.
    Format: - **[Name](url)** - Description"""
    content = fetch_raw_content("wong2/awesome-mcp-servers", "README.md")
    if not content:
        logger.error("Failed to fetch wong2/awesome-mcp-servers README")
        return []

    entries = []
    current_category = ""

    for line in content.split("\n"):
        # Detect category headers
        cat_match = re.match(r"^#{2,3}\s+(.+)", line)
        if cat_match:
            current_category = cat_match.group(1).strip()
            continue

        # Skip non-server sections
        if current_category.lower() in ("sponsors", "clients", "frameworks"):
            continue

        # Parse: - **[Name](url)** - Description
        entry_match = re.match(
            r"^-\s+\*\*\[([^\]]+)\]\(([^)]+)\)\*\*\s*[-–—]\s*(.+)", line
        )
        if not entry_match:
            continue

        name = entry_match.group(1).strip()
        url = entry_match.group(2).strip()
        description = entry_match.group(3).strip()

        if "github.com" not in url:
            continue

        meta = _load_repo_meta(url)
        stars = meta["stars"] if meta else None
        pushed_at = meta["pushed_at"] if meta else None
        if stars == 0:
            stars = None
        if stars is not None and stars < MIN_STARS:
            continue

        tags = extract_tags(name, description)
        category = categorize(name, description, tags, current_category)

        entries.append(
            {
                "id": to_kebab_case(name),
                "name": name,
                "type": "mcp",
                "description": description,
                "source_url": url,
                "stars": stars,
                "pushed_at": pushed_at,
                "category": category,
                "tags": tags,
                "tech_stack": [],
                "install": {"method": "manual"},
                "source": "awesome-mcp-servers",
                "last_synced": TODAY,
            }
        )

    logger.info(f"Parsed {len(entries)} MCP entries from wong2/awesome-mcp-servers")
    return entries


def parse_awesome_mcp_zh() -> list:
    """Parse yzfly/Awesome-MCP-ZH README.md (Markdown tables)."""
    content = fetch_raw_content("yzfly/Awesome-MCP-ZH", "README.md")
    if not content:
        logger.error("Failed to fetch Awesome-MCP-ZH README")
        return []

    entries = []
    # Match table rows: | [Name](url) | description | notes |
    row_pattern = re.compile(
        r"\|\s*\[([^\]]+)\]\(([^)]+)\)\s*\|\s*([^|]+)\|\s*([^|]*)\|"
    )

    for match in row_pattern.finditer(content):
        name = match.group(1).strip()
        url = match.group(2).strip()
        description = match.group(3).strip()

        if "github.com" not in url:
            continue

        meta = _load_repo_meta(url)
        stars = meta["stars"] if meta else None
        pushed_at = meta["pushed_at"] if meta else None
        if stars == 0:
            stars = None
        if stars is not None and stars < MIN_STARS:
            continue

        tags = extract_tags(name, description)
        category = categorize(name, description, tags)

        entries.append(
            {
                "id": to_kebab_case(name),
                "name": name,
                "type": "mcp",
                "description": description,
                "source_url": url,
                "stars": stars,
                "pushed_at": pushed_at,
                "category": category,
                "tags": tags,
                "tech_stack": [],
                "install": {"method": "manual"},
                "source": "awesome-mcp-zh",
                "last_synced": TODAY,
            }
        )

    logger.info(f"Parsed {len(entries)} MCP entries from Awesome-MCP-ZH")
    return entries


def detect_placeholders(config: dict) -> tuple[str, dict]:
    """Detect placeholder patterns in install config.
    Returns (method, placeholder_hints)."""
    hints = {}
    args = config.get("args", [])
    env = config.get("env", {})

    for arg in args:
        if isinstance(arg, str):
            matches = re.findall(r"<([A-Za-z][A-Za-z0-9_-]+)>", arg)
            for m in matches:
                hints[m] = (
                    f"Replace with actual {m.lower().replace('_', ' ').replace('-', ' ')}"
                )

    for key, val in env.items():
        if isinstance(val, str):
            if (
                val == ""
                or re.match(r"^(YOUR_|your_)", val)
                or re.match(r"^<.+>$", val)
            ):
                hints[key] = f"Set your {key}"

    if hints:
        return "mcp_config_template", hints
    return "mcp_config", {}


def extract_readme_mcp_config(github_url: str) -> dict | None:
    """Try to extract mcpServers config from a GitHub repo's README.
    Returns install config dict or None."""
    # Extract repo slug
    match = re.search(r"github\.com/([^/]+/[^/?#]+)", github_url)
    if not match:
        return None

    repo_slug = match.group(1).rstrip("/")
    # Strip tree/blob paths for monorepo sub-dirs
    repo_slug = re.sub(r"/(?:tree|blob)/.*$", "", repo_slug)

    # Try README.md, then readme.md
    readme = fetch_raw_content(repo_slug, "README.md", quiet_404=True)
    if not readme:
        readme = fetch_raw_content(repo_slug, "readme.md", quiet_404=True)
    if not readme:
        return None

    # Find JSON code blocks containing mcpServers
    json_blocks = re.findall(
        r"```(?:json|jsonc|js|javascript)\s*\n(.*?)```", readme, re.DOTALL
    )

    for block in json_blocks:
        if '"mcpServers"' not in block:
            continue
        try:
            # Clean potential comments (// style) for jsonc
            cleaned = re.sub(r"//.*$", "", block, flags=re.MULTILINE)
            parsed = json.loads(cleaned)
            servers = parsed.get("mcpServers", {})
            if not servers:
                continue

            first_key = next(iter(servers))
            server_config = servers[first_key]
            config = {
                "command": server_config.get("command", ""),
                "args": server_config.get("args", []),
            }
            if server_config.get("env"):
                config["env"] = server_config["env"]

            return config
        except (json.JSONDecodeError, StopIteration, AttributeError):
            continue

    return None


def merge_three_sources(seed: list, wong2: list, zh: list) -> list:
    """Merge three sources with dedup by GitHub URL.
    Priority: mcp.so seed > Awesome-MCP-ZH > wong2/awesome-mcp-servers.
    If lower priority has ZH description and higher doesn't, merge it."""
    # Index by normalized GitHub URL
    url_map: dict[str, dict] = {}
    zh_descriptions: dict[str, str] = {}

    # Collect ZH descriptions first for merging
    for entry in zh:
        norm_url = normalize_github_url(entry.get("source_url", ""))
        if norm_url:
            zh_descriptions[norm_url] = entry.get("description", "")

    # Process in priority order: seed first, then ZH, then wong2
    for entries, source_label in [
        (seed, "mcp.so"),
        (zh, "awesome-mcp-zh"),
        (wong2, "awesome-mcp-servers"),
    ]:
        for entry in entries:
            norm_url = normalize_github_url(entry.get("source_url", ""))
            if not norm_url:
                continue

            if norm_url in url_map:
                # Already have a higher-priority entry
                existing = url_map[norm_url]
                # Merge ZH description if current entry has one and existing doesn't look Chinese
                if source_label == "awesome-mcp-zh":
                    desc = entry.get("description", "")
                    existing_desc = existing.get("description", "")
                    # If ZH desc contains Chinese chars and existing doesn't
                    if re.search(r"[\u4e00-\u9fff]", desc) and not re.search(
                        r"[\u4e00-\u9fff]", existing_desc
                    ):
                        existing["description_zh"] = desc
                continue

            url_map[norm_url] = entry

    result = list(url_map.values())

    # For entries from ZH/wong2 that don't have install config,
    # merge ZH description if available
    for entry in result:
        norm_url = normalize_github_url(entry.get("source_url", ""))
        if norm_url in zh_descriptions and "description_zh" not in entry:
            zh_desc = zh_descriptions[norm_url]
            existing_desc = entry.get("description", "")
            if re.search(r"[\u4e00-\u9fff]", zh_desc) and not re.search(
                r"[\u4e00-\u9fff]", existing_desc
            ):
                entry["description_zh"] = zh_desc

    logger.info(f"Three-source merge: {len(result)} unique entries")
    return result


def enrich_missing_configs(entries: list) -> list:
    """For entries without install config, try README mcpServers extraction."""
    manual_entries = [
        e for e in entries if e.get("install", {}).get("method") == "manual"
    ]
    manual_entries.sort(key=_readme_enrich_priority)
    if README_ENRICH_LIMIT > 0:
        probe_entries = manual_entries[:README_ENRICH_LIMIT]
    else:
        probe_entries = []

    logger.info(
        f"Attempting README config extraction for {len(probe_entries)}/{len(manual_entries)} "
        "manual entries..."
    )
    if len(probe_entries) < len(manual_entries):
        logger.info(
            "README enrichment capped at "
            f"{README_ENRICH_LIMIT} entries; prioritizing non-seed entries and higher-star repos"
        )

    enriched_count = 0
    for entry in probe_entries:
        github_url = entry.get("source_url", "")
        if not github_url:
            continue

        config = extract_readme_mcp_config(github_url)
        if not config:
            continue

        method, placeholder_hints = detect_placeholders(config)
        entry["install"] = {"method": method, "config": config}
        if placeholder_hints:
            entry["install"]["placeholder_hints"] = placeholder_hints
        enriched_count += 1

    logger.info(
        f"Enriched {enriched_count}/{len(probe_entries)} probed entries from README"
    )
    return entries


def _readme_enrich_priority(entry: dict) -> tuple:
    """Prioritize non-seed entries first, then higher-star repos."""
    source_rank = 0 if entry.get("source") != "mcp.so" else 1
    stars = entry.get("stars")
    star_rank = -(stars if stars is not None else -1)
    return (source_rank, star_rank, entry.get("name", "").lower())


def _backfill_seed_stars(seed: list) -> list:
    """Backfill stars for seed entries where stars=None (previous API failures).

    - Queries GitHub API for entries with missing stars
    - Filters out entries with stars < MIN_STARS or deleted repos (404)
    - Writes updated star values back to the seed file
    """
    if not GITHUB_TOKEN:
        logger.info("No GITHUB_TOKEN; skipping seed star backfill")
        return seed

    need_backfill = [e for e in seed if e.get("stars") is None]
    if not need_backfill:
        logger.info("All seed entries have stars; no backfill needed")
        return seed

    logger.info(f"Backfilling stars for {len(need_backfill)} seed entries...")
    updated = 0
    removed_404 = 0
    removed_low = 0
    still_none = 0
    keep_set = set()  # source_urls to keep

    for i, entry in enumerate(need_backfill):
        meta = _load_repo_meta(entry.get("source_url", ""))
        if meta is None:
            # API failed or 404 — mark for removal
            removed_404 += 1
            continue
        stars = meta.get("stars", 0)
        if stars < MIN_STARS:
            removed_low += 1
            continue
        entry["stars"] = stars
        keep_set.add(id(entry))
        updated += 1
        if (i + 1) % 200 == 0:
            logger.info(f"  Backfill progress: {i+1}/{len(need_backfill)}")

    # Build filtered seed: keep entries that had stars already, or passed backfill
    result = []
    for entry in seed:
        if entry.get("stars") is not None and entry["stars"] >= MIN_STARS:
            result.append(entry)
        elif id(entry) in keep_set:
            result.append(entry)
        # else: filtered out (None stars that failed backfill, or low stars)

    logger.info(
        f"Seed backfill done: {updated} recovered, "
        f"{removed_404} deleted/404, {removed_low} below MIN_STARS, "
        f"{len(seed)} → {len(result)} entries"
    )

    # Write back to seed file so next run doesn't re-query
    try:
        seed_path = os.path.join(CATALOG_DIR, "mcp_so_seed.json")
        # Convert None stars back to -1 sentinel for seed file format
        save_data = []
        for entry in result:
            save_data.append(entry)
        with open(seed_path, "w") as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)
        logger.info(f"Updated seed file: {len(save_data)} entries")
    except IOError as e:
        logger.error(f"Failed to write seed file: {e}")

    return result


def sync():
    # Load three sources
    seed = load_seed()
    if not GITHUB_TOKEN:
        logger.info(
            "GITHUB_TOKEN not set; skipping GitHub API enrichment for awesome-list MCP repos"
        )
    else:
        seed = _backfill_seed_stars(seed)
    wong2 = parse_awesome_mcp_servers_wong2()
    zh = parse_awesome_mcp_zh()

    logger.info(f"Source counts: seed={len(seed)}, wong2={len(wong2)}, zh={len(zh)}")

    # Three-source merge with dedup by GitHub URL
    merged = merge_three_sources(seed, wong2, zh)

    # Log source distribution after merge
    sources_after_merge = {}
    for e in merged:
        s = e.get("source", "unknown")
        sources_after_merge[s] = sources_after_merge.get(s, 0) + 1
    logger.info(f"After merge: {len(merged)} entries, sources={sources_after_merge}")

    # Enrich manual entries with README mcpServers extraction
    merged = enrich_missing_configs(merged)

    logger.info(f"Final: {len(merged)} MCP entries")

    output_path = os.path.join(CATALOG_DIR, "index.json")
    save_index(merged, output_path)


if __name__ == "__main__":
    sync()
