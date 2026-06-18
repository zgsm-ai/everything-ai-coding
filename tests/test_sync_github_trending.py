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
    kind, _, meta = t.classify_repo("o/r", "main", lambda r, b: paths)
    assert kind == expected_kind
    # meta 报告整棵树规模 + SKILL.md 数（Part 1 megaapp 预过滤的免费信号）
    assert meta["total_files"] == len(paths)
    assert meta["skill_count"] == sum(
        1 for p in paths if p.upper().endswith("SKILL.MD")
    )


def test_classify_plugin_wins_over_skill():
    """既含 marketplace.json 又含 SKILL.md → 路由 plugin（bundled skill 交下游合成）。"""
    paths = [".claude-plugin/marketplace.json", "skills/a/SKILL.md"]
    kind, skill_paths, meta = t.classify_repo("o/r", "main", lambda r, b: paths)
    assert kind == "plugin"
    assert skill_paths == []
    # plugin 仍报告 skill_count（这里有 1 个 SKILL.md），但 plugin 路径不跑 megaapp 过滤
    assert meta["skill_count"] == 1


# --- Part 1：megaapp 廉价预过滤（实测样本校准）-----------------------------

@pytest.mark.parametrize("name,total,skills,topics,expected_drop", [
    # app：文件极多 + 密度极低 + 无 skill topic → 丢
    ("openclaw", 20116, 113, [], True),
    # 真 skill 集合：文件少 → 保留（即使密度低）
    ("graphify", 579, 1, [], False),
    ("gstack", 1162, 59, [], False),
    ("anthropics-skills", 398, 18, [], False),
    ("taste-skill", 41, 13, [], False),
    # 模糊样本：文件多但密度不够低（hermes 34‰）/ 文件不够多（deer-flow 1323）→ 放行交 LLM
    ("hermes-agent", 5122, 174, [], False),
    ("deer-flow", 1323, 25, [], False),
    # 文件极多但有强 skill topic → 正信号 override，不丢
    ("big-but-tagged", 20116, 113, ["claude-skill"], False),
    ("big-but-plugin-topic", 30000, 5, ["claude-plugin"], False),
])
def test_is_megaapp_empirical(name, total, skills, topics, expected_drop):
    assert t.is_megaapp(total, skills, topics) is expected_drop


def test_is_megaapp_firecrawl_like():
    """firecrawl 这类巨型 app（很多文件、零/极少 SKILL.md、无 skill topic）→ 丢。"""
    assert t.is_megaapp(8000, 2, ["scraping", "crawler"]) is True


def test_is_megaapp_topic_override_case_insensitive():
    """topic 大小写不敏感地 override。"""
    assert t.is_megaapp(50000, 1, ["Claude-Skill"]) is False


def test_skill_density_permille():
    assert t._skill_density_permille(0, 5) == 0.0
    assert t._skill_density_permille(1000, 50) == 50.0
    assert round(t._skill_density_permille(20116, 113), 1) == 5.6


# --- Stage A：discover_candidates 纯搜索（零 Tree）-------------------------

def _setup_stage_a(monkeypatch, candidates_map, known=None):
    """注入 Stage A 依赖：known_repos + collect_candidates（纯搜索，无 Tree）。

    candidates_map: {full_name: search_item}。返回记录已发起的 Tree 调用列表
    （应始终为空 —— Stage A 不许拉任何 Tree）。
    """
    monkeypatch.setattr(t, "build_known_repos", lambda: known or set())
    monkeypatch.setattr(
        t, "collect_candidates",
        lambda *a, **k: (dict(candidates_map),
                         {"raw": len(candidates_map), "prefiltered_known": 0,
                          "below_min_stars": 0}),
    )
    tree_calls = []
    monkeypatch.setattr(
        t, "list_repo_files",
        lambda *a, **k: tree_calls.append(a) or pytest.fail("Stage A 不许拉 Tree"),
    )
    # classify_repo / build_skill_entries / sync_plugins 也不该在 Stage A 调用
    monkeypatch.setattr(t, "classify_repo", lambda *a, **k: pytest.fail("Stage A 不许 classify"))
    monkeypatch.setattr(t, "build_skill_entries", lambda *a, **k: pytest.fail("Stage A 不许 build"))
    # 默认无 seed（避免读真实 seed 文件触发网络）；seed 专项测试单独注入。
    monkeypatch.setattr(t, "load_seed_repos", lambda *a, **k: [])
    return tree_calls


