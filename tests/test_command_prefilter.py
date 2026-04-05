"""
Tests for command prefilter optimization.

Validates that:
1. All command files instruct LLM to use bash+python prefiltering (not in-context JSON processing)
2. All SKILL.md files contain the prefilter strategy guidance
3. Python filtering scripts produce correct results for search/browse/recommend
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLATFORMS = {
    "claude-code": {
        "cmd_dir": "platforms/claude-code/commands/coding-hub",
        "cmd_names": {"search": "search.md", "browse": "browse.md", "recommend": "recommend.md"},
        "skill": "platforms/claude-code/skills/coding-hub/SKILL.md",
    },
    "opencode": {
        "cmd_dir": "platforms/opencode/command",
        "cmd_names": {"search": "coding-hub-search.md", "browse": "coding-hub-browse.md", "recommend": "coding-hub-recommend.md"},
        "skill": "platforms/opencode/skills/coding-hub/SKILL.md",
    },
    "costrict": {
        "cmd_dir": "platforms/costrict/commands/coding-hub",
        "cmd_names": {"search": "coding-hub-search.md", "browse": "coding-hub-browse.md", "recommend": "coding-hub-recommend.md"},
        "skill": "platforms/costrict/skills/coding-hub/SKILL.md",
    },
    "vscode-costrict": {
        "cmd_dir": "platforms/vscode-costrict/commands/coding-hub",
        "cmd_names": {"search": "coding-hub-search.md", "browse": "coding-hub-browse.md", "recommend": "coding-hub-recommend.md"},
        "skill": "platforms/vscode-costrict/skills/coding-hub/SKILL.md",
    },
}

# Sample data for filtering tests
SAMPLE_INDEX = [
    {"id": "react-query-mcp", "name": "React Query MCP", "type": "mcp", "description": "MCP server for React Query integration", "stars": 1500, "category": "frontend", "tags": ["react", "query"], "tech_stack": ["react", "javascript"]},
    {"id": "python-linter", "name": "Python Linter", "type": "rule", "description": "Linting rules for Python projects", "stars": 800, "category": "tooling", "tags": ["python", "linter"], "tech_stack": ["python"]},
    {"id": "docker-compose-mcp", "name": "Docker Compose MCP", "type": "mcp", "description": "Manage Docker containers via MCP", "stars": 2000, "category": "devops", "tags": ["docker", "container"], "tech_stack": ["docker"]},
    {"id": "typescript-rules", "name": "TypeScript Rules", "type": "rule", "description": "TypeScript best practices and rules", "stars": 500, "category": "frontend", "tags": ["typescript", "rules"], "tech_stack": ["typescript", "javascript"]},
    {"id": "fastapi-skill", "name": "FastAPI Skill", "type": "skill", "description": "FastAPI development skill", "stars": 300, "category": "backend", "tags": ["python", "fastapi", "api"], "tech_stack": ["python", "fastapi"]},
    {"id": "react-testing", "name": "React Testing", "type": "skill", "description": "React component testing skill", "stars": 600, "category": "testing", "tags": ["react", "testing", "jest"], "tech_stack": ["react", "javascript"]},
    {"id": "go-mcp", "name": "Go MCP Server", "type": "mcp", "description": "Go language MCP server", "stars": 400, "category": "backend", "tags": ["go", "golang"], "tech_stack": ["go"]},
    {"id": "vue-prompt", "name": "Vue.js Prompt", "type": "prompt", "description": "Vue.js development prompt", "stars": 200, "category": "frontend", "tags": ["vue", "frontend"], "tech_stack": ["vue", "javascript"]},
]


class TestCommandFilesHavePrefilter(unittest.TestCase):
    """Verify command files instruct LLM to use bash prefiltering."""

    def _read(self, rel_path):
        p = ROOT / rel_path
        self.assertTrue(p.exists(), f"File not found: {rel_path}")
        return p.read_text(encoding="utf-8")

    def test_search_commands_have_prefilter(self):
        for platform, cfg in PLATFORMS.items():
            path = f"{cfg['cmd_dir']}/{cfg['cmd_names']['search']}"
            content = self._read(path)
            has_prefilter = "预过滤" in content or "pre-filter" in content.lower()
            self.assertTrue(has_prefilter, f"{platform} search: missing pre-filter instruction")
            self.assertIn("python", content.lower(), f"{platform} search: missing python reference")
            # Should NOT tell LLM to process full JSON in context
            self.assertNotIn("获取 JSON", content, f"{platform} search: still has '获取 JSON' (full in-context pattern)")

    def test_browse_commands_have_prefilter(self):
        for platform, cfg in PLATFORMS.items():
            path = f"{cfg['cmd_dir']}/{cfg['cmd_names']['browse']}"
            content = self._read(path)
            has_prefilter = "预过滤" in content or "pre-filter" in content.lower()
            self.assertTrue(has_prefilter, f"{platform} browse: missing pre-filter instruction")
            self.assertIn("python", content.lower(), f"{platform} browse: missing python reference")
            self.assertNotIn("获取 JSON", content, f"{platform} browse: still has '获取 JSON'")

    def test_recommend_commands_have_prefilter(self):
        for platform, cfg in PLATFORMS.items():
            path = f"{cfg['cmd_dir']}/{cfg['cmd_names']['recommend']}"
            content = self._read(path)
            has_prefilter = "预过滤" in content or "pre-filter" in content.lower()
            self.assertTrue(has_prefilter, f"{platform} recommend: missing pre-filter instruction")
            self.assertIn("python", content.lower(), f"{platform} recommend: missing python reference")
            self.assertNotIn("获取 JSON", content, f"{platform} recommend: still has '获取 JSON'")

    def test_skill_files_have_prefilter_strategy(self):
        for platform, cfg in PLATFORMS.items():
            content = self._read(cfg["skill"])
            has_prefilter = "预过滤" in content or "pre-filter" in content.lower()
            self.assertTrue(has_prefilter, f"{platform} SKILL.md: missing pre-filter strategy")

    def test_commands_have_python_compat_hint(self):
        """Commands should mention python3/python cross-platform compatibility."""
        for platform, cfg in PLATFORMS.items():
            for cmd_type in ("search", "browse", "recommend"):
                path = f"{cfg['cmd_dir']}/{cfg['cmd_names'][cmd_type]}"
                content = self._read(path)
                has_compat = ("python3" in content and "python" in content) or "command -v" in content
                self.assertTrue(has_compat, f"{platform} {cmd_type}: missing python cross-platform hint")


class TestSearchFilter(unittest.TestCase):
    """Test the python search filtering logic with sample data."""

    def _run_filter(self, keywords, type_filter=None, limit=10):
        """Run search filter script and return parsed results."""
        index_file = self._write_sample()
        script = self._search_script(index_file, keywords, type_filter, limit)
        return self._exec(script)

    def _write_sample(self):
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump(SAMPLE_INDEX, f, ensure_ascii=False)
        f.close()
        return f.name

    def _search_script(self, index_file, keywords, type_filter=None, limit=10):
        type_cond = f"and item.get('type') == '{type_filter}'" if type_filter else ""
        return f"""
