#!/usr/bin/env python3

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Literal, TypeAlias

Language: TypeAlias = Literal["en", "zh"]
CatalogEntry: TypeAlias = dict[str, object]
SceneDefinition: TypeAlias = tuple[str, dict[Language, str], list[str]]

ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = ROOT / "catalog" / "index.json"
FEATURED_OUTPUTS: dict[Language, Path] = {
    "en": ROOT / "catalog" / "featured.md",
    "zh": ROOT / "catalog" / "featured.zh-CN.md",
}

TYPE_EMOJI: dict[str, str] = {
    "mcp": "🔌",
    "skill": "🎯",
    "rule": "📋",
    "prompt": "💡",
}

SCENE_CATEGORIES: list[SceneDefinition] = [
    (
        "browser",
        {"en": "🌐 Browser & Automation", "zh": "🌐 浏览器与自动化"},
        [
            "playwright",
            "puppeteer",
            "selenium",
            "automation",
            "browser",
            "scraping",
            "crawl",
            "web-scraping",
            "e2e",
            "scraper",
        ],
    ),
    (
        "git",
        {"en": "🐙 Git & Collaboration", "zh": "🐙 Git 与协作"},
        ["git", "github", "gitlab", "version-control"],
    ),
    (
        "devops",
        {"en": "🚀 DevOps & Security", "zh": "🚀 DevOps 与安全"},
        [
            "docker",
            "kubernetes",
            "k8s",
            "ci",
            "cd",
            "deploy",
            "terraform",
            "aws",
            "gcp",
            "azure",
            "cloud",
            "nginx",
            "linux",
            "devops",
            "security",
            "auth",
            "oauth",
            "owasp",
            "audit",
            "cloudflare",
            "monitoring",
            "logging",
        ],
    ),
    (
        "docs",
        {"en": "📚 Documentation & Knowledge", "zh": "📚 文档与知识"},
        [
            "documentation",
            "markdown",
            "knowledge",
            "rag",
            "memory",
            "docs",
            "markitdown",
            "technical-writing",
        ],
    ),
    (
        "frontend",
        {"en": "🎨 Frontend & Design", "zh": "🎨 前端与设计"},
        [
            "react",
            "vue",
            "angular",
            "svelte",
            "nextjs",
            "next.js",
            "tailwind",
            "css",
            "ui",
            "figma",
            "design",
            "frontend",
            "html",
            "shadcn",
        ],
    ),
    (
        "backend",
        {"en": "⚙️ Backend & Databases", "zh": "⚙️ 后端与数据库"},
        [
            "fastapi",
            "django",
            "flask",
            "express",
            "nestjs",
            "spring",
            "backend",
            "microservice",
            "postgres",
            "mysql",
            "mongodb",
            "redis",
            "sqlite",
            "database",
            "sql",
            "supabase",
            "pydantic",
        ],
    ),
    (
        "ai",
        {"en": "🤖 AI & MCP Development", "zh": "🤖 AI 与 MCP 开发"},
        [
            "llm",
            "langchain",
            "openai",
            "anthropic",
            "claude",
            "agent",
            "mcp",
            "embedding",
            "vector",
            "blender",
            "3d",
            "ai",
            "ml",
            "deep-learning",
        ],
    ),
]

SOURCE_LABELS: dict[Language, dict[str, str]] = {
    "en": {
        "anthropics-skills": "Anthropic official",
        "ai-agent-skills": "Community curated",
        "curated": "Curated",
        "rules-2.1-optimized": "Rules 2.1",
        "awesome-cursorrules": "CursorRules",
        "prompts-chat": "prompts.chat",
        "wonderful-prompts": "wonderful-prompts",
    },
    "zh": {
        "anthropics-skills": "Anthropic 官方",
        "ai-agent-skills": "社区精选",
        "curated": "精选",
        "rules-2.1-optimized": "Rules 2.1",
        "awesome-cursorrules": "CursorRules",
        "prompts-chat": "prompts.chat",
        "wonderful-prompts": "wonderful-prompts",
    },
}

