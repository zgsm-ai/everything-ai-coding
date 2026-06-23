#!/usr/bin/env python3
"""Build frontend data files from catalog/index.json and catalog/featured.md."""

import hashlib
import json
import os
import re
from collections import Counter

from source_registry import build_sources_payload

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG = os.path.join(ROOT, "catalog")
OUT = os.path.join(ROOT, "frontend", "public", "api")

# ---------------------------------------------------------------------------
# search-index / per-entry sharding tuning knobs
# ---------------------------------------------------------------------------
# Number of buckets the full per-entry data is sharded into. With ~23k entries
# this gives ~90 entries/bucket — small enough to fetch one bucket per Detail
# view, while keeping the file count fixed at 256 regardless of catalog growth.
ENTRY_SHARD_BUCKETS = 256
# Card "snippet" (truncated description) length kept in the slim search-index.
# It does double duty: list cards render it directly (no per-entry fetch), and
# PR2 indexes it as a MiniSearch field so description prose stays searchable
# WITHOUT being duplicated into ``search_text`` (which keeps the index small).
SNIPPET_MAX_CHARS = 160


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
    # Ensure all known types are present (with zero) so the frontend can rely
    # on stable keys even before the corresponding sync source has populated
    # the catalog.
    for known_type in ("mcp", "skill", "rule", "prompt", "plugin"):
        by_type.setdefault(known_type, 0)
    return {
        "total": len(items),
        "byType": dict(by_type),
        "byCategory": dict(sorted(by_category.items(), key=lambda x: -x[1])),
    }


def build_type_files(items):
    """Split items into per-type JSON files with fields needed for browse cards.

    By default, ``skills.json`` excludes entries with a non-empty ``bundled_in``
    field — those skills are already represented by their parent plugin entry,
    and surfacing both in browse views causes confusing duplicates. The full
    ``search-index.json`` retains them so client-side search stays complete.
    """
    type_map = {}
    for item in items:
        t = item["type"]
        if t == "skill" and item.get("bundled_in"):
            # Skip bundled-in skills from per-type listing (search-index keeps them).
            continue
        type_map.setdefault(t, []).append(slim_item(item))
    # Ensure plugins.json is always emitted (even empty) so consumers can rely
    # on a stable URL.
    type_map.setdefault("plugin", [])
    for t, arr in type_map.items():
        arr.sort(key=lambda x: -(x.get("final_score") or 0))
        fname = (
            f"{t}s.json" if t in ("skill", "rule", "prompt", "plugin") else f"{t}.json"
        )
        save_json(os.path.join(OUT, fname), arr)
        print(f"  {fname}: {len(arr)} items")