def test_discover_candidates_search_only_no_tree(monkeypatch):
    """Stage A 只产候选表，零 Tree / 零 classify / 零 build。候选含零成本字段。"""
    cmap = {
        "a/s500": {"full_name": "a/s500", "stargazers_count": 500,
                   "default_branch": "main", "pushed_at": "2026-06-01T00:00:00Z",
                   "topics": ["claude-skill"], "description": "a coding skill"},
        "b/s100": {"full_name": "b/s100", "stargazers_count": 100,
                   "default_branch": "master", "pushed_at": "2026-05-01T00:00:00Z",
                   "topics": [], "description": "another"},
    }
    _setup_stage_a(monkeypatch, cmap)
    candidates, stats = t.discover_candidates()
    # 按 stars 降序
    assert [c["full_name"] for c in candidates] == ["a/s500", "b/s100"]
    # 候选表只带零成本字段
    top = candidates[0]
    assert top == {
        "full_name": "a/s500", "stars": 500, "default_branch": "main",
        "pushed_at": "2026-06-01T00:00:00Z", "topics": ["claude-skill"],
        "description": "a coding skill",
    }
    assert stats["candidates"] == 2
    assert stats["deferred"] == 0


def test_discover_candidates_limits_to_top_n_by_stars(monkeypatch):
    """候选超过 max_verify → 只保留 stars 最高的前 N，其余推迟（deferred），零 Tree。"""
    cmap = {f"o/r{s}": {"full_name": f"o/r{s}", "stargazers_count": s,
                        "default_branch": "main", "pushed_at": "", "topics": [],
                        "description": ""}
            for s in (10, 500, 50, 900, 100)}
    _setup_stage_a(monkeypatch, cmap)
    candidates, stats = t.discover_candidates(max_verify=2)
    assert [c["full_name"] for c in candidates] == ["o/r900", "o/r500"]
    assert stats["deferred"] == 3
    assert stats["candidates"] == 2


def test_discover_candidates_max_verify_zero_unlimited(monkeypatch):
    cmap = {f"o/r{i}": {"full_name": f"o/r{i}", "stargazers_count": 100 + i,
                        "default_branch": "main", "pushed_at": "", "topics": [],
                        "description": ""}
            for i in range(5)}
    _setup_stage_a(monkeypatch, cmap)
    candidates, stats = t.discover_candidates(max_verify=0)
    assert stats["deferred"] == 0
    assert stats["candidates"] == 5


# --- 手工 seed 仓清单 ------------------------------------------------------

def test_load_seed_repos_string_and_object(tmp_path):
    """seed 元素支持 'owner/repo' 字符串 + {repo, branch} 对象两种形式。"""
    p = tmp_path / "seed.json"
    p.write_text(json.dumps({
        "_comment": "ignore me",
        "repos": [
            "mattpocock/skills",
            {"repo": "foo/bar", "branch": "dev"},
            {"repo": "baz/qux"},          # 对象无 branch → None
            "   spaced/repo   ",          # 前后空白被 strip
            "notaslug",                   # 无 / → 丢
            {"repo": ""},                 # 空 repo → 丢
            123,                          # 非 str/dict → 丢
        ],
    }), encoding="utf-8")
    seeds = t.load_seed_repos(str(p))
    assert seeds == [
        {"repo": "mattpocock/skills", "branch": None},
        {"repo": "foo/bar", "branch": "dev"},
        {"repo": "baz/qux", "branch": None},
        {"repo": "spaced/repo", "branch": None},
    ]


def test_load_seed_repos_bare_array(tmp_path):
    """顶层直接是数组（无 repos 包裹）也能解析。"""
    p = tmp_path / "seed.json"
    p.write_text(json.dumps(["a/b", {"repo": "c/d"}]), encoding="utf-8")
    assert t.load_seed_repos(str(p)) == [
        {"repo": "a/b", "branch": None},
        {"repo": "c/d", "branch": None},
    ]


def test_load_seed_repos_missing_or_broken(tmp_path):
    """文件缺失 / 损坏 / 空 → 返回空列表，不崩。"""
    assert t.load_seed_repos(str(tmp_path / "nope.json")) == []
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert t.load_seed_repos(str(bad)) == []
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({"repos": []}), encoding="utf-8")
    assert t.load_seed_repos(str(empty)) == []