LANGUAGE_CONFIG: dict[Language, dict[str, str]] = {
    "en": {
        "title": "## ⭐ Featured Picks",
        "intro": (
            "> Curated by use case from {total}+ resources. After installation, use "
            "`/coding-hub:search` to explore the full index or `/coding-hub:recommend` "
            "for project-aware suggestions."
        ),
        "legend": "> Legend: 🔌 MCP Server · 🎯 Skill · 📋 Rule · 💡 Prompt",
    },
    "zh": {
        "title": "## ⭐ 精选推荐",
        "intro": (
            "> 从 {total}+ 资源中按使用场景精选。安装后可使用 `/coding-hub:search` "
            "搜索完整索引，或通过 `/coding-hub:recommend` 获取项目级推荐。"
        ),
        "legend": "> 图例：🔌 MCP Server · 🎯 Skill · 📋 Rule · 💡 Prompt",
    },
}


def load_catalog(catalog_path: Path = CATALOG_PATH) -> list[CatalogEntry]:
    with open(catalog_path, "r", encoding="utf-8") as f:
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


def format_stars(stars: int | None) -> str | None:
    if stars is None:
        return None
    if stars >= 1000:
        return f"{stars / 1000:.1f}k"
    return str(stars)


def trunc(text: str, limit: int = 80) -> str:
    if len(text) <= limit:
        return text

    cut = text[:limit]
    if ord(cut[-1]) > 127:
        return cut.rstrip("。，、；：！？") + "…"

    last_space = cut.rfind(" ")
    if last_space > limit * 0.6:
        return cut[:last_space] + "…"
    return cut + "…"


def extract_repo_key(url: str) -> str:
    match = re.match(r"https://github\.com/([^/]+/[^/]+)", url)
    return match.group(1) if match else url


def get_text(item: CatalogEntry, key: str) -> str:
    value = item.get(key, "")
    return value if isinstance(value, str) else ""


def get_tags(item: CatalogEntry) -> list[str]:
    value = item.get("tags", [])
    if not isinstance(value, list):
        return []
    return [tag for tag in value if isinstance(tag, str)]


def get_optional_int(item: CatalogEntry, key: str) -> int | None:
    value = item.get(key)
    return value if isinstance(value, int) else None


def get_reason(item: CatalogEntry) -> str:
    evaluation = item.get("evaluation")
    if not isinstance(evaluation, dict):
        return ""
    reason = evaluation.get("reason") if "reason" in evaluation else None
    return reason if isinstance(reason, str) else ""


def classify_item(item: CatalogEntry) -> str | None:
    tags = {tag.lower() for tag in get_tags(item)}
    name_lower = get_text(item, "name").lower()
    desc_lower = get_text(item, "description").lower()[:200]
    category = get_text(item, "category").lower()

    category_hint = {
        "automation": "browser",
        "browser": "browser",
        "git": "git",
        "github": "git",
        "devops": "devops",
        "security": "devops",
        "documentation": "docs",
        "frontend": "frontend",
        "backend": "backend",
        "database": "backend",
        "ai-ml": "ai",
        "testing": None,
        "tooling": "ai",
    }.get(category)

    for scene_key, _, keywords in SCENE_CATEGORIES:
        for keyword in keywords:
            if keyword in tags or keyword in name_lower:
                return scene_key
            if re.search(rf"\b{re.escape(keyword)}\b", desc_lower):
                return scene_key

    return category_hint


def get_source_label(item: CatalogEntry, lang: Language) -> str:
    source = get_text(item, "source")
    return SOURCE_LABELS[lang].get(source, source)


def get_description(item: CatalogEntry, lang: Language) -> str:
    if lang == "zh":
        return get_text(item, "description_zh") or get_text(item, "description")

    description = get_text(item, "description")
    if re.search(r"[\u4e00-\u9fff]", description):
        reason = get_reason(item).strip()
        if reason:
            return reason.strip()
    return description or get_text(item, "description_zh")