import json, sys
data = json.load(open('{index_file}'))
keywords = {keywords!r}.lower().split()
results = []
for item in data:
    searchable = ' '.join([
        item.get('name', ''),
        item.get('description', ''),
        ' '.join(item.get('tags', []))
    ]).lower()
    match_count = sum(1 for kw in keywords if kw in searchable)
    if match_count > 0 {type_cond}:
        results.append((match_count, item.get('stars', 0), item['id'], item['name'], item['type'], item.get('category', ''), item.get('stars', 0), item.get('description', '')[:80]))
results.sort(key=lambda x: (-x[0], -x[1]))
for r in results[:{limit}]:
    print('\\t'.join(str(x) for x in r[2:]))
"""

    def _exec(self, script):
        py = sys.executable
        result = subprocess.run([py, "-c", script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, f"Script failed: {result.stderr}")
        lines = [l for l in result.stdout.strip().split("\n") if l]
        return [l.split("\t") for l in lines]

    def test_search_keyword_match(self):
        results = self._run_filter("react")
        ids = [r[0] for r in results]
        self.assertIn("react-query-mcp", ids)
        self.assertIn("react-testing", ids)
        self.assertNotIn("python-linter", ids)

    def test_search_type_filter(self):
        results = self._run_filter("react", type_filter="mcp")
        ids = [r[0] for r in results]
        self.assertIn("react-query-mcp", ids)
        self.assertNotIn("react-testing", ids)  # skill, not mcp

    def test_search_no_match(self):
        results = self._run_filter("zzz_nonexistent")
        self.assertEqual(len(results), 0)

    def test_search_ranking_by_match_count_then_stars(self):
        # "python" matches python-linter (tags:python) and fastapi-skill (tags:python,fastapi)
        results = self._run_filter("python")
        ids = [r[0] for r in results]
        self.assertIn("python-linter", ids)
        self.assertIn("fastapi-skill", ids)
        # python-linter has more stars (800 vs 300), both match 1 keyword
        self.assertEqual(ids[0], "python-linter")

    def test_search_limit(self):
        results = self._run_filter("a", limit=3)  # 'a' matches many items
        self.assertLessEqual(len(results), 3)


class TestBrowseFilter(unittest.TestCase):
    """Test the python browse filtering logic."""

    def _write_sample(self):
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump(SAMPLE_INDEX, f, ensure_ascii=False)
        f.close()
        return f.name

    def _exec(self, script):
        py = sys.executable
        result = subprocess.run([py, "-c", script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, f"Script failed: {result.stderr}")
        lines = [l for l in result.stdout.strip().split("\n") if l]
        return [l.split("\t") for l in lines]

    def test_browse_categories_overview(self):
        index_file = self._write_sample()
        script = f"""
