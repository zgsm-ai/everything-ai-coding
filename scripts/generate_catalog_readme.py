#!/usr/bin/env python3
"""Generate per-type catalog README files (Top 100) from catalog/index.json."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX_PATH = ROOT / "catalog" / "index.json"
GITHUB_PAGES_BASE = "https://zgsm-ai.github.io/everything-ai-coding/"
MAIN_README_REL = "../../README.md"

RESOURCE_TYPES = ("mcp", "skills", "rules", "prompts")

TOP_N = 100
FEATURED_N = 10
DESC_MAX_LEN = 80

# --- Source label mapping ---

SOURCE_LABELS = {
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

SOURCE_LABELS_ZH = {
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

# --- Type metadata ---

TYPE_META = {
    "mcp": {
        "emoji": "🔌",
        "title_en": "MCP Servers",
        "title_zh": "MCP 服务器",
        "desc_en": "Model Context Protocol servers that connect AI agents to external tools, databases, and services.",
        "desc_zh": "模型上下文协议服务器，将 AI Agent 连接到外部工具、数据库和服务。",
        "dir": "mcp",
    },
    "skill": {
        "emoji": "🎯",
        "title_en": "Skills",
        "title_zh": "Skills 技能",
        "desc_en": "Reusable agent capabilities and workflows for AI coding assistants.",
        "desc_zh": "AI 编程助手的可复用能力和工作流。",
        "dir": "skills",
    },
    "rule": {
        "emoji": "📋",
        "title_en": "Rules",
        "title_zh": "Rules 规则",
        "desc_en": "Coding conventions and AI behavior guidelines for consistent development.",
        "desc_zh": "编码规范和 AI 行为准则，确保开发一致性。",
        "dir": "rules",
    },
    "prompt": {
        "emoji": "💡",
        "title_en": "Prompts",
        "title_zh": "Prompts 提示词",
        "desc_en": "Developer-focused prompt templates for common coding tasks.",
        "desc_zh": "面向开发者的提示词模板，覆盖常见编码场景。",
        "dir": "prompts",
    },
}


# --- Helpers ---


def load_entries() -> list[dict]:
    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def sort_key(entry: dict) -> tuple:
    score = entry.get("final_score") or 0
    stars = entry.get("stars") or 0
    return (-score, -stars)


def format_stars(stars) -> str:
    if not stars:
        return "—"
    if stars >= 1000:
        return f"{stars / 1000:.1f}k"
    return str(stars)


def freshness_badge(entry: dict) -> str:
    health = entry.get("health") or {}
    label = health.get("freshness_label")
    has_date = bool(health.get("last_commit") or entry.get("pushed_at"))
    # "abandoned" with no date data means "unknown", not actually abandoned
    if label == "abandoned" and not has_date:
        return "—"
    return {"active": "🟢 Active", "stale": "🟡 Stale", "abandoned": "🔴 Abandoned"}.get(
        label or "", "—"
    )


def freshness_badge_zh(entry: dict) -> str:
    health = entry.get("health") or {}
    label = health.get("freshness_label")
    has_date = bool(health.get("last_commit") or entry.get("pushed_at"))
    if label == "abandoned" and not has_date:
        return "—"
    return {"active": "🟢 活跃", "stale": "🟡 停滞", "abandoned": "🔴 停更"}.get(
        label or "", "—"
    )


def truncate(text: str | None, max_len: int = DESC_MAX_LEN) -> str:
    if not text:
        return "—"
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def _is_placeholder_path(s: str) -> bool:
    """Detect placeholder/example paths like /path/to/x, /Users/username/..., path/to/..."""
    indicators = ("/path/", "path/to/", "/full/", "/Users/", "/opt/", "/home/", "ABSOLUTE/PATH")
    return any(ind in s for ind in indicators)


def install_summary(entry: dict) -> str:
    inst = entry.get("install") or {}
    method = inst.get("method", "manual")
    if method in ("mcp_config", "mcp_config_template"):
        config = inst.get("config") or {}
        cmd = config.get("command", "").strip()
        args = config.get("args") or []
        suffix = " ⚙️" if method == "mcp_config_template" else ""

        # Path-like or placeholder commands → See repo
        if _is_placeholder_path(cmd):
            return "📖 See repo"

        # Find the package name (first arg that's not a flag)
        pkg = ""
        for arg in args:
            if isinstance(arg, str) and not arg.startswith("-") and arg != "-y":
                pkg = arg
                break

        # If the package/arg is a placeholder path, fall back to See repo
        if pkg and _is_placeholder_path(pkg):
            return "📖 See repo"

        if cmd and pkg:
            return f"`{cmd} {pkg}`{suffix}"

        # Bare command with no args (e.g. cmd=mcp-maigret, args=[])
        # These are typically npx-able packages
        if cmd and not args and "/" not in cmd:
            return f"`npx {cmd}`{suffix}"

        if cmd:
            return f"`{cmd}`{suffix}"
        return "📖 See repo"
    if method == "git_clone":
        files = inst.get("files") or []
        if files:
            path = files[0].rstrip("/").split("/")[-1]
            return f"`git clone` → {path}/"
        return "`git clone`"
    if method == "download_file":
        return "📥 Download"
    return "📖 See repo"


def source_label(entry: dict, zh: bool = False) -> str:
    src = entry.get("source", "")
    labels = SOURCE_LABELS_ZH if zh else SOURCE_LABELS
    return labels.get(src, src)


def entry_link(entry: dict) -> str:
    url = entry.get("source_url", "")
    name = entry.get("name", entry.get("id", ""))
    if url:
        return f"[{name}]({url})"
    return name


def tags_str(entry: dict) -> str:
    tags = entry.get("tags") or []
    if not tags:
        return "—"
    return ", ".join(f"`{t}`" for t in tags[:3])


def last_active(entry: dict) -> str:
    health = entry.get("health") or {}
    dt = health.get("last_commit") or entry.get("pushed_at")
    if not dt:
        return "—"
    return dt[:10]


def install_details(entry: dict) -> str:
    """Full install details for <details> block."""
    inst = entry.get("install") or {}
    method = inst.get("method", "manual")

    if method in ("mcp_config", "mcp_config_template"):
        config = inst.get("config") or {}
        config_json = json.dumps(
            {"mcpServers": {entry.get("name", "server"): config}},
            indent=2,
            ensure_ascii=False,
        )
        note = ""
        if method == "mcp_config_template":
            env = config.get("env") or {}
            if env:
                placeholders = ", ".join(f"`{k}`" for k in list(env.keys())[:5])
                note = f"\n\n⚙️ Requires environment variables: {placeholders}"
        return f"**MCP Config**:\n```json\n{config_json}\n```{note}"

    if method == "git_clone":
        repo = inst.get("repo", "")
        files = inst.get("files") or []
        parts = [f"```bash\ngit clone {repo}\n```"]
        if files:
            parts.append(f"Files: `{', '.join(files)}`")
        return "\n".join(parts)

    if method == "download_file":
        files = inst.get("files") or []
        if files:
            links = "\n".join(f"- [{f.split('/')[-1]}]({f})" for f in files[:3])
            return f"**Download**:\n{links}"
        return "📥 Download from source repository"

    return f"📖 See [{entry.get('name', 'repository')}]({entry.get('source_url', '')})"


# --- Table renderers ---


def _has_enough_dates(entries: list[dict], threshold: float = 0.3) -> bool:
    """Check if enough entries have date data to warrant an Updated column."""
    if not entries:
        return False
    with_date = sum(1 for e in entries if last_active(e) != "—")
    return (with_date / len(entries)) >= threshold


def _render_table(entries: list[dict], zh: bool, has_stars: bool = False) -> str:
    """Unified table renderer for all types.

    All types get: #, Name, Description, Source/Stars, Status, Score, Updated (if data), Category, Tags.
    MCP uses Stars instead of Source.
    """
    show_updated = _has_enough_dates(entries)

    # Build header
    if has_stars:
        if zh:
            cols = ["#", "名称", "描述", "⭐ Stars", "状态", "评分"]
        else:
            cols = ["#", "Name", "Description", "⭐ Stars", "Status", "Score"]
    else:
        if zh:
            cols = ["#", "名称", "描述", "来源", "状态", "评分"]
        else:
            cols = ["#", "Name", "Description", "Source", "Status", "Score"]

    if show_updated:
        cols.append("最近更新" if zh else "Updated")
    cols.append("分类" if zh else "Category")
    cols.append("标签" if zh else "Tags")

    header = "| " + " | ".join(cols) + " |\n"
    sep = "|" + "|".join("---" for _ in cols) + "|\n"

    rows = []
    for i, e in enumerate(entries, 1):
        desc = truncate(e.get("description_zh") if zh else e.get("description"))
        status = freshness_badge_zh(e) if zh else freshness_badge(e)
        cat = e.get("category", "—") or "—"

        if has_stars:
            src_or_stars = format_stars(e.get("stars"))
        else:
            src_or_stars = source_label(e, zh)

        parts = [str(i), entry_link(e), desc, src_or_stars, status, str(e.get("final_score", "—"))]
        if show_updated:
            parts.append(last_active(e))
        parts.append(cat)
        parts.append(tags_str(e))

        rows.append("| " + " | ".join(parts) + " |")
    return header + sep + "\n".join(rows)


def render_mcp_table(entries: list[dict], zh: bool = False) -> str:
    return _render_table(entries, zh, has_stars=True)


def render_skill_table(entries: list[dict], zh: bool = False) -> str:
    return _render_table(entries, zh, has_stars=False)


def render_rule_table(entries: list[dict], zh: bool = False) -> str:
    return _render_table(entries, zh, has_stars=False)


def render_prompt_table(entries: list[dict], zh: bool = False) -> str:
    return _render_table(entries, zh, has_stars=False)


TABLE_RENDERERS = {
    "mcp": render_mcp_table,
    "skill": render_skill_table,
    "rule": render_rule_table,
    "prompt": render_prompt_table,
}


# --- Featured details ---


def render_featured_details(entries: list[dict], zh: bool = False) -> str:
    blocks = []
    for e in entries[:FEATURED_N]:
        name = e.get("name", e.get("id", ""))
        desc_full = (e.get("description_zh") if zh else e.get("description")) or ""
        stars_str = f" ({format_stars(e.get('stars'))}★)" if e.get("stars") else ""
        url = e.get("source_url", "")
        score = e.get("final_score", "—")
        health_score = (e.get("health") or {}).get("score", "—")
        src = source_label(e, zh)
        active = last_active(e)
        tags = tags_str(e)
        install_detail = install_details(e)

        summary_label = "详情" if zh else "Details"
        score_label = "评分" if zh else "Score"
        health_label = "健康度" if zh else "Health"
        tags_label = "标签" if zh else "Tags"
        source_label_text = "来源" if zh else "Source"
        active_label = "最近活跃" if zh else "Last active"

        block = f"""<details>
