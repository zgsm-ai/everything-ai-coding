"""sync_github_trending 单测：发现 / known_repos 预过滤（去重主防线）/ 结构验证 / merge。

全程注入 fake api / monkeypatch，无网络。
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import sync_github_trending as t  # noqa: E402


# --- owner/repo 解析 + 镜像归一 -------------------------------------------

@pytest.mark.parametrize("url,expected", [
    ("https://github.com/Owner/Repo", "owner/repo"),
    ("https://github.com/Owner/Repo.git", "owner/repo"),
    ("https://github.com/Owner/Repo/tree/main/skills/x", "owner/repo"),
    ("https://github.com/Owner/Repo/blob/HEAD/a.md", "owner/repo"),
    ("https://example.com/not/github", None),
    ("", None),
    # 镜像归一到 canonical
    ("https://github.com/sickn33/antigravity-awesome-skills/tree/main/skills/foo",
     "anthropics/skills"),
])
def test_owner_repo_from_url(url, expected):
    assert t.owner_repo_from_url(url) == expected


# --- known_repos 双路提取 + 失败不静默 ------------------------------------

def _write_index(tmp_path, name, entries):
    p = tmp_path / name
    p.write_text(json.dumps(entries), encoding="utf-8")
    return str(p)


def test_build_known_repos_dual_path(tmp_path):
    """source_url 反解 + install.marketplace_repo 双路都要进 known_repos。"""
    idx = _write_index(tmp_path, "index.json", [
        {"type": "skill", "source_url": "https://github.com/Foo/Bar/tree/main/skills/a"},
        # plugin 容器仓：source_url 指向被打包的真仓，repo 身份只在 marketplace_repo
        {"type": "plugin",
         "source_url": "https://github.com/someone/packaged.git",
         "install": {"marketplace_repo": "obra/superpowers-marketplace"}},
    ])
    known = t.build_known_repos([idx])
    assert "foo/bar" in known                          # source_url 路
    assert "someone/packaged" in known                 # source_url 路（被打包仓）
    assert "obra/superpowers-marketplace" in known     # marketplace_repo 路（容器仓盲区）


def test_build_known_repos_raises_when_no_index(tmp_path):
    """没有任何 index 可读时必须 raise，不能静默退化成空 set（否则预过滤失效）。"""
    with pytest.raises(RuntimeError):
        t.build_known_repos([str(tmp_path / "nonexistent.json")])


# --- 发现预过滤：去重主防线（含跨类型地雷）---------------------------------

def _fake_api(items_by_query):
    """返回一个 fake github_api：按 query 中的关键词返回对应 items（单页）。"""
    def api(path):
        for key, items in items_by_query.items():
            if key in path:
                return {"items": items}
        return {"items": []}
    return api


def _item(full_name, stars=100, branch="main"):
    return {"full_name": full_name, "stargazers_count": stars,
            "default_branch": branch, "pushed_at": "2026-06-01T00:00:00Z"}


def test_collect_candidates_prefilters_known():
    """已在 known_repos 的仓必须被预过滤掉（扫描之前）。"""
    api = _fake_api({"repositories": [_item("new/repo"), _item("old/known")]})
    known = {"old/known"}
    cands, stats = t.collect_candidates(["topic:claude-skill"], known,
                                        throttle=0, api=api)
    assert "new/repo" in cands
    assert "old/known" not in cands
    assert stats["prefiltered_known"] == 1


def test_collect_candidates_cross_type_landmine():
    """核心验收：一个仓只以 plugin 形式在库，被当 skill 搜到时也必须被预过滤
    —— 否则会产生 deduplicate() 抓不住的跨类型重复（30 地雷场景）。"""
    # known_repos 来自一个"仅 plugin"的现有条目（如 claude-plugins-dev 收的 superpowers）
    api = _fake_api({"repositories": [_item("obra/superpowers")]})
    known = {"obra/superpowers"}  # 仅以 plugin 存在
    cands, stats = t.collect_candidates(["topic:claude-skill"], known,
                                        throttle=0, api=api)
    assert cands == {}                       # 被预过滤，不会再当 skill 发现
    assert stats["prefiltered_known"] == 1


def test_collect_candidates_skips_below_min_stars_and_dedups():
    api = _fake_api({"repositories": [
        _item("a/high", stars=500),
        _item("b/low", stars=10),
        _item("a/high", stars=500),  # 跨查询重复
    ]})
    cands, stats = t.collect_candidates(["topic:claude-skill"], set(),
                                        min_stars=50, throttle=0, api=api)
    assert set(cands) == {"a/high"}
    assert stats["below_min_stars"] == 1


# --- 结构验证路由 ----------------------------------------------------------

@pytest.mark.parametrize("paths,expected_kind", [
    ([".claude-plugin/marketplace.json", "README.md"], "plugin"),
    (["marketplace.json"], "plugin"),
    (["skills/foo/SKILL.md", "x.py"], "skill"),
    (["nested/deep/SKILL.md"], "skill"),
    (["main.py", "README.md"], None),         # 越界工具：俩都没有
    ([], None),
])
def test_classify_repo(paths, expected_kind):
    kind, _ = t.classify_repo("o/r", "main", lambda r, b: paths)
    assert kind == expected_kind


def test_classify_plugin_wins_over_skill():
    """既含 marketplace.json 又含 SKILL.md → 路由 plugin（bundled skill 交下游合成）。"""
    paths = [".claude-plugin/marketplace.json", "skills/a/SKILL.md"]
    kind, skill_paths = t.classify_repo("o/r", "main", lambda r, b: paths)
    assert kind == "plugin"
    assert skill_paths == []


# --- merge-preserve --------------------------------------------------------

def test_merge_preserve_id_and_url_dedup():
    existing = [{"id": "x-skill", "source_url": "https://github.com/o/r/tree/main/a"}]
    new = [
        {"id": "x-skill", "source_url": "https://github.com/o/r/tree/main/a"},  # id 撞
        {"id": "y-skill", "source_url": "https://github.com/o/r/tree/main/a"},  # url 撞
        {"id": "z-skill", "source_url": "https://github.com/o/r/tree/main/b"},  # 全新
    ]
    combined, accepted = t.merge_preserve(new, existing, dedup_url=True)
    assert accepted == 1
    assert {e["id"] for e in combined} == {"x-skill", "z-skill"}


def test_merge_preserve_plugin_url_not_deduped():
    """plugin 传 dedup_url=False：同 monorepo 多 plugin 合法共享 URL，不应被 URL 去重。"""
    existing = [{"id": "p1", "source_url": "https://github.com/o/mono.git"}]
    new = [{"id": "p2", "source_url": "https://github.com/o/mono.git"}]  # 同 url 不同 id
    combined, accepted = t.merge_preserve(new, existing, dedup_url=False)
    assert accepted == 1
    assert {e["id"] for e in combined} == {"p1", "p2"}


# --- skill entry 构造（monkeypatch 扫描）----------------------------------

def test_build_skill_entries(monkeypatch):
    monkeypatch.setattr(t.skill_registry, "scan_repo_via_api", lambda repo, branch: [
        {"name": "My Skill", "description": "a coding skill for unit testing, long enough",
         "category": "", "tags": [], "skill_dir": "skills/my-skill"},
    ])
    item = _item("foo/bar", stars=120)
    entries = t.build_skill_entries("foo/bar", "main", item, "2026-06-16")
    assert len(entries) == 1
    e = entries[0]
    assert e["type"] == "skill"
    assert e["source"] == "github-trending"
    assert e["source_url"] == "https://github.com/foo/bar/tree/main/skills/my-skill"
    assert e["install"] == {"method": "git_clone", "repo": "foo/bar",
                            "branch": "main", "path": "skills/my-skill"}
    assert e["stars"] == 120


def test_build_skill_entries_hard_filter_drops_low_stars(monkeypatch):
    monkeypatch.setattr(t.skill_registry, "scan_repo_via_api", lambda repo, branch: [
        {"name": "S", "description": "a coding skill long enough description here",
         "category": "", "tags": [], "skill_dir": "s"},
    ])
    item = _item("foo/bar", stars=10)  # ≤50 → hard_filter 刷掉
    assert t.build_skill_entries("foo/bar", "main", item, "2026-06-16") == []


# --- discover() 健壮性：单仓异常不拖垮整个流程 -----------------------------

def _setup_discover_env(monkeypatch, candidates, classify_side_effect):
    """注入 discover() 的所有外部依赖（known_repos / cache / search），
    candidates 为 {full_name: item}，classify_side_effect(repo_slug)->kind 或抛异常。"""
    monkeypatch.setattr(t, "build_known_repos", lambda: set())
    monkeypatch.setattr(t, "load_verify_cache", lambda: {})
    saved = {}
    monkeypatch.setattr(t, "save_verify_cache", lambda c: saved.update({"cache": c}))
    monkeypatch.setattr(
        t, "collect_candidates",
        lambda *a, **k: (dict(candidates),
                         {"raw": len(candidates), "prefiltered_known": 0,
                          "below_min_stars": 0}),
    )

    def fake_classify(repo_slug, branch, list_files):
        return classify_side_effect(repo_slug)

    monkeypatch.setattr(t, "classify_repo", fake_classify)
    return saved


def test_discover_isolates_per_repo_exception(monkeypatch):
    """某个候选仓在结构验证 / 解析处抛异常 → discover() 不崩，
    其他候选照常产出，errored 计数正确，崩溃仓不写 cache（下次重试）。"""
    candidates = {
        "good/skill": _item("good/skill", stars=120),
        "boom/repo": _item("boom/repo", stars=200),
        "good/plugin": _item("good/plugin", stars=300),
    }

    def classify(repo_slug):
        if repo_slug == "boom/repo":
            # 模拟 fetch_raw_content 抛 http.client.RemoteDisconnected 那类瞬时网络断
            import http.client
            raise http.client.RemoteDisconnected("Remote end closed connection")
        if repo_slug == "good/plugin":
            return "plugin", []
        return "skill", ["skills/x/SKILL.md"]

    saved = _setup_discover_env(monkeypatch, candidates, classify)
    # good/skill 的 skill entry 构造也要 stub（否则会真扫描）
    monkeypatch.setattr(
        t, "build_skill_entries",
        lambda repo, branch, item, ls: [
            {"id": "x-skill", "type": "skill", "source": t.SOURCE_ID,
             "source_url": f"https://github.com/{repo}/tree/{branch}/skills/x"},
        ],
    )

    skill_entries, plugin_cfgs, stats = t.discover("2026-06-16")

    # 没崩；好仓照常产出
    assert len(skill_entries) == 1
    assert stats["skill_repos"] == 1
    assert len(plugin_cfgs) == 1
    assert stats["plugin_repos"] == 1
    # 崩溃仓被计入 errored
    assert stats["errored"] == 1
    # 崩溃仓不写 new_cache（下次重试），好仓写了
    cache = saved["cache"]
    assert "boom/repo" not in cache
    assert "good/skill" in cache
    assert "good/plugin" in cache


def test_discover_build_skill_entries_exception_counts_errored(monkeypatch):
    """异常发生在 build_skill_entries（scan/fetch 阶段）也要被 per-candidate 捕获。"""
    candidates = {"boom/skill": _item("boom/skill", stars=120)}
    saved = _setup_discover_env(
        monkeypatch, candidates, lambda r: ("skill", ["skills/x/SKILL.md"])
    )

    def boom(repo, branch, item, ls):
        import http.client
        raise http.client.RemoteDisconnected("boom")

    monkeypatch.setattr(t, "build_skill_entries", boom)

    skill_entries, plugin_cfgs, stats = t.discover("2026-06-16")
    assert skill_entries == []
    assert stats["errored"] == 1
    assert "boom/skill" not in saved["cache"]
