"""Tests for deduplicate() — ID dedup, URL dedup, type-aware behavior."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from utils import deduplicate


def _entry(id, type="mcp", source_url="https://github.com/test/repo", name="Test"):
    return {
        "id": id,
        "name": name,
        "type": type,
        "description": "test",
        "source_url": source_url,
        "stars": 0,
        "category": "tooling",
        "tags": [],
        "tech_stack": [],
        "install": {"method": "manual"},
        "source": "test",
        "last_synced": "2026-03-30",
    }


class TestDeduplicateBasics:
    """Basic dedup: by ID, empty list, entries without ID."""

    def test_dedup_by_id(self):
        entries = [
            {"id": "tool-a", "name": "First"},
            {"id": "tool-a", "name": "Duplicate"},
            {"id": "tool-b", "name": "Other"},
        ]
        result = deduplicate(entries)
        assert len(result) == 2
        assert result[0]["name"] == "First"

    def test_no_duplicates(self):
        entries = [
            {"id": "a", "source_url": "https://github.com/owner/a"},
            {"id": "b", "source_url": "https://github.com/owner/b"},
        ]
        result = deduplicate(entries)
        assert len(result) == 2

    def test_empty_list(self):
        assert deduplicate([]) == []

    def test_entries_without_id(self):
        entries = [{"name": "no-id"}, {"name": "also-no-id"}]
        result = deduplicate(entries)
        assert len(result) == 2

    def test_entries_without_source_url(self):
        entries = [{"id": "a"}, {"id": "b"}]
        result = deduplicate(entries)
        assert len(result) == 2


class TestUrlNormalization:
    """URL normalization: trailing slash, .git suffix, case insensitive."""

    def test_url_trailing_slash(self):
        entries = [
            _entry("a", source_url="https://github.com/owner/repo"),
            _entry("b", source_url="https://github.com/owner/repo/"),
        ]
        result = deduplicate(entries)
        assert len(result) == 1

    def test_url_dot_git_suffix(self):
        entries = [
            _entry("a", source_url="https://github.com/owner/repo"),
            _entry("b", source_url="https://github.com/owner/repo.git"),
        ]
        result = deduplicate(entries)
        assert len(result) == 1

    def test_url_case_insensitive(self):
        entries = [
            _entry("a", source_url="https://github.com/Owner/Repo"),
            _entry("b", source_url="https://github.com/owner/repo"),
        ]
        result = deduplicate(entries)
        assert len(result) == 1

    def test_different_urls_kept(self):
        entries = [
            _entry("a", source_url="https://github.com/owner/repo-a"),
            _entry("b", source_url="https://github.com/owner/repo-b"),
        ]
        result = deduplicate(entries)
        assert len(result) == 2


class TestTypeAwareDedup:
    """Type-aware URL dedup: prompt/rule skip URL dedup, MCP/skill keep it."""

    def test_prompts_sharing_url_all_preserved(self):
        """10 prompts with unique ids but same source_url → all 10 kept."""
        entries = [
            _entry(f"prompt-{i}", type="prompt", source_url="https://github.com/f/prompts.chat")
            for i in range(10)
        ]
        result = deduplicate(entries)
        assert len(result) == 10

    def test_rules_sharing_url_all_preserved(self):
        """5 rules with unique ids but same source_url → all 5 kept."""
        entries = [
            _entry(f"rule-{i}", type="rule", source_url="https://github.com/Mr-chen-05/rules-2.1-optimized")
            for i in range(5)
        ]
        result = deduplicate(entries)
        assert len(result) == 5

    def test_mcp_same_url_deduped(self):
        """2 MCP entries with different ids but same source_url → only first kept."""
        entries = [
            _entry("mcp-a", type="mcp", source_url="https://github.com/owner/server"),
            _entry("mcp-b", type="mcp", source_url="https://github.com/owner/server"),
        ]
        result = deduplicate(entries)
        assert len(result) == 1
        assert result[0]["id"] == "mcp-a"

    def test_skill_same_url_deduped(self):
        """2 skill entries with different ids but same source_url → only first kept."""
        entries = [
            _entry("skill-a", type="skill", source_url="https://github.com/owner/skills"),
            _entry("skill-b", type="skill", source_url="https://github.com/owner/skills"),
        ]
        result = deduplicate(entries)
        assert len(result) == 1
        assert result[0]["id"] == "skill-a"

    def test_prompt_id_dedup_still_works(self):
        """2 prompts with same id → only first kept (id dedup active)."""
        entries = [
            _entry("same-id", type="prompt", source_url="https://github.com/f/prompts.chat", name="First"),
            _entry("same-id", type="prompt", source_url="https://github.com/f/prompts.chat", name="Second"),
        ]
        result = deduplicate(entries)
        assert len(result) == 1
        assert result[0]["name"] == "First"
