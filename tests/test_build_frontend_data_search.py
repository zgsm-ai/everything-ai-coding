"""Tests for the slim search-index + per-entry shard build path in
``scripts/build_frontend_data.py`` (06-22 search-index perf refactor).

Covers:
- The slim search-index keeps only minimal card fields + ``search_text`` and
  drops heavy fields (full description / description_zh / install /
  bundled_in / tech_stack / install_method / source_url).
- ``search_text`` carries source provenance (source id, owner/repo, owner)
  so "search by source/author" (e.g. mattpocock) recalls every entry from
  that source, not just the name-matched ones.
- ``source`` is filled (non-empty) on every entry that has one in the catalog.
- Per-entry shards: id-hashed into a fixed bucket count, retrievable O(1) by
  id, carry the full Detail-facing field set, and the file count is bounded.
- The slim index is materially smaller than a full-field index baseline.
"""

import json
import pathlib
import sys

import pytest

sys.path.insert(
    0,
    str(pathlib.Path(__file__).resolve().parent.parent / "scripts"),
)

import build_frontend_data  # noqa: E402
from build_frontend_data import (  # noqa: E402
    ENTRY_SHARD_BUCKETS,
    build_entry_shards,
    build_search_entry,
    build_search_index,
    build_search_text,
    parse_owner_repo,
    shard_bucket,
    write_entry_shards,
)


# ---------------------------------------------------------------------------
# Fixtures / factories
# ---------------------------------------------------------------------------


def _entry(id, type_="skill", **extra):
    entry = {
        "id": id,
        "name": id,
        "type": type_,
        "description": f"{id} does a thing for engineering workflows.",
        "description_zh": f"{id} 中文描述",
        "source": "mattpocock/skills",
        "source_url": f"https://github.com/mattpocock/skills/tree/main/skills/{id}",
        "stars": 132000,
        "final_score": 70,
        "tags": ["engineering", "workflow"],
        "tech_stack": ["typescript"],
        "search_terms": ["skill router", "AI coding"],
        "install": {"method": "git_clone", "repo": "mattpocock/skills"},
        "freshness_label": "active",
    }
    entry.update(extra)
    return entry


def _read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def out_dir(tmp_path, monkeypatch):
    target = tmp_path / "api"
    target.mkdir()
    monkeypatch.setattr(build_frontend_data, "OUT", str(target))
    return target


# ---------------------------------------------------------------------------
# parse_owner_repo
# ---------------------------------------------------------------------------


def test_parse_owner_repo_basic():
    owner, repo = parse_owner_repo(
        "https://github.com/mattpocock/skills/tree/main/skills/ask-matt"
    )
    assert owner == "mattpocock"
    assert repo == "skills"


def test_parse_owner_repo_strips_git_suffix():
    owner, repo = parse_owner_repo("https://github.com/owner/repo.git")
    assert (owner, repo) == ("owner", "repo")


def test_parse_owner_repo_non_github_returns_none():
    assert parse_owner_repo("https://example.com/foo/bar") == (None, None)
    assert parse_owner_repo("") == (None, None)
    assert parse_owner_repo(None) == (None, None)


# ---------------------------------------------------------------------------
# search_text — source provenance recall
# ---------------------------------------------------------------------------


def test_search_text_includes_source_owner_repo_and_owner():
    item = _entry("ask-matt")
    text = build_search_text(item).lower()
    # source id, owner/repo, and bare owner all present for "search by source"
    assert "mattpocock/skills" in text
    assert "mattpocock" in text
    # tags + search_terms folded in for recall
    assert "engineering" in text
    assert "skill router" in text


def test_search_text_omits_full_description_and_name():
    """search_text must NOT duplicate name/description (those are separate
    indexed fields) — that duplication is what blew up the old 21MB index."""
    item = _entry(
        "ask-matt",
        name="ask-matt",
        description="A very long unique description sentinel token zzqqxx.",
    )
    text = build_search_text(item)
    assert "zzqqxx" not in text  # description not folded in
    # name appears only incidentally via source_url owner/repo, not duplicated
    assert "A very long unique description" not in text