def test_fetch_seed_candidate_isomorphic_to_search_item():
    """seed 元数据组装成与 search item 同构的候选 dict。"""
    def api(path):
        assert path == "repos/mattpocock/skills"
        return {"full_name": "mattpocock/skills", "stargazers_count": 132733,
                "default_branch": "main", "pushed_at": "2026-06-01T00:00:00Z",
                "topics": [], "description": "Skills for Real Engineers"}
    item = t.fetch_seed_candidate("mattpocock/skills", api=api)
    assert item == {
        "full_name": "mattpocock/skills", "stargazers_count": 132733,
        "default_branch": "main", "pushed_at": "2026-06-01T00:00:00Z",
        "topics": [], "description": "Skills for Real Engineers",
    }


def test_fetch_seed_candidate_branch_override():
    """seed 显式 branch 覆盖 repo 元数据的 default_branch。"""
    api = lambda path: {"full_name": "o/r", "stargazers_count": 5,
                        "default_branch": "main", "pushed_at": "",
                        "topics": [], "description": ""}
    item = t.fetch_seed_candidate("o/r", branch="dev", api=api)
    assert item["default_branch"] == "dev"


def test_fetch_seed_candidate_failure_returns_none():
    """元数据拉取失败（None / 非 dict）→ 返回 None，不崩。"""
    assert t.fetch_seed_candidate("o/r", api=lambda path: None) is None
    assert t.fetch_seed_candidate("o/r", api=lambda path: []) is None


def test_collect_seed_candidates_skips_known_and_failures():
    """已收录的 seed 被 known_repos 跳过；拉取失败的 WARN 跳过、不崩。"""
    def api(path):
        if "o/good" in path:
            return {"full_name": "o/good", "stargazers_count": 10,
                    "default_branch": "main", "pushed_at": "", "topics": [],
                    "description": ""}
        return None  # o/dead 拉取失败
    seeds = [
        {"repo": "o/good", "branch": None},
        {"repo": "Already/Known", "branch": None},   # 大小写归一后命中 known
        {"repo": "o/dead", "branch": None},          # 拉取失败
    ]
    items, stats = t.collect_seed_candidates(seeds, {"already/known"}, api=api)
    assert [it["full_name"] for it in items] == ["o/good"]
    assert stats == {"loaded": 3, "skipped_known": 1, "fetch_failed": 1}


def test_discover_candidates_seed_exempt_from_cap(monkeypatch):
    """seed 候选豁免 MAX_VERIFY 截断：小 cap 下搜索候选被砍，seed 仍在候选表。"""
    cmap = {f"o/r{s}": {"full_name": f"o/r{s}", "stargazers_count": s,
                        "default_branch": "main", "pushed_at": "", "topics": [],
                        "description": ""}
            for s in (900, 500, 100)}
    _setup_stage_a(monkeypatch, cmap)
    # 注入 seed：一个低星仓（远低于被保留的搜索候选），仍必须进候选表。
    monkeypatch.setattr(t, "load_seed_repos",
                        lambda *a, **k: [{"repo": "seed/low", "branch": None}])
    monkeypatch.setattr(t, "fetch_seed_candidate",
                        lambda slug, branch=None, api=None: {
                            "full_name": "seed/low", "stargazers_count": 3,
                            "default_branch": "main", "pushed_at": "",
                            "topics": [], "description": ""})
    candidates, stats = t.discover_candidates(max_verify=1)
    names = {c["full_name"] for c in candidates}
    # cap=1 只保留 stars 最高 o/r900；seed/low 豁免 cap 仍进
    assert names == {"o/r900", "seed/low"}
    assert stats["seed_injected"] == 1
    assert stats["deferred"] == 2  # o/r500, o/r100 被推迟


def test_discover_candidates_seed_dedup_with_search(monkeypatch):
    """seed 与搜索结果重叠 → 按 full_name 去重，不重复进候选表。"""
    cmap = {"o/dup": {"full_name": "o/dup", "stargazers_count": 500,
                      "default_branch": "main", "pushed_at": "", "topics": [],
                      "description": "from search"}}
    _setup_stage_a(monkeypatch, cmap)
    monkeypatch.setattr(t, "load_seed_repos",
                        lambda *a, **k: [{"repo": "O/Dup", "branch": None}])
    monkeypatch.setattr(t, "fetch_seed_candidate",
                        lambda slug, branch=None, api=None: {
                            "full_name": "o/dup", "stargazers_count": 500,
                            "default_branch": "main", "pushed_at": "",
                            "topics": [], "description": "from seed"})
    candidates, stats = t.discover_candidates(max_verify=0)
    assert [c["full_name"] for c in candidates] == ["o/dup"]
    assert stats["seed_injected"] == 0  # 已在搜索候选表，去重