def slim_item(item):
    """Keep only fields needed for browse cards to reduce file size."""
    slim = {
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
    # Security scan block (add-security-risk-eval): passed through to frontend
    # so Detail page banner + ResourceCard shield icon can render. Only present
    # on entries the LLM successfully evaluated this cycle.
    security = item.get("security")
    if security is not None:
        slim["security"] = security
    # Plugin-specific fields (only present on plugin entries).
    if item.get("type") == "plugin":
        for key in ("marketplace_url", "platforms", "bundle", "manifest_completeness"):
            value = item.get(key)
            if value is not None:
                slim[key] = value
    # MCP installability fields — surface eval_bridge.map_result_to_entry()
    # outputs to the frontend so the Detail page can render an install-readiness
    # banner. Same pattern as the plugin block above: only carry values that
    # exist on the source entry, so older catalogs without these fields stay
    # backward-compatible.
    if item.get("type") == "mcp":
        for key in (
            "mcp_schema_valid",
            "mcp_install_state",
            "mcp_validation_tags",
            "mcp_installability_reason",
        ):
            value = item.get(key)
            if value is not None:
                slim[key] = value
    # Carry bundled_in onto skill entries when present (currently excluded from
    # per-type skills.json by build_type_files but kept in the search index).
    bundled_in = item.get("bundled_in")
    if bundled_in:
        slim["bundled_in"] = bundled_in
    return slim


# ---------------------------------------------------------------------------
# Slim search index + per-entry shards (06-22 search-index perf refactor)
# ---------------------------------------------------------------------------

_GITHUB_OWNER_REPO_RE = re.compile(
    r"github\.com/([^/]+)/([^/#?]+)", re.IGNORECASE
)


def parse_owner_repo(source_url):
    """Return ``(owner, repo)`` parsed from a GitHub ``source_url``.

    Returns ``(None, None)`` for non-GitHub or unparsable URLs. The ``.git``
    suffix (if any) is stripped from the repo segment.
    """
    if not source_url:
        return (None, None)
    m = _GITHUB_OWNER_REPO_RE.search(source_url)
    if not m:
        return (None, None)
    owner = m.group(1).strip()
    repo = m.group(2).strip()
    if repo.endswith(".git"):
        repo = repo[:-4]
    return (owner or None, repo or None)


def _truncate(text, limit):
    """Truncate ``text`` to ``limit`` chars, appending an ellipsis when cut."""
    if not text:
        return ""
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def build_search_text(item):
    """Build the ``search_text`` recall blob for one catalog entry.

    This deliberately does **not** repeat the name or description — those live
    once in the ``name`` and ``snippet`` fields (which PR2 indexes alongside
    ``search_text``), keeping the index small. ``search_text`` carries only the
    *extra* recall tokens those fields lack: tags + **source provenance**
    (source id, owner/repo, and bare owner parsed from ``source_url``) + LLM
    ``search_terms``. The source provenance is the crux of "search by
    source/author": queries like ``mattpocock`` / ``matt`` then surface every
    entry from that source, not just the ones whose name happens to contain the
    token.
    """
    owner, repo = parse_owner_repo(item.get("source_url", ""))
    source = item.get("source") or ""
    owner_repo = f"{owner}/{repo}" if owner and repo else ""

    parts = [
        " ".join(item.get("tags") or []),
        # Provenance tokens — the crux of "search by source/author".
        source,
        owner_repo,
        owner or "",
        " ".join(item.get("search_terms") or []),
    ]
    # De-dup whitespace-joined parts while preserving order; drop empties.
    seen = []
    for p in parts:
        p = (p or "").strip()
        if p and p not in seen:
            seen.append(p)
    return " ".join(seen)


def build_search_entry(item, buckets=ENTRY_SHARD_BUCKETS):
    """Build one slim search-index entry.

    Carries only the minimal fields a list card needs to render
    (id / name / type / source / stars / final_score / freshness_label +
    a short description snippet) plus the ``search_text`` recall blob. Heavy
    fields (full description / description_zh / install / bundled_in /
    tech_stack / install_method / source_url) are deliberately excluded — they
    live in the per-entry shards and are fetched on demand by the Detail view.

    The ``shard`` integer is the per-entry shard bucket for this id (same
    function as :func:`shard_bucket` / :func:`build_entry_shards`). It is
    carried inline so the frontend Detail view can fetch the one shard file
    (``api/entries/<shard>.json``) WITHOUT recomputing the hash — browsers
    cannot easily compute MD5 (SubtleCrypto has no MD5), so the build side
    pre-computes it here.
    """
    freshness = item.get("freshness_label")
    if not freshness:
        health = item.get("health")
        if isinstance(health, dict):
            freshness = health.get("freshness_label")
    return {
        "id": item["id"],
        "name": item.get("name", ""),
        "type": item.get("type", ""),
        "source": item.get("source", "") or "",
        "stars": item.get("stars"),
        "final_score": item.get("final_score", 0),
        "freshness_label": freshness,
        "snippet": _truncate(item.get("description", ""), SNIPPET_MAX_CHARS),
        "search_text": build_search_text(item),
        "shard": shard_bucket(item["id"], buckets),
    }


def build_search_index(items, buckets=ENTRY_SHARD_BUCKETS):
    """Build the slim search-index array (MiniSearch ``addAll``-ready).

    Each entry carries a ``shard`` field (computed with the same ``buckets``
    used by :func:`write_entry_shards`) so the frontend can fetch the matching
    per-entry shard without hashing on the client.
    """
    return [build_search_entry(item, buckets) for item in items]


def shard_bucket(entry_id, buckets=ENTRY_SHARD_BUCKETS):
    """Return the deterministic bucket index for an entry id.

    Uses a stable hash (md5) so the bucket number can be recomputed on the
    client from the entry id alone — the frontend fetches exactly one shard
    file per Detail view (O(1) lookup, no full per-type scan).
    """
    digest = hashlib.md5(entry_id.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % buckets


def build_entry_shards(items, buckets=ENTRY_SHARD_BUCKETS):
    """Group full per-entry data into ``buckets`` shard maps keyed by id.

    Returns a dict ``{bucket_index: {id: full_entry}}``. The full entry reuses
    ``slim_item`` (which already carries every field the Detail page renders:
    description / description_zh / install / health / evaluation / tags /
    tech_stack / bundle / bundled_in / security / mcp_* …).
    """
    shards = {}
    for item in items:
        entry_id = item["id"]
        bucket = shard_bucket(entry_id, buckets)
        shards.setdefault(bucket, {})[entry_id] = slim_item(item)
    return shards


def write_entry_shards(items, out_dir=None, buckets=ENTRY_SHARD_BUCKETS):
    """Write per-entry shard files to ``<out_dir>/entries/<bucket>.json``.

    Each shard is a ``{id: full_entry}`` map. The Detail view computes the
    bucket via ``shard_bucket(id)`` and fetches just that one file.
    """
    out_dir = out_dir or OUT
    shards = build_entry_shards(items, buckets)
    entries_dir = os.path.join(out_dir, "entries")
    # Clean stale shards so removed entries do not linger across runs.
    if os.path.isdir(entries_dir):
        for fname in os.listdir(entries_dir):
            if fname.endswith(".json"):
                os.remove(os.path.join(entries_dir, fname))
    os.makedirs(entries_dir, exist_ok=True)
    for bucket, entry_map in shards.items():
        save_json(os.path.join(entries_dir, f"{bucket}.json"), entry_map)
    return shards


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

    # 4. Data sources (About 页"数据源 / 信任分级"两个区块的真相来源)
    sources_payload = build_sources_payload(items)
    save_json(os.path.join(OUT, "sources.json"), sources_payload)
    print(
        f"sources.json: {len(sources_payload['sources'])} sources, "
        f"{len(sources_payload['tiers'])} tiers"
    )

    # 5. Slim search index (build from catalog/index.json — authoritative).
    #    We no longer copy catalog/search-index.json (which is heavy and lacks
    #    source provenance). Instead emit a slim, MiniSearch-ready array whose
    #    search_text carries source / owner-repo / owner for "search by source".
    search_index = build_search_index(items)
    si_path = os.path.join(OUT, "search-index.json")
    save_json(si_path, search_index)
    si_size_mb = os.path.getsize(si_path) / 1024 / 1024
    nonempty_source = sum(1 for e in search_index if e.get("source"))
    print(
        f"search-index.json: {len(search_index)} entries, {si_size_mb:.2f}MB, "
        f"{nonempty_source} with non-empty source"
    )

    # 6. Per-entry full data, sharded by id-hash into ENTRY_SHARD_BUCKETS files
    #    under api/entries/<bucket>.json. Detail fetches one shard per view.
    shards = write_entry_shards(items, OUT)
    total_sharded = sum(len(m) for m in shards.values())
    print(
        f"entries/: {len(shards)} shard files, {total_sharded} entries "
        f"(~{total_sharded // max(len(shards), 1)} per shard)"
    )

    print("\nDone! Files written to frontend/public/api/")


if __name__ == "__main__":
    main()
