#!/usr/bin/env python3
"""从 catalog/index.json 生成按使用场景分类的精选推荐（方案B：bullet list）。

按场景分类，混合 MCP/Skill/Rule/Prompt 四种资源类型。
MCP 展示 star 数，其他类型展示来源标签。
"""

import json
import re
from pathlib import Path
from collections import defaultdict, Counter


def load_catalog():
    catalog_path = Path(__file__).parent.parent / "catalog" / "index.json"
    with open(catalog_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def format_stars(stars):
    if stars is None:
        return None
    if stars >= 1000:
        return f"{stars/1000:.1f}k"
    return str(stars)


def trunc(text, n=80):
    if len(text) <= n:
        return text
    # 在词边界截断，避免截到中文字中间
    cut = text[:n]
    # 如果最后是中文字符，直接截断
    if ord(cut[-1]) > 127:
        return cut.rstrip('。，、；：！？') + '…'
    # 否则尝试在最后一个空格处截断
    last_space = cut.rfind(' ')
    if last_space > n * 0.6:
        return cut[:last_space] + '…'
    return cut + '…'


def extract_repo_key(url):
    """提取 org/repo 作为去重 key"""
    m = re.match(r'https://github\.com/([^/]+/[^/]+)', url)
    return m.group(1) if m else url


# ── 使用场景分类 ──────────────────────────────────────────

SCENE_CATEGORIES = [
    # 顺序决定匹配优先级：更具体的分类放前面
    ('browser',  '🌐 浏览器 & 自动化', [
        'playwright', 'puppeteer', 'selenium', 'automation', 'browser',
        'scraping', 'crawl', 'web-scraping', 'e2e', 'scraper',
    ]),
    ('git',      '🐙 Git & 协作', [
        'git', 'github', 'gitlab', 'version-control',
    ]),
    ('devops',   '🚀 DevOps & 安全', [
        'docker', 'kubernetes', 'k8s', 'ci', 'cd', 'deploy', 'terraform',
        'aws', 'gcp', 'azure', 'cloud', 'nginx', 'linux', 'devops',
        'security', 'auth', 'oauth', 'owasp', 'audit', 'cloudflare',
        'monitoring', 'logging',
    ]),
    ('docs',     '📚 文档 & 知识', [
        'documentation', 'markdown', 'knowledge', 'rag', 'memory',
        'docs', 'markitdown', 'technical-writing',
    ]),
    ('frontend', '🎨 前端 & 设计', [
        'react', 'vue', 'angular', 'svelte', 'nextjs', 'next.js', 'tailwind',
        'css', 'ui', 'figma', 'design', 'frontend', 'html', 'shadcn',
    ]),
    ('backend',  '⚙️ 后端 & 数据库', [
        'fastapi', 'django', 'flask', 'express', 'nestjs', 'spring',
        'backend', 'microservice',
        'postgres', 'mysql', 'mongodb', 'redis', 'sqlite', 'database',
        'sql', 'supabase', 'pydantic',
    ]),
    ('ai',       '🤖 AI & MCP 开发', [
        'llm', 'langchain', 'openai', 'anthropic', 'claude', 'agent',
        'mcp', 'embedding', 'vector', 'blender', '3d',
        'ai', 'ml', 'deep-learning',
    ]),
]


def classify_item(item):
    """返回 item 匹配到的第一个场景分类 key"""
    tags = set(t.lower() for t in item.get('tags', []))
    name_lower = item.get('name', '').lower()
    desc_lower = item.get('description', '').lower()[:200]
    cat = item.get('category', '').lower()

    # 先用 catalog 自带的 category 做粗映射
    cat_hint = {
        'automation': 'browser', 'browser': 'browser',
        'git': 'git', 'github': 'git',
        'devops': 'devops', 'security': 'devops',
        'documentation': 'docs',
        'frontend': 'frontend',
        'backend': 'backend', 'database': 'backend',
        'ai-ml': 'ai', 'testing': None,
        'tooling': 'ai',
    }.get(cat)

    # 再用关键词精确匹配
    for cat_key, _, keywords in SCENE_CATEGORIES:
        for kw in keywords:
            if kw in tags or kw in name_lower:
                return cat_key
            # 描述匹配需要词边界，避免误匹配
            if re.search(rf'\b{re.escape(kw)}\b', desc_lower):
                return cat_key

    # fallback 到 category hint
    return cat_hint


# ── 来源标签 ──────────────────────────────────────────

SOURCE_LABELS = {
    'anthropics-skills': 'Anthropic 官方',
    'ai-agent-skills': '社区精选',
    'curated': '精选',
    'rules-2.1-optimized': 'Rules 2.1',
    'awesome-cursorrules': 'CursorRules',
    'prompts-chat': 'prompts.chat',
    'wonderful-prompts': 'wonderful-prompts',
}


def get_source_label(item):
    """获取非 MCP 类型的来源标签"""
    source = item.get('source', '')
    return SOURCE_LABELS.get(source, source)


# ── 选择策略 ──────────────────────────────────────────

def select_top_items(catalog):
    """从全部资源中按场景选出精选条目。

    策略:
    - MCP: 按 star 排序，每个场景取 top 3-4，总共约 25 个
    - Skill/Rule/Prompt: 按来源优先级选，每个场景补 1-2 个
    """
    by_type = defaultdict(list)
    for item in catalog:
        by_type[item['type']].append(item)

    # MCP: 过滤有 star 的，按 star 排序
    mcp_items = sorted(
        [i for i in by_type['mcp'] if i.get('stars') and i['stars'] > 0],
        key=lambda x: x['stars'],
        reverse=True,
    )

    # Skill: 按来源优先级
    skill_priority = {'curated': 0, 'anthropics-skills': 1, 'ai-agent-skills': 2}
    skill_items = sorted(
        by_type['skill'],
        key=lambda x: (skill_priority.get(x.get('source', ''), 99), x.get('name', '')),
    )

    # Rule: 按来源优先级 + tag 丰富度
    rule_priority = {'curated': 0, 'rules-2.1-optimized': 1, 'awesome-cursorrules': 2}
    rule_items = sorted(
        by_type['rule'],
        key=lambda x: (rule_priority.get(x.get('source', ''), 99), -len(x.get('tags', []))),
    )

    # Prompt: 按来源优先级，优先 coding 相关
    prompt_priority = {'curated': 0, 'wonderful-prompts': 1, 'prompts-chat': 2}
    prompt_items = sorted(
        by_type['prompt'],
        key=lambda x: (prompt_priority.get(x.get('source', ''), 99), x.get('name', '')),
    )

    # 按场景分组选择
    scene_items = defaultdict(list)
    seen_repos = set()  # 全局去重

    # 1. 每个场景选 MCP top items
    mcp_per_scene = 4
    for item in mcp_items:
        scene = classify_item(item)
        if scene is None:
            continue
        repo_key = extract_repo_key(item.get('source_url', ''))
        if repo_key in seen_repos:
            continue
        if len([i for i in scene_items[scene] if i['type'] == 'mcp']) >= mcp_per_scene:
            continue
        seen_repos.add(repo_key)
        scene_items[scene].append(item)

    # 2. 每个场景补 Skill/Rule/Prompt
    for items, max_per_scene in [
        (skill_items, 2),
        (rule_items, 2),
        (prompt_items, 1),
    ]:
        scene_count = Counter()
        for item in items:
            scene = classify_item(item)
            if scene is None:
                continue
            if scene_count[scene] >= max_per_scene:
                continue
            name_key = item.get('name', '').lower()
            if name_key in seen_repos:
                continue
            seen_repos.add(name_key)
            scene_count[scene] += 1
            scene_items[scene].append(item)

    return scene_items


# ── 渲染 ──────────────────────────────────────────

TYPE_EMOJI = {
    'mcp': '🔌',
    'skill': '🎯',
    'rule': '📋',
    'prompt': '💡',
}


def render_bullet(item):
    """渲染单条 bullet"""
    emoji = TYPE_EMOJI.get(item['type'], '📦')
    name = item.get('name', '')
    url = item.get('source_url', '')
    desc = trunc(item.get('description', ''), 70)

    # 尾部信息：MCP 用 star，其他用来源标签
    if item['type'] == 'mcp' and item.get('stars'):
        tail = f"⭐ {format_stars(item['stars'])}"
    else:
        tail = f"`{get_source_label(item)}`"

    return f"- {emoji} **[{name}]({url})** — {desc} {tail}"


def generate_featured_section():
    catalog = load_catalog()
    scene_items = select_top_items(catalog)

    total = len(catalog)

    out = []
    out.append("## ⭐ 精选推荐")
    out.append("")
    out.append(f"> 从 {total}+ 资源中按使用场景精选。安装后用 `/coding-hub:search` 搜索完整索引，或 `/coding-hub:recommend` 获取项目级推荐。")
    out.append("")

    for cat_key, cat_name, _ in SCENE_CATEGORIES:
        items = scene_items.get(cat_key, [])
        if not items:
            continue

        out.append(f"### {cat_name}")
        out.append("")
        for item in items:
            out.append(render_bullet(item))
        out.append("")

    out.append("> 图例：🔌 MCP Server · 🎯 Skill · 📋 Rule · 💡 Prompt")
    out.append("")

    return '\n'.join(out)


if __name__ == '__main__':
    featured = generate_featured_section()

    output_path = Path(__file__).parent.parent / "catalog" / "featured.md"
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(featured)

    print(f"✅ 精选内容已生成: {output_path}")