def select_top_items(catalog: list[CatalogEntry]) -> dict[str, list[CatalogEntry]]:
    by_type: dict[str, list[CatalogEntry]] = defaultdict(list)
    for item in catalog:
        entry_type = get_text(item, "type")
        if entry_type:
            by_type[entry_type].append(item)

    mcp_items = sorted(
        [item for item in by_type["mcp"] if (get_optional_int(item, "stars") or 0) > 0],
        key=lambda item: get_optional_int(item, "stars") or 0,
        reverse=True,
    )

    skill_priority = {"curated": 0, "anthropics-skills": 1, "ai-agent-skills": 2}
    skill_items = sorted(
        by_type["skill"],
        key=lambda item: (
            skill_priority.get(get_text(item, "source"), 99),
            get_text(item, "name"),
        ),
    )

    rule_priority = {"curated": 0, "rules-2.1-optimized": 1, "awesome-cursorrules": 2}
    rule_items = sorted(
        by_type["rule"],
        key=lambda item: (
            rule_priority.get(get_text(item, "source"), 99),
            -len(get_tags(item)),
        ),
    )

    prompt_priority = {"curated": 0, "wonderful-prompts": 1, "prompts-chat": 2}
    prompt_items = sorted(
        by_type["prompt"],
        key=lambda item: (
            prompt_priority.get(get_text(item, "source"), 99),
            get_text(item, "name"),
        ),
    )

    scene_items: dict[str, list[CatalogEntry]] = defaultdict(list)
    seen_repos: set[str] = set()

    mcp_per_scene = 4
    for item in mcp_items:
        scene = classify_item(item)
        if scene is None:
            continue
        repo_key = extract_repo_key(get_text(item, "source_url"))
        if repo_key in seen_repos:
            continue
        if (
            len(
                [
                    entry
                    for entry in scene_items[scene]
                    if get_text(entry, "type") == "mcp"
                ]
            )
            >= mcp_per_scene
        ):
            continue
        seen_repos.add(repo_key)
        scene_items[scene].append(item)

    for items, max_per_scene in ((skill_items, 2), (rule_items, 2), (prompt_items, 1)):
        scene_count: Counter[str] = Counter()
        for item in items:
            scene = classify_item(item)
            if scene is None:
                continue
            if scene_count[scene] >= max_per_scene:
                continue
            name_key = get_text(item, "name").lower()
            if name_key in seen_repos:
                continue
            seen_repos.add(name_key)
            scene_count[scene] += 1
            scene_items[scene].append(item)

    return scene_items


def render_bullet(item: CatalogEntry, lang: Language) -> str:
    entry_type = get_text(item, "type")
    emoji = TYPE_EMOJI.get(entry_type, "📦")
    name = get_text(item, "name")
    url = get_text(item, "source_url")
    desc = trunc(get_description(item, lang), 70)

    stars = get_optional_int(item, "stars")
    if entry_type == "mcp" and stars:
        tail = f"⭐ {format_stars(stars)}"
    else:
        tail = f"`{get_source_label(item, lang)}`"

    return f"- {emoji} **[{name}]({url})** — {desc} {tail}"


def generate_featured_section(
    lang: Language = "en", catalog: list[CatalogEntry] | None = None
) -> str:
    if lang not in LANGUAGE_CONFIG:
        raise ValueError(f"Unsupported language: {lang}")

    catalog_entries = catalog if catalog is not None else load_catalog()
    scene_items = select_top_items(catalog_entries)
    total = len(catalog_entries)
    config = LANGUAGE_CONFIG[lang]

    lines = [config["title"], "", config["intro"].format(total=total), ""]

    for scene_key, labels, _ in SCENE_CATEGORIES:
        items = scene_items.get(scene_key, [])
        if not items:
            continue
        lines.append(f"### {labels[lang]}")
        lines.append("")
        for item in items:
            lines.append(render_bullet(item, lang))
        lines.append("")

    lines.append(config["legend"])
    lines.append("")
    return "\n".join(lines)


def write_featured_sections(
    catalog: list[CatalogEntry] | None = None,
) -> dict[Language, Path]:
    catalog_entries = catalog if catalog is not None else load_catalog()
    written_paths: dict[Language, Path] = {}

    for lang, output_path in FEATURED_OUTPUTS.items():
        _ = output_path.write_text(
            generate_featured_section(lang=lang, catalog=catalog_entries),
            encoding="utf-8",
        )
        written_paths[lang] = output_path

    return written_paths


def main() -> None:
    written_paths = write_featured_sections()
    for lang, path in written_paths.items():
        print(f"Generated {lang} featured section: {path}")


if __name__ == "__main__":
    main()
