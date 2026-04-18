#!/usr/bin/env python3

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path
from typing import TypeAlias

CatalogEntry: TypeAlias = dict[str, object]

ROOT = Path(__file__).resolve().parent.parent
INDEX_PATH = ROOT / "catalog" / "index.json"
RESOURCE_BADGE_PATTERN = re.compile(r"resources-\d+-2ECC71")

COUNT_MARKERS: dict[str, str] = {
    "approx": "README_APPROX_COUNT",
    "mcp": "README_COUNT_MCP",
    "prompt": "README_COUNT_PROMPT",
    "rule": "README_COUNT_RULE",
    "skill": "README_COUNT_SKILL",
}

TOP5_MARKERS: dict[str, str] = {
    "mcp": "README_TOP5_MCP",
    "skill": "README_TOP5_SKILL",
    "rule": "README_TOP5_RULE",
    "prompt": "README_TOP5_PROMPT",
}

TOP5_LIMIT = 5
TOP5_DESC_MAX = 70

SOURCE_LABELS_EN: dict[str, str] = {
    "anthropics-skills": "Anthropic Official",
    "anthropics/claude-code": "Anthropic Official",
    "ai-agent-skills": "Community Curated",
    "antigravity-skills": "Antigravity Skills",
    "vasilyu-skills": "Vasilyu Skills",
    "awesome-mcp-servers": "Awesome MCP",
    "awesome-mcp-zh": "Awesome MCP ZH",
    "mcp.so": "mcp.so",
    "awesome-cursorrules": "CursorRules",
    "rules-2.1-optimized": "Rules 2.1",
    "prompts-chat": "prompts.chat",
    "wonderful-prompts": "wonderful-prompts",
    "davila7/claude-code-templates": "Claude Code Templates",
    "curated": "Curated",
}

SOURCE_LABELS_ZH: dict[str, str] = {
    "anthropics-skills": "Anthropic 官方",
    "anthropics/claude-code": "Anthropic 官方",
    "ai-agent-skills": "社区精选",
    "antigravity-skills": "Antigravity Skills",
    "vasilyu-skills": "Vasilyu Skills",
    "awesome-mcp-servers": "Awesome MCP",
    "awesome-mcp-zh": "Awesome MCP 中文",
    "mcp.so": "mcp.so",
    "awesome-cursorrules": "CursorRules",
    "rules-2.1-optimized": "Rules 2.1",
    "prompts-chat": "prompts.chat",
    "wonderful-prompts": "精彩提示词",
    "davila7/claude-code-templates": "Claude Code 模板",
    "curated": "手工精选",
}

README_PATHS: tuple[Path, ...] = (
    ROOT / "README.md",
    ROOT / "README.zh-CN.md",
)


def load_entries(index_path: Path = INDEX_PATH) -> list[CatalogEntry]:
    with open(index_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        return []

    entries: list[CatalogEntry] = []
    for raw_entry in data:
        if not isinstance(raw_entry, dict):
            continue
        entry: CatalogEntry = {}
        for key, value in raw_entry.items():
            if isinstance(key, str):
                entry[key] = value
        entries.append(entry)
    return entries


def compute_stats(entries: list[CatalogEntry]) -> dict[str, int]:
    total = len(entries)
    approx = math.floor(total / 100) * 100
    by_type: dict[str, int] = {"mcp": 0, "prompt": 0, "rule": 0, "skill": 0}

    for entry in entries:
        entry_type_value = entry.get("type")
        if isinstance(entry_type_value, str) and entry_type_value in by_type:
            by_type[entry_type_value] += 1

    return {"total": total, "approx": approx, **by_type}


def _format_stars(stars: object) -> str:
    if not isinstance(stars, (int, float)) or stars <= 0:
        return "—"
    if stars >= 1000:
        return f"{stars / 1000:.1f}k"
    return str(int(stars))


def _truncate(text: object, limit: int = TOP5_DESC_MAX) -> str:
    if not isinstance(text, str) or not text:
        return "—"
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: max(0, limit - 1)].rstrip() + "…"


def _source_label(entry: CatalogEntry, zh: bool) -> str:
    src = entry.get("source")
    if not isinstance(src, str) or not src:
        return "—"
    labels = SOURCE_LABELS_ZH if zh else SOURCE_LABELS_EN
    return labels.get(src, src)


def _entry_link(entry: CatalogEntry) -> str:
    url = entry.get("source_url")
    name = entry.get("name") or entry.get("id") or "—"
    if isinstance(url, str) and url:
        return f"[{name}]({url})"
    return str(name)