import json
from collections import Counter
data = json.load(open('{index_file}'))
counts = Counter(item.get('category', 'unknown') for item in data)
for cat, cnt in sorted(counts.items(), key=lambda x: -x[1]):
    print(f'{{cat}}\\t{{cnt}}')
"""
        results = self._exec(script)
        cats = {r[0]: int(r[1]) for r in results}
        self.assertEqual(cats["frontend"], 3)  # react-query, typescript-rules, vue-prompt
        self.assertEqual(cats["backend"], 2)  # fastapi-skill, go-mcp
        self.assertEqual(cats["devops"], 1)
        self.assertEqual(cats["tooling"], 1)
        self.assertEqual(cats["testing"], 1)

    def test_browse_specific_category(self):
        index_file = self._write_sample()
        script = f"""
import json
data = json.load(open('{index_file}'))
category = 'frontend'
results = [item for item in data if item.get('category') == category]
results.sort(key=lambda x: -(x.get('stars') or 0))
for r in results:
    print('\\t'.join([r['id'], r['name'], r['type'], str(r.get('stars', 0)), (r.get('description') or '')[:80]]))
"""
        results = self._exec(script)
        ids = [r[0] for r in results]
        self.assertEqual(ids, ["react-query-mcp", "typescript-rules", "vue-prompt"])  # sorted by stars desc

    def test_browse_category_with_type_filter(self):
        index_file = self._write_sample()
        script = f"""
import json
data = json.load(open('{index_file}'))
category = 'frontend'
type_filter = 'rule'
results = [item for item in data if item.get('category') == category and item.get('type') == type_filter]
results.sort(key=lambda x: -(x.get('stars') or 0))
for r in results:
    print('\\t'.join([r['id'], r['name'], r['type'], str(r.get('stars', 0)), (r.get('description') or '')[:80]]))
"""
        results = self._exec(script)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0], "typescript-rules")


class TestRecommendFilter(unittest.TestCase):
    """Test the python recommend filtering logic."""

    def _write_sample(self):
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump(SAMPLE_INDEX, f, ensure_ascii=False)
        f.close()
        return f.name

    def _exec(self, script):
        py = sys.executable
        result = subprocess.run([py, "-c", script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, f"Script failed: {result.stderr}")
        lines = [l for l in result.stdout.strip().split("\n") if l]
        return [l.split("\t") for l in lines]

    def test_recommend_tag_matching(self):
        index_file = self._write_sample()
        script = f"""
import json
data = json.load(open('{index_file}'))
project_tags = {{'react', 'javascript'}}
results = []
for item in data:
    item_tags = set(item.get('tags', []) + item.get('tech_stack', []))
    matched = project_tags & item_tags
    if matched:
        results.append((len(matched), item.get('stars', 0), item['id'], item['name'], item['type'], ','.join(sorted(matched)), item.get('stars', 0), (item.get('description') or '')[:80]))
results.sort(key=lambda x: (-x[0], -x[1]))
for r in results[:10]:
    print('\\t'.join(str(x) for x in r[2:]))
"""
        results = self._exec(script)
        ids = [r[0] for r in results]
        # react + javascript match both fields for react-query-mcp and react-testing
        self.assertIn("react-query-mcp", ids)
        self.assertIn("react-testing", ids)
        # typescript-rules has javascript in tech_stack
        self.assertIn("typescript-rules", ids)
        # vue-prompt has javascript in tech_stack
        self.assertIn("vue-prompt", ids)
        # python/go items should NOT match
        self.assertNotIn("python-linter", ids)
        self.assertNotIn("go-mcp", ids)

    def test_recommend_ranking(self):
        """Items matching more tags should rank higher."""
        index_file = self._write_sample()
        script = f"""
import json
data = json.load(open('{index_file}'))
project_tags = {{'react', 'javascript'}}
results = []
for item in data:
    item_tags = set(item.get('tags', []) + item.get('tech_stack', []))
    matched = project_tags & item_tags
    if matched:
        results.append((len(matched), item.get('stars', 0), item['id'], item['name'], item['type'], ','.join(sorted(matched)), item.get('stars', 0), (item.get('description') or '')[:80]))
results.sort(key=lambda x: (-x[0], -x[1]))
for r in results[:10]:
    print('\\t'.join(str(x) for x in r[2:]))