def test_search_text_handles_missing_source_url():
    item = _entry("no-url", source_url="", source="curated")
    text = build_search_text(item)
    assert "curated" in text  # source id still present


def test_mattpocock_recall_across_whole_source():
    """The headline AC: searching the owner token recalls every entry from the
    source, including ones whose name does NOT contain the token."""
    items = [
        _entry("grilling", name="grilling"),
        _entry("handoff", name="handoff"),
        _entry("ask-matt", name="ask-matt"),
    ]
    index = build_search_index(items)
    # All three carry "mattpocock" in search_text via provenance, even though
    # only one name contains "matt".
    with_matt = [e for e in index if "mattpocock" in e["search_text"].lower()]
    assert len(with_matt) == 3
    name_with_matt = [e for e in index if "matt" in e["name"].lower()]
    assert len(name_with_matt) == 1  # naive name-only search would miss 2/3


# ---------------------------------------------------------------------------
# build_search_entry — slim card fields, heavy fields dropped
# ---------------------------------------------------------------------------


def test_search_entry_keeps_minimal_card_fields():
    entry = build_search_entry(_entry("ask-matt"))
    assert set(entry.keys()) == {
        "id",
        "name",
        "type",
        "source",
        "stars",
        "final_score",
        "freshness_label",
        "snippet",
        "search_text",
        "shard",
    }


def test_search_entry_drops_heavy_fields():
    entry = build_search_entry(_entry("ask-matt"))
    for heavy in (
        "description",
        "description_zh",
        "install",
        "install_method",
        "bundled_in",
        "tech_stack",
        "tags",
        "source_url",
        "category",
    ):
        assert heavy not in entry, f"{heavy} must not be in slim search entry"


def test_search_entry_source_non_empty():
    entry = build_search_entry(_entry("ask-matt"))
    assert entry["source"] == "mattpocock/skills"
    assert entry["source"]  # non-empty


def test_search_index_source_filled_for_all():
    items = [_entry(f"e{i}") for i in range(5)]
    index = build_search_index(items)
    assert all(e["source"] for e in index)


def test_search_entry_snippet_truncated():
    long_desc = "x" * 500
    entry = build_search_entry(_entry("long", description=long_desc))
    # Snippet is bounded (truncation marker appended when cut).
    assert len(entry["snippet"]) <= build_frontend_data.SNIPPET_MAX_CHARS + 1
    assert entry["snippet"].endswith("…")


def test_search_entry_freshness_falls_back_to_health():
    item = _entry("e", freshness_label=None, health={"freshness_label": "recent"})
    entry = build_search_entry(item)
    assert entry["freshness_label"] == "recent"


# ---------------------------------------------------------------------------
# shard field — frontend reads it directly (no client-side hashing)
# ---------------------------------------------------------------------------


def test_search_entry_carries_shard_matching_shard_bucket():
    """Each slim entry's ``shard`` must equal ``shard_bucket(id)`` so the
    frontend can fetch ``api/entries/<shard>.json`` without recomputing md5."""
    item = _entry("ask-matt")
    entry = build_search_entry(item)
    assert entry["shard"] == shard_bucket("ask-matt")
    assert isinstance(entry["shard"], int)
    assert 0 <= entry["shard"] < ENTRY_SHARD_BUCKETS


def test_search_entry_shard_locates_per_entry_file(out_dir):
    """The headline shard-contract invariant: the ``shard`` written into the
    slim search-index entry points at the per-entry shard file that actually
    contains that id. Mirror the client: read entry.shard → fetch that file →
    find the id."""
    items = [_entry(f"e{i}") for i in range(400)]
    index = build_search_index(items)
    write_entry_shards(items, str(out_dir))
    by_id = {e["id"]: e for e in index}
    # Spot-check several ids spread across the table.
    for target_id in ("e0", "e123", "e250", "e399"):
        shard_no = by_id[target_id]["shard"]
        shard = _read_json(out_dir / "entries" / f"{shard_no}.json")
        assert target_id in shard, (
            f"{target_id} not in shard {shard_no} its slim entry pointed at"
        )