<summary>⭐ <strong>{name}</strong>{stars_str} — {truncate(desc_full, 60)}</summary>

{desc_full}

{install_detail}

📊 {score_label}: {score} · 🏥 {health_label}: {health_score} · 🏷️ {tags_label}: {tags}
📅 {active_label}: {active} · 📦 {source_label_text}: {src}

</details>"""
        blocks.append(block)
    return "\n\n".join(blocks)


# --- Full README generation ---


def generate_readme(type_key: str, entries: list[dict], zh: bool = False) -> str:
    meta = TYPE_META[type_key]
    title = meta["title_zh"] if zh else meta["title_en"]
    desc = meta["desc_zh"] if zh else meta["desc_en"]
    emoji = meta["emoji"]
    total = len([e for e in load_entries() if e.get("type") == type_key])
    browse_url = f"{GITHUB_PAGES_BASE}#/browse?type={type_key}"

    # Language toggle
    if zh:
        lang_toggle = "[English](./README.md) · **简体中文**"
    else:
        lang_toggle = "**English** · [简体中文](./README.zh-CN.md)"

    # Header
    header_text = "精选" if zh else "Top"
    browse_text = "在线浏览" if zh else "Browse interactively"
    back_text = "返回主页" if zh else "Back to main"
    auto_gen = "自动生成" if zh else "Auto-generated from"
    last_updated = "最后更新" if zh else "Last updated"
    featured_title = "Top 10 安装指南" if zh else "Top 10 — Install Guide"
    scoring_title = "评分方法" if zh else "Scoring Methodology"

    top_entries = sorted(entries, key=sort_key)[:TOP_N]
    table = TABLE_RENDERERS[type_key](top_entries, zh)
    featured = render_featured_details(top_entries, zh)

    if zh:
        scoring_body = """资源按综合评分（0-100）排名，综合以下维度：