def test_discover_candidates_seed_known_skipped(monkeypatch):
    """已在 catalog（known_repos）的 seed 被 collect_seed_candidates 跳过、不注入。"""
    _setup_stage_a(monkeypatch, {}, known={"seed/known"})
    monkeypatch.setattr(t, "load_seed_repos",
                        lambda *a, **k: [{"repo": "Seed/Known", "branch": None}])
    # 已在 known，不该 fetch
    monkeypatch.setattr(t, "fetch_seed_candidate",
                        lambda *a, **k: pytest.fail("known seed 不该 fetch"))
    candidates, stats = t.discover_candidates(max_verify=0)
    assert candidates == []
    assert stats["seed_injected"] == 0
    assert stats["seed_skipped_known"] == 1


def test_discover_candidates_seed_fetch_failure_no_crash(monkeypatch):
    """seed 元数据拉取失败 → 跳过该 seed、不崩，其余候选正常。"""
    cmap = {"o/r": {"full_name": "o/r", "stargazers_count": 100,
                    "default_branch": "main", "pushed_at": "", "topics": [],
                    "description": ""}}
    _setup_stage_a(monkeypatch, cmap)
    monkeypatch.setattr(t, "load_seed_repos",
                        lambda *a, **k: [{"repo": "seed/dead", "branch": None}])
    monkeypatch.setattr(t, "fetch_seed_candidate",
                        lambda *a, **k: None)  # 拉取失败
    candidates, stats = t.discover_candidates(max_verify=0)
    assert {c["full_name"] for c in candidates} == {"o/r"}
    assert stats["seed_injected"] == 0
    assert stats["seed_fetch_failed"] == 1


def test_save_load_candidates_roundtrip(tmp_path):
    path = str(tmp_path / "candidates.json")
    cands = [{"full_name": "o/r", "stars": 100, "default_branch": "main",
              "pushed_at": "", "topics": [], "description": "x"}]
    t.save_candidates(cands, path)
    assert t.load_candidates(path) == cands


def test_load_candidates_missing_returns_empty(tmp_path):
    assert t.load_candidates(str(tmp_path / "nope.json")) == []


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


# --- 促升清单：加载 + schema 校验 + per-repo source 覆盖 --------------------

def test_load_promoted_repos_valid(tmp_path):
    """促升清单正常加载：合法字段全保留，label/url 缺省回填。"""
    p = tmp_path / "promote.json"
    p.write_text(json.dumps({
        "_comment": "ignore me",
        "repos": [
            {"repo": "ComposioHQ/awesome-codex-skills",
             "source_slug": "composiohq/awesome-codex-skills",
             "label": "Composio Codex", "url": "https://github.com/ComposioHQ/awesome-codex-skills",
             "type": "skill", "trust": 3},
            {"repo": "browserbase/skills", "source_slug": "browserbase/skills",
             "type": "plugin"},  # label/url/trust 缺省
        ],
    }), encoding="utf-8")
    promoted = t.load_promoted_repos(str(p))
    assert promoted == [
        {"repo": "ComposioHQ/awesome-codex-skills",
         "source_slug": "composiohq/awesome-codex-skills",
         "label": "Composio Codex",
         "url": "https://github.com/ComposioHQ/awesome-codex-skills",
         "type": "skill", "trust": 3},
        {"repo": "browserbase/skills", "source_slug": "browserbase/skills",
         "label": "browserbase/skills",                       # label 缺省 → source_slug
         "url": "https://github.com/browserbase/skills",       # url 缺省 → 拼 repo
         "type": "plugin", "trust": 3},                        # trust 缺省 → 3
    ]


