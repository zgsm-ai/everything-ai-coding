"""scripts/sync_skills.py 文档/办公专源 parser 单元测试。

覆盖：
- parse_claude_office_skills：仓库根 <dir>/SKILL.md 收录、排除目录、固定 category、install 形态
- parse_composio_office_skills：master 分支、exclude-set、composio-skills 嵌套排除、跨源去重、license-unknown tag
- source_registry：两个新 slug 登记 + build_sources_payload 计数
"""

import os
import sys
import unittest
import unittest.mock as mock

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import sync_skills as ss  # noqa: E402
import source_registry as sr  # noqa: E402


def _repo_info(stars=207, pushed_at="2026-01-31T14:03:56Z"):
    return {"stargazers_count": stars, "pushed_at": pushed_at}


class TestParseClaudeOfficeSkills(unittest.TestCase):
    def setUp(self):
        # list_repo_files would already substring-filter to SKILL.md paths.
        self.tree_paths = [
            "academic-search/SKILL.md",
            "contract-review/SKILL.md",
            "_template/SKILL.md",          # scaffolding → excluded (_ prefix)
            "official-skills/SKILL.md",    # in exclude set → excluded
            "nested/sub/SKILL.md",         # not root-level (3 parts) → excluded
        ]

    def _fake_fetch(self, repo, path, branch="main", quiet_404=False):
        bodies = {
            "academic-search/SKILL.md": (
                '---\nname: academic-search\n'
                'description: "Search academic papers."\n---\n# body'
            ),
            "contract-review/SKILL.md": (
                "---\nname: contract-review\n"
                "description: Review contracts for risk.\n---\n# body"
            ),
        }
        return bodies.get(path)

    def test_full_parse(self):
        with mock.patch.object(ss, "list_repo_files", return_value=self.tree_paths), \
             mock.patch.object(ss, "github_api", return_value=_repo_info(stars=207)), \
             mock.patch.object(ss, "fetch_raw_content", side_effect=self._fake_fetch):
            entries = ss.parse_claude_office_skills()

        ids = {e["id"] for e in entries}
        self.assertEqual(ids, {"academic-search-offskill", "contract-review-offskill"})
        self.assertNotIn("template-offskill", ids)
        self.assertNotIn("official-skills-offskill", ids)

        e = next(x for x in entries if x["id"] == "academic-search-offskill")
        self.assertEqual(e["category"], "documentation")
        self.assertEqual(e["source"], "claude-office-skills")
        self.assertEqual(e["name"], "academic-search")
        self.assertEqual(e["description"], "Search academic papers.")
        self.assertEqual(
            e["install"]["repo"], "https://github.com/claude-office-skills/skills.git"
        )
        self.assertEqual(e["install"]["files"], ["academic-search/"])
        self.assertNotIn("branch", e["install"])  # main → no explicit branch
        self.assertEqual(e["stars"], 207)
        self.assertIn("office", e["tags"])
        self.assertIn("documentation", e["tags"])
        self.assertEqual(
            e["source_url"],
            "https://github.com/claude-office-skills/skills/tree/main/academic-search",
        )

    def test_fetch_failure_skips_entry(self):
        with mock.patch.object(ss, "list_repo_files", return_value=self.tree_paths), \
             mock.patch.object(ss, "github_api", return_value=_repo_info()), \
             mock.patch.object(ss, "fetch_raw_content", return_value=None):
            entries = ss.parse_claude_office_skills()
        self.assertEqual(entries, [])


class TestParseComposioOfficeSkills(unittest.TestCase):
    def setUp(self):
        self.tree_paths = [
            "content-research-writer/SKILL.md",     # original → kept
            "tailored-resume-generator/SKILL.md",   # original → kept
            "internal-comms/SKILL.md",              # anthropics copy → excluded
            "mcp-builder/SKILL.md",                 # anthropics copy → excluded
            "composio-skills/ably-automation/SKILL.md",  # nested plumbing → excluded
            "changelog-generator/SKILL.md",         # claude-office dup → excluded via dedupe
        ]

    def _fake_fetch(self, repo, path, branch="master", quiet_404=False):
        return f'---\nname: {path.split("/")[0]}\ndescription: x.\n---\n# body'

    def test_excludes_copies_plumbing_and_dups(self):
        with mock.patch.object(ss, "list_repo_files", return_value=self.tree_paths), \
             mock.patch.object(ss, "github_api", return_value=_repo_info(stars=64089)), \
             mock.patch.object(ss, "fetch_raw_content", side_effect=self._fake_fetch):
            entries = ss.parse_composio_office_skills(
                dedupe_against={"changelog-generator"}
            )

        ids = {e["id"] for e in entries}
        self.assertEqual(
            ids,
            {"content-research-writer-coskill", "tailored-resume-generator-coskill"},
        )
        self.assertNotIn("internal-comms-coskill", ids)
        self.assertNotIn("mcp-builder-coskill", ids)
        self.assertNotIn("ably-automation-coskill", ids)   # nested
        self.assertNotIn("changelog-generator-coskill", ids)  # cross-repo dedupe

        e = next(x for x in entries if x["id"] == "content-research-writer-coskill")
        self.assertEqual(e["category"], "documentation")
        self.assertEqual(e["source"], "composio-office")
        self.assertEqual(e["install"]["branch"], "master")  # critical: not main
        self.assertEqual(
            e["install"]["repo"],
            "https://github.com/ComposioHQ/awesome-claude-skills.git",
        )
        self.assertIn("license-unknown", e["tags"])
        self.assertEqual(e["stars"], 64089)
        self.assertEqual(
            e["source_url"],
            "https://github.com/ComposioHQ/awesome-claude-skills/tree/master/"
            "content-research-writer",
        )


class TestOfficeSourceRegistry(unittest.TestCase):
    def test_slugs_registered(self):
        self.assertEqual(sr.SOURCE_REGISTRY["claude-office-skills"]["trust"], 3)
        self.assertEqual(sr.SOURCE_REGISTRY["composio-office"]["trust"], 2)
        self.assertEqual(sr.SOURCE_REGISTRY["claude-office-skills"]["type"], "Skills")
        self.assertEqual(sr.SOURCE_REGISTRY["composio-office"]["type"], "Skills")

    def test_build_sources_payload_counts(self):
        items = [
            {"source": "claude-office-skills"},
            {"source": "claude-office-skills"},
            {"source": "composio-office"},
        ]
        payload = sr.build_sources_payload(items)
        by_slug = {s["slug"]: s for s in payload["sources"]}
        self.assertEqual(by_slug["claude-office-skills"]["count"], 2)
        self.assertEqual(by_slug["composio-office"]["count"], 1)
        # trust 3 → Tier 3, trust 2 → Tier 4 grouping present
        tier_scores = {t["score"] for t in payload["tiers"]}
        self.assertIn(3, tier_scores)
        self.assertIn(2, tier_scores)


if __name__ == "__main__":
    unittest.main()