- **编码相关性**（1-5）— 对开发的直接帮助程度
- **内容质量**（1-5）— 文档、维护、完整性
- **来源可信度**（1-5）— 上游声誉
- **社区信号** — Stars、活跃度、可安装性"""
    else:
        scoring_body = """Resources are ranked by a composite score (0-100) combining:
- **Coding relevance** (1-5) — How directly useful for development
- **Content quality** (1-5) — Documentation, maintenance, completeness
- **Source trust** (1-5) — Upstream reputation
- **Community signals** — Stars, freshness, installability"""

    return f"""# {emoji} {title}

> {total} {desc}
>
> [{back_text} →]({MAIN_README_REL}) · [{browse_text} →]({browse_url})

{lang_toggle}

## {header_text} {TOP_N}

{table}

## {featured_title}

{featured}

---

## {scoring_title}

{scoring_body}

---

*{auto_gen} [catalog/index.json](../index.json). {last_updated}: {date.today().isoformat()}*
"""


def main() -> None:
    all_entries = load_entries()

    # Group by type
    by_type: dict[str, list[dict]] = {}
    for entry in all_entries:
        t = entry.get("type")
        if t:
            by_type.setdefault(t, []).append(entry)

    generated = []
    for type_key, meta in TYPE_META.items():
        entries = by_type.get(type_key, [])
        if not entries:
            print(f"WARNING: No entries for type '{type_key}', skipping")
            continue

        out_dir = ROOT / "catalog" / meta["dir"]
        out_dir.mkdir(parents=True, exist_ok=True)

        # English
        en_path = out_dir / "README.md"
        en_path.write_text(generate_readme(type_key, entries, zh=False), encoding="utf-8")
        generated.append(en_path)

        # Chinese
        zh_path = out_dir / "README.zh-CN.md"
        zh_path.write_text(generate_readme(type_key, entries, zh=True), encoding="utf-8")
        generated.append(zh_path)

    print(f"Generated {len(generated)} catalog README files:")
    for p in generated:
        print(f"  {p.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