def test_load_promoted_repos_schema_validation(tmp_path):
    """schema 校验：缺 repo/source_slug/type、type 非法、非 owner/repo 的条目被丢。"""
    p = tmp_path / "promote.json"
    p.write_text(json.dumps({"repos": [
        {"repo": "o/r", "source_slug": "o/r", "type": "skill"},     # 合法
        {"source_slug": "x/y", "type": "skill"},                    # 缺 repo
        {"repo": "a/b", "type": "skill"},                           # 缺 source_slug
        {"repo": "a/b", "source_slug": "a/b"},                      # 缺 type
        {"repo": "a/b", "source_slug": "a/b", "type": "mcp"},       # type 非法
        {"repo": "noslug", "source_slug": "a/b", "type": "skill"},  # repo 非 owner/repo
        {"repo": "a/b", "source_slug": "noslug", "type": "skill"},  # slug 非 owner/repo
        "not-a-dict",                                               # 非 dict
    ]}), encoding="utf-8")
    promoted = t.load_promoted_repos(str(p))
    assert [pr["repo"] for pr in promoted] == ["o/r"]


def test_load_promoted_repos_missing_or_broken(tmp_path):
    """文件缺失 / 损坏 / 空 → 返回空列表，不崩。"""
    assert t.load_promoted_repos(str(tmp_path / "nope.json")) == []
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert t.load_promoted_repos(str(bad)) == []
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({"repos": []}), encoding="utf-8")
    assert t.load_promoted_repos(str(empty)) == []


def test_build_promoted_map_lowercases_full_name(tmp_path):
    """promote map 的 key 是小写 full_name，值是清单里的（小写）source_slug。"""
    p = tmp_path / "promote.json"
    p.write_text(json.dumps({"repos": [
        {"repo": "ComposioHQ/Awesome-Codex-Skills",
         "source_slug": "composiohq/awesome-codex-skills", "type": "skill"},
    ]}), encoding="utf-8")
    m = t.build_promoted_map(str(p))
    assert m == {"composiohq/awesome-codex-skills": "composiohq/awesome-codex-skills"}


def test_build_skill_entries_default_source(monkeypatch):
    """未传 source_id → 默认 github-trending（向后兼容）。"""
    monkeypatch.setattr(t.skill_registry, "scan_repo_via_api", lambda repo, branch: [
        {"name": "S", "description": "a coding skill long enough description here",
         "category": "", "tags": [], "skill_dir": "s"},
    ])
    entries = t.build_skill_entries("foo/bar", "main", _item("foo/bar", stars=120), "2026-06-16")
    assert entries[0]["source"] == "github-trending"


def test_build_skill_entries_per_repo_source_override(monkeypatch):
    """促升仓：build_skill_entries 接受 source_id → entry 带专属 per-repo slug。"""
    monkeypatch.setattr(t.skill_registry, "scan_repo_via_api", lambda repo, branch: [
        {"name": "S", "description": "a coding skill long enough description here",
         "category": "", "tags": [], "skill_dir": "s"},
    ])
    entries = t.build_skill_entries(
        "google/skills", "main", _item("google/skills", stars=13800),
        "2026-06-16", source_id="google/skills",
    )
    assert entries[0]["source"] == "google/skills"


def test_real_promoted_repos_json_loads():
    """仓内真实促升清单加载正确（含 mattpocock/skills、browserbase plugin）。"""
    promoted = t.load_promoted_repos()
    slugs = {pr["source_slug"] for pr in promoted}
    assert "mattpocock/skills" in slugs                    # 首次入库即带专属 slug
    assert "composiohq/awesome-codex-skills" in slugs
    # browserbase 走 plugin 路由，登记 type=plugin
    bb = next(pr for pr in promoted if pr["repo"] == "browserbase/skills")
    assert bb["type"] == "plugin"
    # 全部 trust=3、source_slug 全小写
    for pr in promoted:
        assert pr["trust"] == 3
        assert pr["source_slug"] == pr["source_slug"].lower()


def test_save_verify_cache_best_effort_on_write_failure(monkeypatch, tmp_path):
    """cache 写失败要 best-effort 不崩（OSError 被吞）。"""
    bad_dir = tmp_path / "nope"
    bad_path = bad_dir / "verify_cache.json"
    monkeypatch.setattr(t, "CACHE_DIR", "/dev/null/cannot-mkdir")
    monkeypatch.setattr(t, "VERIFY_CACHE_PATH", str(bad_path))
    # 不应抛
    t.save_verify_cache({"o/r": {"kind": "skill"}})
