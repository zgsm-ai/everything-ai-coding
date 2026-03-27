#!/usr/bin/env python3
"""从 catalog/index.json 生成按技术栈分类的精选推荐（方案C：混合展示）。

MCP:    前5详细展开 + 其余按技术栈折叠
Skills: 前3详细展开 + 其余按技术栈折叠
Rules:  按技术栈折叠表格
Prompts: 按技术栈折叠表格
"""

import json
import re
from pathlib import Path
from datetime import datetime
from collections import defaultdict, Counter


def load_catalog():
    catalog_path = Path(__file__).parent.parent / "catalog" / "index.json"
    with open(catalog_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def format_stars(stars):
    if stars >= 1000:
        return f"{stars/1000:.1f}k"
    return str(stars)


def format_date(date_str):
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime('%Y-%m')
    except Exception:
        return date_str[:7]


def trunc(text, n=80):
    return text if len(text) <= n else text[:n - 3] + "..."


def extract_repo_key(url):
    """提取 org/repo 作为去重 key。
    对 monorepo（同一仓库的不同子目录）也只保留一个代表。
    """
    m = re.match(r'https://github\.com/([^/]+/[^/]+)', url)
    return m.group(1) if m else url


# ── 技术栈分类 ──────────────────────────────────────────

TECH_CATEGORIES = [
    # 顺序决定匹配优先级：更具体的分类放前面
    ('security',   '🔒 安全',       ['security', 'auth', 'oauth', 'jwt', 'encryption', 'owasp', 'audit', 'vulnerability', 'pentesting']),
    ('mobile',     '📱 移动开发',   ['ios', 'android', 'flutter', 'react-native', 'swift', 'kotlin', 'mobile', 'dart']),
    ('docs',       '📝 文档 / 写作', ['documentation', 'markdown', 'technical-writing', 'api-docs', 'readme', 'writing']),
    ('database',   '🗄️ 数据库',    ['postgres', 'mysql', 'mongodb', 'redis', 'sqlite', 'database', 'sql', 'nosql', 'supabase', 'firebase', 'dynamodb', 'cassandra', 'elasticsearch']),
    ('automation', '🔧 自动化 / 浏览器', ['playwright', 'puppeteer', 'selenium', 'automation', 'browser', 'scraping', 'crawl', 'web-scraping', 'e2e']),
    ('git',        '🐙 Git / GitHub', ['git', 'github', 'gitlab', 'version-control']),
    ('ai-ml',      '🤖 AI / ML',   ['llm', 'rag', 'langchain', 'llamaindex', 'transformers', 'gradio', 'openai', 'anthropic', 'huggingface', 'embedding', 'vector', 'gpt', 'claude', 'deepseek']),
    ('devops',     '🚀 DevOps / CI', ['docker', 'kubernetes', 'k8s', 'ci', 'cd', 'deploy', 'terraform', 'ansible', 'aws', 'gcp', 'azure', 'cloud', 'nginx', 'linux', 'shell', 'devops', 'monitoring']),
    ('frontend',   '🎨 前端开发',  ['react', 'vue', 'angular', 'svelte', 'nextjs', 'next.js', 'tailwind', 'css', 'ui', 'shadcn', 'typescript', 'javascript', 'frontend', 'html', 'sass', 'less', 'webpack', 'vite', 'electron']),
    ('backend',    '⚙️ 后端开发',  ['python', 'go', 'golang', 'java', 'rust', 'c#', 'dotnet', '.net', 'ruby', 'php', 'spring', 'django', 'flask', 'fastapi', 'express', 'nestjs', 'api', 'backend', 'server', 'microservice', 'nodejs', 'node.js']),
    ('other',      '🛠️ 其他工具',   []),
]


def classify_item(item):
    """返回 item 匹配到的第一个技术栈分类 key"""
    tags = set(t.lower() for t in item.get('tags', []))
    name_lower = item['name'].lower()
    desc_lower = item['description'].lower()[:200]

    for cat_key, _, keywords in TECH_CATEGORIES:
        if cat_key == 'other':
            continue
        for kw in keywords:
            if kw in tags or kw in name_lower or kw in desc_lower:
                return cat_key
    return 'other'


def group_by_tech(items):
    groups = defaultdict(list)
    for item in items:
        groups[classify_item(item)].append(item)
    return groups


# ── 选择策略 ──────────────────────────────────────────

def select_mcp_top(items, top_n=5):
    """Top N：严格按 org/repo 去重，确保多样性"""
    items = sorted(items, key=lambda x: x['stars'] or 0, reverse=True)
    seen = set()
    result = []
    for item in items:
        key = extract_repo_key(item['source_url'])
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
        if len(result) >= top_n:
            break
    return result


def select_mcp_rest(items, exclude_ids, top_n=30):
    """其余：允许同 monorepo 不同子项目，但每个 repo 最多 3 个"""
    items = sorted(items, key=lambda x: x['stars'] or 0, reverse=True)
    repo_count = Counter()
    result = []
    for item in items:
        if item['id'] in exclude_ids:
            continue
        key = extract_repo_key(item['source_url'])
        if repo_count[key] >= 3:
            continue
        repo_count[key] += 1
        result.append(item)
        if len(result) >= top_n:
            break
    return result


def select_skills(items, top_n=12):
    priority = {
        'curated': 0, 'anthropics-skills': 1, 'huggingface/skills': 2,
        'nextlevelbuilder/ui-ux-pro-max-skill': 3,
        'ai-agent-skills': 4, 'davila7/claude-code-templates': 5,
    }
    items = sorted(items, key=lambda x: (priority.get(x['source'], 99), -(x['stars'] or 0)))
    count = Counter()
    result = []
    for item in items:
        if count[item['source']] >= 4:
            continue
        count[item['source']] += 1
        result.append(item)
        if len(result) >= top_n:
            break
    return result


def select_rules(items, top_n=15):
    priority = {'curated': 0, 'rules-2.1-optimized': 1, 'awesome-cursorrules': 2}
    items = sorted(items, key=lambda x: (priority.get(x['source'], 99), -len(x.get('tags', []))))
    return items[:top_n]


def select_prompts(items, top_n=15):
    coding_tags = {
        'for-devs', 'python', 'javascript', 'typescript', 'java', 'golang',
        'rust', 'react', 'vue', 'angular', 'nodejs', 'fullstack', 'frontend',
        'backend', 'database', 'sql', 'docker', 'kubernetes', 'devops', 'git',
        'linux', 'shell', 'chinese',
    }
    priority = {'curated': 0, 'wonderful-prompts': 1, 'prompts-chat': 2}

    filtered = []
    for item in items:
        if item['source'] == 'prompts-chat':
            if not (set(t.lower() for t in item.get('tags', [])) & coding_tags):
                continue
        filtered.append(item)

    filtered.sort(key=lambda x: priority.get(x['source'], 99))
    seen = set()
    result = []
    for item in filtered:
        if item['name'] in seen:
            continue
        seen.add(item['name'])
        result.append(item)
        if len(result) >= top_n:
            break
    return result


# ── 渲染模块 ──────────────────────────────────────────

def render_detailed(items, show_stars=True):
    """详细卡片式展示"""
    lines = []
    for i, item in enumerate(items, 1):
        date = format_date(item['last_synced'])
        tags = ' '.join(f"`{t}`" for t in item['tags'][:3])

        lines.append(f"**{i}. [{item['name']}]({item['source_url']})**")
        lines.append("")
        lines.append(f"> {trunc(item['description'], 120)}")
        lines.append("")
        if show_stars:
            stars = format_stars(item['stars'])
            lines.append(f"⭐ **{stars}** · 📅 {date}{' · ' + tags if tags else ''}")
        else:
            lines.append(f"📅 {date}{' · ' + tags if tags else ''}")
        lines.append("")
    return '\n'.join(lines)


def render_table(items, show_stars=True):
    """表格展示"""
    lines = []
    if show_stars:
        lines.append("| 名称 | 描述 | ⭐ Stars | 标签 |")
        lines.append("|------|------|---------|------|")
    else:
        lines.append("| 名称 | 描述 | 来源 | 标签 |")
        lines.append("|------|------|------|------|")

    for item in items:
        name = f"[{item['name']}]({item['source_url']})"
        desc = trunc(item['description'], 70)
        tags = ' '.join(f"`{t}`" for t in item['tags'][:3])

        if show_stars:
            lines.append(f"| {name} | {desc} | {format_stars(item['stars'])} | {tags} |")
        else:
            lines.append(f"| {name} | {desc} | {item.get('source', '')} | {tags} |")

    return '\n'.join(lines)


def render_tech_groups(groups, show_stars=True):
    """按技术栈折叠展示"""
    lines = []
    for cat_key, cat_name, _ in TECH_CATEGORIES:
        cat_items = groups.get(cat_key, [])
        if not cat_items:
            continue

        lines.append("<details>")
        lines.append(f"<summary>{cat_name}（{len(cat_items)} 个）</summary>")
        lines.append("")
        lines.append(render_table(cat_items, show_stars=show_stars))
        lines.append("")
        lines.append("</details>")
        lines.append("")

    return '\n'.join(lines)


# ── 主生成逻辑 ──────────────────────────────────────────

def generate_featured_section():
    catalog = load_catalog()

    by_type = defaultdict(list)
    for item in catalog:
        by_type[item['type']].append(item)

    mcp_all = by_type['mcp']
    skill_all = select_skills(by_type['skill'])
    rule_all = select_rules(by_type['rule'])
    prompt_all = select_prompts(by_type['prompt'])

    out = []

    # ── Header ──
    out.append("## ⭐ 精选推荐")
    out.append("")
    out.append("> 从 1400+ 资源中按 Star 数、活跃度、技术栈自动筛选。每周随索引同步更新。")
    out.append(">")
    out.append("> 💡 安装后使用 `/coding-hub:search <关键词>` 搜索完整索引，或 `/coding-hub:recommend` 获取基于项目的智能推荐。")
    out.append("")

    # ── MCP Servers ──
    out.append("### 🔌 MCP Servers")
    out.append("")
    out.append("MCP (Model Context Protocol) 让 AI 能够访问外部工具和数据源。以下按 Star 数精选最受欢迎的服务器：")
    out.append("")

    mcp_top = select_mcp_top(by_type['mcp'], 5)
    top_ids = {item['id'] for item in mcp_top}
    mcp_rest = select_mcp_rest(by_type['mcp'], top_ids, 30)

    out.append(render_detailed(mcp_top))
    out.append("")

    rest_groups = group_by_tech(mcp_rest)
    if mcp_rest:
        out.append("**更多按技术栈分类：**")
        out.append("")
        out.append(render_tech_groups(rest_groups, show_stars=True))

    # ── Skills ──
    out.append("### 🎯 Skills")
    out.append("")
    out.append("Skills 扩展 AI Agent 的专业能力。精选来自 Anthropic 官方、HuggingFace 和社区的高质量技能：")
    out.append("")

    skill_top = skill_all[:3]
    skill_rest = skill_all[3:]

    out.append(render_detailed(skill_top, show_stars=False))
    out.append("")

    skill_groups = group_by_tech(skill_rest)
    if skill_rest:
        out.append("**更多按技术栈分类：**")
        out.append("")
        out.append(render_tech_groups(skill_groups, show_stars=False))

    # ── Rules ──
    out.append("### 📋 Rules")
    out.append("")
    out.append("编码规范和 AI 辅助规则，帮你的 Agent 写出更规范的代码：")
    out.append("")
    rule_groups = group_by_tech(rule_all)
    out.append(render_tech_groups(rule_groups, show_stars=False))

    # ── Prompts ──
    out.append("### 💡 Prompts")
    out.append("")
    out.append("开发者专用 Prompt，覆盖编码、调试、架构设计等场景：")
    out.append("")
    prompt_groups = group_by_tech(prompt_all)
    out.append(render_tech_groups(prompt_groups, show_stars=False))

    return '\n'.join(out)


if __name__ == '__main__':
    featured = generate_featured_section()

    output_path = Path(__file__).parent.parent / "catalog" / "featured.md"
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(featured)

    print(f"✅ 精选内容已生成: {output_path}")