"""
        results = self._exec(script)
        # react-query-mcp matches 2 tags (react, javascript), stars=1500
        # react-testing matches 2 tags (react, javascript), stars=600
        # Both should come before typescript-rules (1 tag match: javascript)
        ids = [r[0] for r in results]
        rq_idx = ids.index("react-query-mcp")
        rt_idx = ids.index("react-testing")
        ts_idx = ids.index("typescript-rules")
        self.assertLess(rq_idx, ts_idx)
        self.assertLess(rt_idx, ts_idx)
        # react-query-mcp has more stars, should rank first among 2-tag matches
        self.assertLess(rq_idx, rt_idx)

    def test_recommend_type_filter(self):
        index_file = self._write_sample()
        script = f"""
import json
data = json.load(open('{index_file}'))
project_tags = {{'react', 'javascript'}}
type_filter = 'mcp'
results = []
for item in data:
    if type_filter and item.get('type') != type_filter:
        continue
    item_tags = set(item.get('tags', []) + item.get('tech_stack', []))
    matched = project_tags & item_tags
    if matched:
        results.append((len(matched), item.get('stars', 0), item['id'], item['name'], item['type'], ','.join(sorted(matched)), item.get('stars', 0), (item.get('description') or '')[:80]))
results.sort(key=lambda x: (-x[0], -x[1]))
for r in results[:10]:
    print('\\t'.join(str(x) for x in r[2:]))
"""
        results = self._exec(script)
        ids = [r[0] for r in results]
        self.assertIn("react-query-mcp", ids)
        self.assertNotIn("react-testing", ids)  # skill, not mcp
        self.assertNotIn("typescript-rules", ids)  # rule, not mcp

    def test_recommend_no_match(self):
        index_file = self._write_sample()
        script = f"""
import json
data = json.load(open('{index_file}'))
project_tags = {{'swift', 'ios'}}
results = []
for item in data:
    item_tags = set(item.get('tags', []) + item.get('tech_stack', []))
    matched = project_tags & item_tags
    if matched:
        results.append((len(matched), item.get('stars', 0), item['id']))
results.sort(key=lambda x: (-x[0], -x[1]))
for r in results[:10]:
    print(r[2])
"""
        results = self._exec(script)
        self.assertEqual(len(results), 0)


class TestCommandIndexRouting(unittest.TestCase):
    """Verify search/browse/recommend use Pages search-index, install uses Pages per-entry API."""

    PAGES_BASE = "zgsm-sangfor.github.io/costrict-coding-hub/api/v1"
    RAW_BASE = "raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/catalog"

    def _read(self, rel_path):
        p = ROOT / rel_path
        self.assertTrue(p.exists(), f"File not found: {rel_path}")
        return p.read_text(encoding="utf-8")

    def test_search_browse_recommend_use_pages_search_index(self):
        for platform, cfg in PLATFORMS.items():
            for cmd_type in ("search", "browse", "recommend"):
                path = f"{cfg['cmd_dir']}/{cfg['cmd_names'][cmd_type]}"
                content = self._read(path)
                self.assertIn(
                    f"{self.PAGES_BASE}/search-index.json", content,
                    f"{platform} {cmd_type}: should reference Pages search-index.json"
                )

    def test_search_browse_recommend_have_raw_fallback(self):
        for platform, cfg in PLATFORMS.items():
            for cmd_type in ("search", "browse", "recommend"):
                path = f"{cfg['cmd_dir']}/{cfg['cmd_names'][cmd_type]}"
                content = self._read(path)
                self.assertIn(
                    f"{self.RAW_BASE}/search-index.json", content,
                    f"{platform} {cmd_type}: should have raw URL fallback"
                )

    def test_install_uses_pages_per_entry_api(self):
        install_files = {
            "claude-code": "platforms/claude-code/commands/coding-hub/install.md",
            "opencode": "platforms/opencode/command/coding-hub-install.md",
            "costrict": "platforms/costrict/commands/coding-hub/coding-hub-install.md",
            "vscode-costrict": "platforms/vscode-costrict/commands/coding-hub/coding-hub-install.md",
        }
        for platform, path in install_files.items():
            content = self._read(path)
            self.assertIn(
                self.PAGES_BASE, content,
                f"{platform} install: should reference Pages API"
            )

    def test_install_has_full_index_fallback(self):
        install_files = {
            "claude-code": "platforms/claude-code/commands/coding-hub/install.md",
            "opencode": "platforms/opencode/command/coding-hub-install.md",
            "costrict": "platforms/costrict/commands/coding-hub/coding-hub-install.md",
            "vscode-costrict": "platforms/vscode-costrict/commands/coding-hub/coding-hub-install.md",
        }
        for platform, path in install_files.items():
            content = self._read(path)
            self.assertIn(
                f"{self.RAW_BASE}/index.json", content,
                f"{platform} install: should have full index fallback"
            )


if __name__ == "__main__":
    unittest.main()
