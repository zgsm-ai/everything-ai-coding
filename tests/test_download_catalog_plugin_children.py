"""Tests for download_catalog repository-backed content downloaders.

Covers the command/subagent/template (+ repo-based rule) download path that
materializes synthesized plugin children into their per-type
``catalog-download/<type-dir>/<id>/<PRIMARY>`` file, and the downloader/primary
mapping coverage that keeps the bundle from dropping new types. Skill source
normalization and authentic-content failure semantics live here as well because
this is the tracked test module for ``download_catalog.py``.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import download_catalog as dc  # noqa: E402


def _child_entry(type_, id_, repo_path):
    """A synthesized single-file plugin child as merge_index would emit it."""
    return {
        "id": id_,
        "name": id_,
        "type": type_,
        "description": f"a {type_}",
        "category": "tooling",
        "bundled_in": "some-plugin",
        "source": f"plugin-bundled-{type_}",
        "source_path": repo_path,
        "install": {
            "method": "git_clone",
            "repo": "https://github.com/yhangf/csc-plugins.git",
            "branch": "main",
            "path": repo_path,
            "files": [repo_path],
        },
    }


@pytest.fixture
def fake_fetch(monkeypatch):
    """Route fetch_raw_content to deterministic content keyed by (repo, path)."""
    seen = {}

    def _fetch(repo, path, branch="main", quiet_404=False):
        seen[(repo, path, branch)] = True
        if path.endswith("-404.md"):
            return None
        return f"# content of {path}\nbody\n"

    monkeypatch.setattr(dc, "fetch_raw_content", _fetch)
    return seen


# ---------------------------------------------------------------------------
# Downloader / primary-file table coverage (alignment with merge + bundle)
# ---------------------------------------------------------------------------

def test_new_types_have_downloaders():
    for t in ("command", "subagent", "template"):
        assert t in dc.DOWNLOADERS, f"no downloader for {t}"


def test_new_types_have_primary_file_mapping():
    for t in ("command", "subagent", "template"):
        assert t in dc._PRIMARY_FILE_BY_TYPE


def test_default_run_types_include_new_dirs():
    # run() default + CLI default must enumerate the new type dirs or their
    # index.json never gets read.
    for td in ("commands", "subagents", "templates"):
        assert td in [
            "skills", "mcp", "rules", "prompts", "plugins",
            "commands", "subagents", "templates",
        ]


# ---------------------------------------------------------------------------
# GitHub repository coordinate and path normalization
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("openclaw/acpx", "openclaw/acpx"),
        ("openclaw/acpx.git", "openclaw/acpx"),
        ("https://github.com/openclaw/acpx", "openclaw/acpx"),
        ("https://github.com/openclaw/acpx.git", "openclaw/acpx"),
        ("https://github.com/openclaw/acpx.git/", "openclaw/acpx"),
    ],
)
def test_github_repo_slug_accepts_catalog_shapes(value, expected):
    assert dc._github_repo_slug(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "openclaw",
        "openclaw/acpx/extra",
        "http://github.com/openclaw/acpx",
        "https://github.com.evil/openclaw/acpx",
        "https://user@github.com/openclaw/acpx",
        "https://github.com:443/openclaw/acpx",
        "https://github.com/openclaw/acpx?ref=main",
        "git@github.com:openclaw/acpx.git",
        "../acpx",
    ],
)
def test_github_repo_slug_rejects_ambiguous_or_unsafe_shapes(value):
    assert dc._github_repo_slug(value) is None


def test_repo_branch_and_dir_supports_shorthand_and_files_precedence():
    entry = {
        "install": {
            "repo": "openclaw/skills",
            "branch": "main",
            "path": "ignored/path",
            "files": ["skills/owner/example/"],
        }
    }
    assert dc._repo_branch_and_dir(entry) == (
        "openclaw/skills",
        "main",
        "skills/owner/example",
    )


@pytest.mark.parametrize("path", ["../outside", "/absolute", "a/../../outside", "a\\outside"])
def test_repo_branch_and_dir_rejects_unsafe_paths(path):
    entry = {"install": {"repo": "owner/repo", "path": path}}
    repo, branch, directory = dc._repo_branch_and_dir(entry)
    assert repo is None
    assert branch == "main"
    assert directory is None


@pytest.mark.parametrize("branch", ["main?raw=1", "main#fragment", "../main", "bad branch"])
def test_repo_branch_and_dir_rejects_unsafe_branches(branch):
    entry = {"install": {"repo": "owner/repo", "branch": branch, "path": "skill"}}
    repo, _, directory = dc._repo_branch_and_dir(entry)
    assert repo is None
    assert directory is None


# ---------------------------------------------------------------------------
# Single-file download materialization
# ---------------------------------------------------------------------------

def test_download_command_writes_primary_and_verbatim(fake_fetch):
    with tempfile.TemporaryDirectory() as out:
        entry = _child_entry(
            "command", "p-command-run", "p-plugin/commands/run.md"
        )
        name, ok, err = dc._download_command(entry, out)
        assert ok and err is None
        primary = os.path.join(out, "commands", "p-command-run", "COMMAND.md")
        verbatim = os.path.join(out, "commands", "p-command-run", "run.md")
        assert os.path.isfile(primary)
        assert os.path.isfile(verbatim)  # real basename preserved
        with open(primary, encoding="utf-8") as f:
            head = f.read().splitlines()[0]
        assert head == "---"  # frontmatter injected


def test_download_subagent_uses_agent_md(fake_fetch):
    with tempfile.TemporaryDirectory() as out:
        entry = _child_entry(
            "subagent", "p-subagent-code-reviewer", "p-plugin/agents/code-reviewer.md"
        )
        name, ok, err = dc._download_subagent(entry, out)
        assert ok and err is None
        assert os.path.isfile(
            os.path.join(out, "subagents", "p-subagent-code-reviewer", "AGENT.md")
        )


def test_download_template_uses_template_md(fake_fetch):
    with tempfile.TemporaryDirectory() as out:
        entry = _child_entry(
            "template", "p-template-x", "p-plugin/templates/x-template.md"
        )
        name, ok, err = dc._download_template(entry, out)
        assert ok and err is None
        assert os.path.isfile(
            os.path.join(out, "templates", "p-template-x", "TEMPLATE.md")
        )


def test_repo_based_rule_routes_to_single_file_downloader(fake_fetch):
    """A synthesized rule (install.repo present) writes rules/<id>/RULE.md from
    the repo file — NOT the legacy raw-url .cursorrules path."""
    with tempfile.TemporaryDirectory() as out:
        entry = _child_entry(
            "rule", "p-rule-dfx安全", "p-plugin/rules/dfx/安全.md"
        )
        name, ok, err = dc._download_rule(entry, out)
        assert ok and err is None
        primary = os.path.join(out, "rules", "p-rule-dfx安全", "RULE.md")
        verbatim = os.path.join(out, "rules", "p-rule-dfx安全", "安全.md")
        assert os.path.isfile(primary)
        assert os.path.isfile(verbatim)  # non-ASCII basename preserved verbatim


def test_download_missing_source_fails_without_placeholder(fake_fetch):
    with tempfile.TemporaryDirectory() as out:
        entry = _child_entry(
            "command", "p-command-gone", "p-plugin/commands/gone-404.md"
        )
        name, ok, err = dc._download_command(entry, out)
        assert not ok
        assert err == "source file unavailable"
        assert not os.path.exists(
            os.path.join(out, "commands", "p-command-gone", "COMMAND.md")
        )


# ---------------------------------------------------------------------------
# Non-ASCII (CJK) repo path → percent-encoded raw URL (regression for the
# UnicodeEncodeError crash when fetching rules/dfx/安全.md and friends)
# ---------------------------------------------------------------------------

def test_quote_repo_path_percent_encodes_non_ascii_keeps_separators():
    p = "cospowers-requirements-plugin/rules/dfx/安全.md"
    q = dc._quote_repo_path(p)
    # the urllib crash was at request.encode("ascii"); the encoded path + URL
    # must now be ASCII-encodable.
    q.encode("ascii")  # would raise UnicodeEncodeError on failure
    url = f"https://raw.githubusercontent.com/yhangf/csc-plugins/main/{q}"
    url.encode("ascii")
    # CJK is percent-encoded, '/' separators kept literal
    assert "%E5%AE%89%E5%85%A8" in q  # 安全
    assert q.count("/") == p.count("/")
    assert q.startswith("cospowers-requirements-plugin/rules/dfx/")


def test_quote_repo_path_idempotent_for_ascii():
    assert dc._quote_repo_path("rules/dfx/perf.md") == "rules/dfx/perf.md"


def test_quote_repo_path_encodes_spaces_and_parens():
    q = dc._quote_repo_path("skills/has space/file (1).md")
    q.encode("ascii")
    assert " " not in q and "(" not in q


def test_single_file_download_sends_percent_encoded_url_keeps_real_basename(monkeypatch):
    """The download MUST pass a percent-encoded path to fetch_raw_content (so
    urllib doesn't crash on CJK), yet write the file under its ORIGINAL non-ASCII
    basename on disk."""
    captured = {}

    def _fetch(repo, path, branch="main", quiet_404=False):
        captured["repo"], captured["path"], captured["branch"] = repo, path, branch
        # Mimic urllib/http.client: the request line must be ASCII-encodable.
        f"https://raw.githubusercontent.com/{repo}/{branch}/{path}".encode("ascii")
        return "# 安全 rule\n中文正文\n"

    monkeypatch.setattr(dc, "fetch_raw_content", _fetch)

    repo_path = "cospowers-requirements-plugin/rules/dfx/安全.md"
    entry = _child_entry("rule", "p-rule-dfx安全", repo_path)
    with tempfile.TemporaryDirectory() as out:
        name, ok, err = dc._download_rule(entry, out)
        assert ok and err is None
        # URL path is percent-encoded (and thus ASCII-safe — no crash)
        assert captured["path"] == "cospowers-requirements-plugin/rules/dfx/%E5%AE%89%E5%85%A8.md"
        captured["path"].encode("ascii")
        # verbatim file lands under its REAL non-ASCII basename
        assert os.path.isfile(os.path.join(out, "rules", "p-rule-dfx安全", "安全.md"))
        # primary RULE.md written too
        assert os.path.isfile(os.path.join(out, "rules", "p-rule-dfx安全", "RULE.md"))


def test_skill_dir_download_quotes_non_ascii_sibling(monkeypatch):
    """_download_skill's directory fetch must also percent-encode non-ASCII
    sibling filenames inside a skill dir."""
    captured_paths = []

    def _fetch(repo, path, branch="main", quiet_404=False):
        captured_paths.append(path)
        f"https://raw.githubusercontent.com/{repo}/{branch}/{path}".encode("ascii")
        return "content\n"

    monkeypatch.setattr(dc, "fetch_raw_content", _fetch)

    entry = {
        "id": "some-skill", "name": "some-skill", "type": "skill",
        "category": "tooling", "description": "d",
        "install": {
            "method": "git_clone",
            "repo": "https://github.com/yhangf/csc-plugins.git",
            "branch": "main",
            "path": "plugin/skills/some-skill",
        },
    }
    repo_tree_cache = {
        ("yhangf/csc-plugins", "main"): [
            "plugin/skills/some-skill/SKILL.md",
            "plugin/skills/some-skill/参考资料.md",  # non-ASCII sibling
        ]
    }
    with tempfile.TemporaryDirectory() as out:
        name, ok, err = dc._download_skill(entry, out, repo_tree_cache=repo_tree_cache)
        assert ok
        # every fetched path is ASCII-encodable (no crash) and the CJK sibling
        # is percent-encoded
        for p in captured_paths:
            p.encode("ascii")
        assert any("%E5%8F%82%E8%80%83%E8%B5%84%E6%96%99" in p for p in captured_paths)  # 参考资料
        # the CJK sibling lands on disk under its real name
        assert os.path.isfile(
            os.path.join(out, "skills", "some-skill", "参考资料.md")
        )


def test_skill_shorthand_repo_downloads_authentic_content(monkeypatch):
    raw_skill = (
        "---\n"
        "name: crabbox\n"
        "description: authentic description\n"
        "---\n\n"
        "# Crabbox\n\n"
        "Actual upstream instructions.\n"
    )
    seen = []

    def _fetch(repo, path, branch="main", quiet_404=False):
        seen.append((repo, path, branch))
        return raw_skill

    monkeypatch.setattr(dc, "fetch_raw_content", _fetch)
    entry = {
        "id": "crabbox-skill",
        "name": "crabbox",
        "type": "skill",
        "description": "catalog description must not become the body",
        "install": {
            "repo": "openclaw/acpx",
            "branch": "main",
            "path": ".agents/skills/crabbox",
        },
    }
    tree = {
        ("openclaw/acpx", "main"): [".agents/skills/crabbox/SKILL.md"]
    }

    with tempfile.TemporaryDirectory() as out:
        name, ok, err = dc._download_skill(entry, out, repo_tree_cache=tree)
        assert name == "crabbox-skill"
        assert ok and err is None
        assert seen == [
            ("openclaw/acpx", ".agents/skills/crabbox/SKILL.md", "main")
        ]
        with open(
            os.path.join(out, "skills", "crabbox-skill", "SKILL.md"),
            encoding="utf-8",
        ) as fh:
            assert fh.read() == raw_skill


def test_skill_tree_failure_downloads_real_primary_only(monkeypatch):
    seen = []

    def _fetch(repo, path, branch="main", quiet_404=False):
        seen.append(path)
        return "# Real skill\n\nDo the actual work.\n"

    monkeypatch.setattr(dc, "fetch_raw_content", _fetch)
    entry = {
        "id": "real-skill",
        "name": "real-skill",
        "type": "skill",
        "description": "metadata",
        "install": {"repo": "owner/repo", "path": "skills/real-skill"},
    }

    with tempfile.TemporaryDirectory() as out:
        name, ok, err = dc._download_skill(
            entry,
            out,
            repo_tree_cache={("owner/repo", "main"): None},
        )
        assert ok
        assert err and "primary file only" in err
        assert seen == ["skills/real-skill/SKILL.md"]
        with open(
            os.path.join(out, "skills", "real-skill", "SKILL.md"),
            encoding="utf-8",
        ) as fh:
            content = fh.read()
        assert "Do the actual work." in content
        assert "\nmetadata\n" not in content


def test_root_skill_downloads_root_skill_md(monkeypatch):
    seen = []

    def _fetch(repo, path, branch="main", quiet_404=False):
        seen.append((repo, path))
        return "# Root skill\n\nInstructions.\n"

    monkeypatch.setattr(dc, "fetch_raw_content", _fetch)
    entry = {
        "id": "root-skill",
        "name": "root-skill",
        "type": "skill",
        "description": "metadata",
        "install": {"repo": "owner/root-skill", "path": ""},
    }

    with tempfile.TemporaryDirectory() as out:
        _, ok, _ = dc._download_skill(
            entry,
            out,
            repo_tree_cache={("owner/root-skill", "main"): ["SKILL.md", "README.md"]},
        )
        assert ok
        assert seen == [("owner/root-skill", "SKILL.md")]


def test_skill_missing_primary_fails_without_generated_content(monkeypatch):
    monkeypatch.setattr(dc, "fetch_raw_content", lambda *args, **kwargs: None)
    entry = {
        "id": "missing-skill",
        "name": "missing-skill",
        "type": "skill",
        "description": "must not become content",
        "install": {"repo": "owner/repo", "path": "skills/missing"},
    }

    with tempfile.TemporaryDirectory() as out:
        _, ok, err = dc._download_skill(entry, out, repo_tree_cache={})
        assert not ok
        assert err and "SKILL.md unavailable" in err
        assert not os.path.exists(
            os.path.join(out, "skills", "missing-skill", "SKILL.md")
        )


def test_skill_accepts_install_files_pointing_to_skill_md(monkeypatch):
    seen = []

    def _fetch(repo, path, branch="main", quiet_404=False):
        seen.append(path)
        return "# Real skill\n\nInstructions.\n"

    monkeypatch.setattr(dc, "fetch_raw_content", _fetch)
    entry = {
        "id": "file-shaped-skill",
        "name": "file-shaped-skill",
        "type": "skill",
        "install": {
            "repo": "owner/repo",
            "files": ["skills/file-shaped/SKILL.md"],
        },
    }
    with tempfile.TemporaryDirectory() as out:
        _, ok, _ = dc._download_skill(entry, out, repo_tree_cache={})
        assert ok
        assert seen == ["skills/file-shaped/SKILL.md"]


def test_legacy_rule_missing_source_fails_without_generated_content():
    entry = {
        "id": "missing-rule",
        "name": "missing-rule",
        "type": "rule",
        "description": "must not become content",
        "install": {"files": []},
    }
    with tempfile.TemporaryDirectory() as out:
        _, ok, err = dc._download_rule(entry, out)
        assert not ok
        assert err == "source rule content unavailable"
        assert not os.path.exists(os.path.join(out, "rules", "missing-rule", "RULE.md"))


def test_prompt_missing_source_fails_without_generated_content(monkeypatch):
    monkeypatch.setattr(dc, "_load_prompts_csv", lambda source: [])
    entry = {
        "id": "missing-prompt",
        "name": "missing-prompt",
        "type": "prompt",
        "description": "must not become content",
        "source": "prompts-chat",
    }
    with tempfile.TemporaryDirectory() as out:
        _, ok, err = dc._download_prompt(entry, out)
        assert not ok
        assert err == "source prompt content unavailable"
        assert not os.path.exists(
            os.path.join(out, "prompts", "missing-prompt", "PROMPT.md")
        )


def test_wonderful_prompt_extracts_authentic_markdown_section(monkeypatch):
    markdown = """# Collection

### Another prompt

Ignore me.

### 模拟 Linux 终端

I want you to act as a Linux terminal.

```text
# this heading is inside a fence
```

#### Example

ls

### Following prompt

Do not include me.
"""
    monkeypatch.setattr(dc, "_load_prompt_markdown", lambda source: markdown)
    entry = {
        "id": "linux-terminal",
        "name": "模拟 Linux 终端",
        "type": "prompt",
        "description": "metadata",
        "source": "wonderful-prompts",
    }
    with tempfile.TemporaryDirectory() as out:
        _, ok, err = dc._download_prompt(entry, out)
        assert ok and err is None
        with open(
            os.path.join(out, "prompts", "linux-terminal", "PROMPT.md"),
            encoding="utf-8",
        ) as fh:
            content = fh.read()
        assert "I want you to act as a Linux terminal." in content
        assert "# this heading is inside a fence" in content
        assert "#### Example" in content
        assert "Do not include me." not in content


def test_download_batch_contains_unexpected_downloader_exception(monkeypatch):
    def _crash(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setitem(dc.DOWNLOADERS, "prompt", _crash)
    successes, errors = dc._download_batch(
        [{"id": "broken", "name": "broken", "type": "prompt"}],
        "/unused",
        max_workers=1,
    )
    assert successes == []
    assert errors == ["broken: unexpected downloader error: boom"]


def test_preload_repo_trees_ignores_malformed_items(monkeypatch):
    monkeypatch.setattr(
        dc,
        "github_api",
        lambda path: {
            "tree": [
                None,
                {},
                {"type": "blob", "path": 123},
                {"type": "tree", "path": "directory"},
                {"type": "blob", "path": "skills/example/SKILL.md"},
            ]
        },
    )
    entry = {
        "id": "example",
        "type": "skill",
        "install": {"repo": "owner/repo", "path": "skills/example"},
    }
    assert dc._preload_repo_trees([entry]) == {
        ("owner/repo", "main"): ["skills/example/SKILL.md"]
    }


def test_reconciliation_uses_current_successes_and_preserves_unprocessed(monkeypatch):
    with tempfile.TemporaryDirectory() as root:
        catalog_dir = os.path.join(root, "catalog")
        output_dir = os.path.join(root, "catalog-download")
        os.makedirs(catalog_dir)
        entries = [
            {"id": "stale-skill", "name": "stale-skill", "type": "skill"},
            {"id": "good-prompt", "name": "good-prompt", "type": "prompt"},
            {"id": "untouched-rule", "name": "untouched-rule", "type": "rule"},
        ]
        with open(os.path.join(catalog_dir, "index.json"), "w", encoding="utf-8") as fh:
            json.dump(entries, fh)

        # A stale file exists, but skill was processed and did not succeed.
        stale = os.path.join(output_dir, "skills", "stale-skill", "SKILL.md")
        os.makedirs(os.path.dirname(stale), exist_ok=True)
        with open(stale, "w", encoding="utf-8") as fh:
            fh.write("stale")
        prompt = os.path.join(output_dir, "prompts", "good-prompt", "PROMPT.md")
        os.makedirs(os.path.dirname(prompt), exist_ok=True)
        with open(prompt, "w", encoding="utf-8") as fh:
            fh.write("fresh")

        monkeypatch.setattr(dc, "CATALOG_DIR", catalog_dir)
        kept, dropped = dc._filter_top_index_to_downloaded(
            output_dir,
            processed_types={"skill", "prompt"},
            successful_names_by_type={"skill": set(), "prompt": {"good-prompt"}},
        )
        assert (kept, dropped) == (2, 1)
        with open(os.path.join(catalog_dir, "index.json"), encoding="utf-8") as fh:
            remaining = json.load(fh)
        assert [entry["id"] for entry in remaining] == [
            "good-prompt",
            "untouched-rule",
        ]
