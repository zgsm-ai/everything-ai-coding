"""migrate_promote_sources 单测：促升清单加载 / source 改写命中 / 不误伤 / 幂等 /
--dry-run 不写盘。

全程用 tmp_path 临时 index.json，无网络、无真实 catalog 改写。
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import migrate_promote_sources as m  # noqa: E402


# --- owner/repo 反解 -------------------------------------------------------

@pytest.mark.parametrize("url,expected", [
    ("https://github.com/Google/Skills/tree/main/x", "google/skills"),
    ("https://github.com/ComposioHQ/awesome-codex-skills/tree/main/a", "composiohq/awesome-codex-skills"),
    ("https://github.com/o/r.git", "o/r"),
    ("https://example.com/not/github", None),
    ("", None),
])
def test_owner_repo_from_url(url, expected):
    assert m.owner_repo_from_url(url) == expected


# --- 促升清单加载（大小写不敏感 key）--------------------------------------

def test_load_promoted_map_lowercases_repo_key(tmp_path):
    p = tmp_path / "promote.json"
    p.write_text(json.dumps({"repos": [
        {"repo": "Google/Skills", "source_slug": "google/skills", "type": "skill"},
        {"repo": "noslug", "source_slug": "a/b", "type": "skill"},  # 非法被丢
    ]}), encoding="utf-8")
    pm = m.load_promoted_map(str(p))
    assert pm == {"google/skills": "google/skills"}


def test_load_promoted_map_missing_returns_empty(tmp_path):
    assert m.load_promoted_map(str(tmp_path / "nope.json")) == {}


# --- source 改写：命中 + 不误伤 + 幂等 -------------------------------------

def _entries():
    return [
        # 促升仓 + github-trending → 改写
        {"id": "a", "source": "github-trending",
         "source_url": "https://github.com/Google/Skills/tree/main/a"},
        # 促升仓但**已是目标 slug**（非 github-trending）→ 不动（幂等）
        {"id": "b", "source": "google/skills",
         "source_url": "https://github.com/google/skills/tree/main/b"},
        # 非促升仓 + github-trending → 不动（不误伤）
        {"id": "c", "source": "github-trending",
         "source_url": "https://github.com/random/repo/tree/main/c"},
        # 促升仓但**来源是别的源**（非 github-trending）→ 不动（不误伤别源）
        {"id": "d", "source": "skills.sh",
         "source_url": "https://github.com/google/skills/tree/main/d"},
        # 无 source_url → 不动
        {"id": "e", "source": "github-trending", "source_url": ""},
    ]


def test_migrate_entries_hits_and_no_collateral():
    pm = {"google/skills": "google/skills"}
    entries = _entries()
    changed = m.migrate_entries(entries, pm)
    assert changed == 1
    by_id = {e["id"]: e for e in entries}
    assert by_id["a"]["source"] == "google/skills"   # 改写
    assert by_id["b"]["source"] == "google/skills"   # 幂等，未重复改
    assert by_id["c"]["source"] == "github-trending" # 非促升仓不误伤
    assert by_id["d"]["source"] == "skills.sh"       # 别源不误伤
    assert by_id["e"]["source"] == "github-trending" # 无 url 不动


def test_migrate_entries_case_insensitive_match():
    """旧 entry 的 source_url 大小写各异，都收敛到统一小写 slug。"""
    pm = {"composiohq/awesome-codex-skills": "composiohq/awesome-codex-skills"}
    entries = [
        {"id": "x", "source": "github-trending",
         "source_url": "https://github.com/ComposioHQ/awesome-codex-skills/tree/main/x"},
        {"id": "y", "source": "github-trending",
         "source_url": "https://github.com/composiohq/AWESOME-CODEX-SKILLS/tree/main/y"},
    ]
    changed = m.migrate_entries(entries, pm)
    assert changed == 2
    assert all(e["source"] == "composiohq/awesome-codex-skills" for e in entries)


def test_migrate_entries_idempotent():
    """重跑不再改动。"""
    pm = {"google/skills": "google/skills"}
    entries = _entries()
    m.migrate_entries(entries, pm)
    second = m.migrate_entries(entries, pm)
    assert second == 0


# --- 文件级迁移 + dry-run --------------------------------------------------

def _write_index(tmp_path, name, entries):
    p = tmp_path / name
    p.write_text(json.dumps(entries), encoding="utf-8")
    return str(p)


def test_migrate_file_writes_when_not_dry_run(tmp_path):
    path = _write_index(tmp_path, "index.json", _entries())
    pm = {"google/skills": "google/skills"}
    changed = m.migrate_file(path, pm, dry_run=False)
    assert changed == 1
    written = json.load(open(path))
    assert {e["id"]: e["source"] for e in written}["a"] == "google/skills"


def test_migrate_file_dry_run_does_not_write(tmp_path):
    entries = _entries()
    path = _write_index(tmp_path, "index.json", entries)
    pm = {"google/skills": "google/skills"}
    changed = m.migrate_file(path, pm, dry_run=True)
    assert changed == 1  # 报告改写数
    # 但磁盘文件未变（仍是 github-trending）
    on_disk = json.load(open(path))
    assert {e["id"]: e["source"] for e in on_disk}["a"] == "github-trending"


def test_migrate_file_missing_returns_zero(tmp_path):
    assert m.migrate_file(str(tmp_path / "nope.json"), {"a/b": "a/b"}) == 0


def test_main_dry_run_against_targets(tmp_path, capsys):
    """main --dry-run：迁移多个目标文件、汇总总数、不写盘。"""
    p1 = _write_index(tmp_path, "skills.json", [
        {"id": "a", "source": "github-trending",
         "source_url": "https://github.com/google/skills/tree/main/a"},
    ])
    p2 = _write_index(tmp_path, "plugins.json", [
        {"id": "b", "source": "github-trending",
         "source_url": "https://github.com/browserbase/skills.git"},
    ])
    promote = tmp_path / "promote.json"
    promote.write_text(json.dumps({"repos": [
        {"repo": "google/skills", "source_slug": "google/skills", "type": "skill"},
        {"repo": "browserbase/skills", "source_slug": "browserbase/skills", "type": "plugin"},
    ]}), encoding="utf-8")
    rc = m.main([
        "--dry-run", "--targets", p1, p2, "--promoted", str(promote),
    ])
    assert rc == 0
    # dry-run 未写盘
    assert json.load(open(p1))[0]["source"] == "github-trending"
    assert json.load(open(p2))[0]["source"] == "github-trending"