def _select_top5(entries: list[CatalogEntry], type_: str) -> list[CatalogEntry]:
    candidates: list[CatalogEntry] = []
    for entry in entries:
        if entry.get("type") != type_:
            continue
        freshness = entry.get("freshness_label") or "active"
        if freshness == "abandoned":
            continue
        candidates.append(entry)

    def sort_key(e: CatalogEntry) -> tuple[float, int]:
        score_raw = e.get("final_score")
        score = float(score_raw) if isinstance(score_raw, (int, float)) else 0.0
        stars_raw = e.get("stars")
        stars = int(stars_raw) if isinstance(stars_raw, (int, float)) else 0
        return (score, stars)

    candidates.sort(key=sort_key, reverse=True)
    return candidates[:TOP5_LIMIT]


def _render_top5_table(entries: list[CatalogEntry], type_: str, zh: bool) -> str:
    items = _select_top5(entries, type_)
    if not items:
        return ""

    if type_ == "mcp":
        if zh:
            header = "| 名称 | ⭐ Stars | 评分 | 描述 |"
            sep = "|------|----------|------|------|"
        else:
            header = "| Name | ⭐ Stars | Score | Description |"
            sep = "|------|----------|-------|-------------|"
    elif type_ == "skill":
        if zh:
            header = "| 名称 | 来源 | 评分 | 描述 |"
            sep = "|------|------|------|------|"
        else:
            header = "| Name | Source | Score | Description |"
            sep = "|------|--------|-------|-------------|"
    else:
        if zh:
            header = "| 名称 | 来源 | 评分 | 分类 |"
            sep = "|------|------|------|------|"
        else:
            header = "| Name | Source | Score | Category |"
            sep = "|------|--------|-------|----------|"

    rows: list[str] = []
    for entry in items:
        name = _entry_link(entry)
        score_raw = entry.get("final_score")
        score_cell = str(round(score_raw)) if isinstance(score_raw, (int, float)) else "—"
        desc_source = entry.get("description_zh") if zh else entry.get("description")
        desc_cell = _truncate(desc_source)
        category = entry.get("category")
        cat_cell = category if isinstance(category, str) and category else "—"

        if type_ == "mcp":
            stars_cell = _format_stars(entry.get("stars"))
            rows.append(f"| {name} | {stars_cell} | {score_cell} | {desc_cell} |")
        elif type_ == "skill":
            source_cell = _source_label(entry, zh)
            rows.append(f"| {name} | {source_cell} | {score_cell} | {desc_cell} |")
        else:
            source_cell = _source_label(entry, zh)
            rows.append(f"| {name} | {source_cell} | {score_cell} | {cat_cell} |")

    return "\n".join([header, sep, *rows])


def _replace_between_markers(content: str, marker_name: str, replacement: str) -> str:
    start = f"<!-- {marker_name}:START -->"
    end = f"<!-- {marker_name}:END -->"
    pattern = re.compile(rf"({re.escape(start)})(.*?)({re.escape(end)})", re.DOTALL)

    if not pattern.search(content):
        raise ValueError(f"Marker pair not found: {marker_name}")

    return pattern.sub(
        lambda match: f"{match.group(1)}{replacement}{match.group(3)}", content, count=1
    )


def update_single_readme(
    readme_path: Path,
    stats: dict[str, int],
    entries: list[CatalogEntry],
) -> bool:
    content = readme_path.read_text(encoding="utf-8")
    original = content
    zh = "zh-CN" in readme_path.name

    content = _replace_between_markers(
        content, COUNT_MARKERS["approx"], str(stats["approx"])
    )
    for key in ("mcp", "prompt", "rule", "skill"):
        content = _replace_between_markers(content, COUNT_MARKERS[key], str(stats[key]))

    content = RESOURCE_BADGE_PATTERN.sub(f"resources-{stats['total']}-2ECC71", content)

    for type_, marker in TOP5_MARKERS.items():
        if f"<!-- {marker}:START -->" not in content:
            continue
        table = _render_top5_table(entries, type_, zh)
        content = _replace_between_markers(content, marker, f"\n{table}\n")

    if content != original:
        _ = readme_path.write_text(content, encoding="utf-8")
        return True
    return False


def update_readmes(
    index_path: Path = INDEX_PATH, readme_paths: tuple[Path, ...] = README_PATHS
) -> list[Path]:
    entries = load_entries(index_path=index_path)
    stats = compute_stats(entries)
    updated_paths: list[Path] = []

    for readme_path in readme_paths:
        if update_single_readme(readme_path, stats, entries):
            updated_paths.append(readme_path)

    return updated_paths


def main() -> None:
    updated_paths = update_readmes()

    if updated_paths:
        print("README files updated:")
        for path in updated_paths:
            print(f"- {path.relative_to(ROOT)}")
    else:
        print("README files already up to date")


if __name__ == "__main__":
    main()
