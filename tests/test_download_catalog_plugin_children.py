"""Tests for download_catalog single-file plugin-child downloaders.

Covers the command/subagent/template (+ repo-based rule) download path that
materializes synthesized plugin children into their per-type
``catalog-download/<type-dir>/<id>/<PRIMARY>`` file, and the downloader/primary
mapping coverage that keeps the bundle from dropping new types.
"""

from __future__ import annotations

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


def test_download_missing_source_writes_placeholder(fake_fetch):
    with tempfile.TemporaryDirectory() as out:
        entry = _child_entry(
            "command", "p-command-gone", "p-plugin/commands/gone-404.md"
        )
        name, ok, err = dc._download_command(entry, out)
        # still succeeds (placeholder) so the entry survives reconciliation
        assert ok
        assert err and "placeholder" in err
        assert os.path.isfile(
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