def test_search_index_shard_consistent_across_all_entries(out_dir):
    """Every slim entry's shard must match where write_entry_shards placed it."""
    items = [_entry(f"e{i}") for i in range(200)]
    index = build_search_index(items)
    shards = write_entry_shards(items, str(out_dir))
    for entry in index:
        bucket = entry["shard"]
        assert entry["id"] in shards[bucket]


# ---------------------------------------------------------------------------
# per-entry shards
# ---------------------------------------------------------------------------


def test_shard_bucket_deterministic_and_bounded():
    b1 = shard_bucket("some-id")
    b2 = shard_bucket("some-id")
    assert b1 == b2
    assert 0 <= b1 < ENTRY_SHARD_BUCKETS


def test_build_entry_shards_round_trip_full_fields():
    items = [_entry(f"e{i}") for i in range(50)]
    shards = build_entry_shards(items)
    for item in items:
        bucket = shard_bucket(item["id"])
        assert item["id"] in shards[bucket]
        full = shards[bucket][item["id"]]
        # Full Detail-facing fields are present in the shard.
        assert full["description"]
        assert full["description_zh"]
        assert full["install"] is not None
        assert "tags" in full
        assert "tech_stack" in full


def test_write_entry_shards_file_count_bounded(out_dir):
    # Far more entries than buckets — file count must stay == buckets used,
    # never one-file-per-entry.
    items = [_entry(f"e{i}") for i in range(1000)]
    write_entry_shards(items, str(out_dir))
    entries_dir = out_dir / "entries"
    files = list(entries_dir.glob("*.json"))
    assert len(files) <= ENTRY_SHARD_BUCKETS
    assert len(files) < 1000  # NOT one file per entry


def test_write_entry_shards_retrievable_by_id(out_dir):
    items = [_entry(f"e{i}") for i in range(300)]
    write_entry_shards(items, str(out_dir))
    # Simulate the client: compute bucket from id, fetch that one file.
    target = items[123]
    bucket = shard_bucket(target["id"])
    shard = _read_json(out_dir / "entries" / f"{bucket}.json")
    assert target["id"] in shard
    assert shard[target["id"]]["name"] == target["name"]


def test_write_entry_shards_cleans_stale_files(out_dir):
    entries_dir = out_dir / "entries"
    entries_dir.mkdir()
    # A stale shard file from a previous run.
    (entries_dir / "999.json").write_text("{}", encoding="utf-8")
    write_entry_shards([_entry("only")], str(out_dir))
    assert not (entries_dir / "999.json").exists()


# ---------------------------------------------------------------------------
# size: slim index materially smaller than full-field baseline
# ---------------------------------------------------------------------------


def test_slim_index_smaller_than_full_field_baseline():
    """The slim entry must serialize materially smaller than a baseline that
    carries the heavy fields the refactor moved out."""
    items = [_entry(f"e{i}", description="d" * 400, description_zh="译" * 400)
             for i in range(200)]
    slim = build_search_index(items)
    slim_bytes = len(json.dumps(slim, ensure_ascii=False, separators=(",", ":")))

    # Baseline = old-style entry carrying full description/description_zh/
    # source_url/install/tech_stack etc.
    baseline = [
        {
            "id": i["id"],
            "name": i["name"],
            "type": i["type"],
            "category": i.get("category", "other"),
            "tags": i["tags"],
            "tech_stack": i["tech_stack"],
            "stars": i["stars"],
            "description": i["description"],
            "description_zh": i["description_zh"],
            "source_url": i["source_url"],
            "final_score": i["final_score"],
            "install": i["install"],
            "search_text": " ".join(
                [i["name"], i["description"], i["description_zh"]]
            ),
        }
        for i in items
    ]
    baseline_bytes = len(
        json.dumps(baseline, ensure_ascii=False, separators=(",", ":"))
    )
    # Slim should be well under half the baseline.
    assert slim_bytes < baseline_bytes * 0.5, (
        f"slim {slim_bytes} not < half of baseline {baseline_bytes}"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
