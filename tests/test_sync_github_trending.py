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


def test_discover_drops_megaapp_before_build(monkeypatch):
    """discover 对 megaapp 在 build_skill_entries 之前丢弃（省 API/LLM），计入 stats。"""
    candidates = {
        "openclaw/openclaw": {
            "full_name": "openclaw/openclaw", "stargazers_count": 500,
            "default_branch": "main", "pushed_at": "2026-06-01T00:00:00Z",
            "topics": [], "description": "an autonomous agent framework",
        },
        "real/skill": {
            "full_name": "real/skill", "stargazers_count": 200,
            "default_branch": "main", "pushed_at": "2026-06-01T00:00:00Z",
            "topics": [], "description": "a coding skill",
        },
    }
    monkeypatch.setattr(t, "build_known_repos", lambda: set())
    monkeypatch.setattr(t, "load_verify_cache", lambda: {})
    saved = {}
    monkeypatch.setattr(t, "save_verify_cache", lambda c: saved.update({"cache": c}))
    monkeypatch.setattr(
        t, "collect_candidates",
        lambda *a, **k: (dict(candidates),
                         {"raw": 2, "prefiltered_known": 0, "below_min_stars": 0}),
    )

    def fake_classify(repo_slug, branch, list_files):
        if repo_slug == "openclaw/openclaw":
            return "skill", ["a/SKILL.md"], {"total_files": 20116, "skill_count": 113}
        return "skill", ["a/SKILL.md"], {"total_files": 300, "skill_count": 5}

    monkeypatch.setattr(t, "classify_repo", fake_classify)

    built_calls = []

    def fake_build(repo, branch, item, ls):
        built_calls.append(repo)
        return [{"id": f"{repo.replace('/', '-')}-skill", "type": "skill",
                 "source": t.SOURCE_ID,
                 "source_url": f"https://github.com/{repo}/tree/{branch}/a"}]

    monkeypatch.setattr(t, "build_skill_entries", fake_build)

    skill_entries, plugin_cfgs, stats = t.discover("2026-06-16")

    # megaapp 在 build 之前被丢，build_skill_entries 不为它调用（省 API）
    assert "openclaw/openclaw" not in built_calls
    assert built_calls == ["real/skill"]
    assert stats["megaapp_dropped"] == 1
    assert stats["skill_repos"] == 1
    assert len(skill_entries) == 1
    # megaapp 写入 cache（kind=megaapp）避免反复 Tree
    assert saved["cache"]["openclaw/openclaw"]["kind"] == "megaapp"


def test_discover_cached_megaapp_stays_dropped(monkeypatch):
    """cache 命中 kind=megaapp 的仓：保持丢弃，不重跑 build，不误记为 discarded。"""
    item = {"full_name": "openclaw/openclaw", "stargazers_count": 500,
            "default_branch": "main", "pushed_at": "2026-06-01T00:00:00Z",
            "topics": [], "description": "agent framework"}
    monkeypatch.setattr(t, "build_known_repos", lambda: set())
    # cache 上轮记的 megaapp（pushed_at 未变 → 命中）
    monkeypatch.setattr(t, "load_verify_cache", lambda: {
        "openclaw/openclaw": {"pushed_at": "2026-06-01T00:00:00Z", "kind": "megaapp",
                              "total_files": 20116, "skill_count": 113},
    })
    saved = {}
    monkeypatch.setattr(t, "save_verify_cache", lambda c: saved.update({"cache": c}))
    monkeypatch.setattr(
        t, "collect_candidates",
        lambda *a, **k: ({"openclaw/openclaw": item},
                         {"raw": 1, "prefiltered_known": 0, "below_min_stars": 0}),
    )
    # classify_repo 不应被调（cache 命中）；build_skill_entries 也不应被调
    monkeypatch.setattr(t, "classify_repo", lambda *a, **k: pytest.fail("classify 不应被调"))
    monkeypatch.setattr(t, "build_skill_entries", lambda *a, **k: pytest.fail("build 不应被调"))

    skill_entries, plugin_cfgs, stats = t.discover("2026-06-16")
    assert skill_entries == []
    assert stats["megaapp_dropped"] == 1
    assert stats["discarded"] == 0
    assert saved["cache"]["openclaw/openclaw"]["kind"] == "megaapp"


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
            return "plugin", [], {"total_files": 50, "skill_count": 0}
        return "skill", ["skills/x/SKILL.md"], {"total_files": 100, "skill_count": 1}

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
        monkeypatch, candidates,
        lambda r: ("skill", ["skills/x/SKILL.md"], {"total_files": 100, "skill_count": 1}),
    )

    def boom(repo, branch, item, ls):
        import http.client
        raise http.client.RemoteDisconnected("boom")

    monkeypatch.setattr(t, "build_skill_entries", boom)

    skill_entries, plugin_cfgs, stats = t.discover("2026-06-16")
    assert skill_entries == []
    assert stats["errored"] == 1
    assert "boom/skill" not in saved["cache"]


# --- 每轮限量（主修超时）：只处理 top-N，按 stars 降序优先 -------------------

def test_discover_limits_to_top_n_by_stars(monkeypatch):
    """net-new 候选超过 max_verify 时，本轮只对 stars 最高的前 N 个做结构验证 + build，
    其余推迟（stats['deferred']），高星优先。"""
    # 5 个候选，stars 各不同；max_verify=2 → 只处理 stars 最高的两个
    candidates = {
        "a/s10": _item("a/s10", stars=10),
        "b/s500": _item("b/s500", stars=500),
        "c/s50": _item("c/s50", stars=50),
        "d/s900": _item("d/s900", stars=900),
        "e/s100": _item("e/s100", stars=100),
    }
    saved = _setup_discover_env(
        monkeypatch, candidates,
        lambda r: ("skill", ["skills/x/SKILL.md"], {"total_files": 100, "skill_count": 1}),
    )

    classified = []

    def fake_classify(repo_slug, branch, list_files):
        classified.append(repo_slug)
        return "skill", ["skills/x/SKILL.md"], {"total_files": 100, "skill_count": 1}

    monkeypatch.setattr(t, "classify_repo", fake_classify)

    built = []

    def fake_build(repo, branch, item, ls):
        built.append(repo)
        return [{"id": f"{repo.replace('/', '-')}-skill", "type": "skill",
                 "source": t.SOURCE_ID,
                 "source_url": f"https://github.com/{repo}/tree/{branch}/x"}]

    monkeypatch.setattr(t, "build_skill_entries", fake_build)

    skill_entries, plugin_cfgs, stats = t.discover("2026-06-16", max_verify=2)

    # 只处理 stars 最高的两个：d/s900, b/s500（按 stars 降序）
    assert classified == ["d/s900", "b/s500"]
    assert built == ["d/s900", "b/s500"]
    assert stats["skill_repos"] == 2
    assert len(skill_entries) == 2
    # 其余 3 个推迟到后续轮次（下轮 known_repos 自动推进 backlog）
    assert stats["deferred"] == 3
    # 推迟的仓不进 cache（本轮根本没验证）
    assert "a/s10" not in saved["cache"]
    assert "c/s50" not in saved["cache"]
    assert "e/s100" not in saved["cache"]


def test_discover_no_limit_when_under_max_verify(monkeypatch):
    """候选数不超过 max_verify 时全量处理，deferred=0。"""
    candidates = {
        "a/s1": _item("a/s1", stars=100),
        "b/s2": _item("b/s2", stars=200),
    }
    _setup_discover_env(
        monkeypatch, candidates,
        lambda r: ("skill", ["skills/x/SKILL.md"], {"total_files": 100, "skill_count": 1}),
    )
    monkeypatch.setattr(
        t, "build_skill_entries",
        lambda repo, branch, item, ls: [
            {"id": f"{repo.replace('/', '-')}-skill", "type": "skill",
             "source": t.SOURCE_ID,
             "source_url": f"https://github.com/{repo}/tree/{branch}/x"},
        ],
    )
    skill_entries, plugin_cfgs, stats = t.discover("2026-06-16", max_verify=10)
    assert stats["deferred"] == 0
    assert stats["skill_repos"] == 2


def test_discover_max_verify_zero_means_unlimited(monkeypatch):
    """max_verify=0 视作不限量（全量验证），不推迟任何候选。"""
    candidates = {f"o/r{i}": _item(f"o/r{i}", stars=100 + i) for i in range(5)}
    _setup_discover_env(
        monkeypatch, candidates,
        lambda r: ("skill", ["skills/x/SKILL.md"], {"total_files": 100, "skill_count": 1}),
    )
    monkeypatch.setattr(
        t, "build_skill_entries",
        lambda repo, branch, item, ls: [
            {"id": f"{repo.replace('/', '-')}-skill", "type": "skill",
             "source": t.SOURCE_ID,
             "source_url": f"https://github.com/{repo}/tree/{branch}/x"},
        ],
    )
    skill_entries, plugin_cfgs, stats = t.discover("2026-06-16", max_verify=0)
    assert stats["deferred"] == 0
    assert stats["skill_repos"] == 5


# --- verify_cache 增量写（二级保险）：中途落盘，被 kill 也持久化 -------------

def test_discover_flushes_verify_cache_incrementally(monkeypatch):
    """验证循环里每 N 个落盘一次 verify_cache（而非只在末尾），即便中途被 kill
    已验证进度也持久化。"""
    # 6 个候选，FLUSH_EVERY=2 → 第 2、4、6 个之后各落盘一次（含末尾）
    candidates = {f"o/r{i}": _item(f"o/r{i}", stars=200 - i) for i in range(6)}
    monkeypatch.setattr(t, "build_known_repos", lambda: set())
    monkeypatch.setattr(t, "load_verify_cache", lambda: {})
    monkeypatch.setattr(t, "VERIFY_CACHE_FLUSH_EVERY", 2)
    monkeypatch.setattr(
        t, "collect_candidates",
        lambda *a, **k: (dict(candidates),
                         {"raw": 6, "prefiltered_known": 0, "below_min_stars": 0}),
    )
    monkeypatch.setattr(
        t, "classify_repo",
        lambda r, b, ls: ("skill", ["skills/x/SKILL.md"], {"total_files": 100, "skill_count": 1}),
    )
    monkeypatch.setattr(
        t, "build_skill_entries",
        lambda repo, branch, item, ls: [
            {"id": f"{repo.replace('/', '-')}-skill", "type": "skill",
             "source": t.SOURCE_ID,
             "source_url": f"https://github.com/{repo}/tree/{branch}/x"},
        ],
    )

    # 记录每次 save_verify_cache 调用时 cache 的大小，验证是"中途渐增"而非只末尾一次
    flush_sizes = []
    monkeypatch.setattr(
        t, "save_verify_cache",
        lambda c: flush_sizes.append(len(c)),
    )

    t.discover("2026-06-16", max_verify=0)

    # 6 个候选 / 每 2 个 flush 一次 = 3 次中途 flush + 1 次末尾 = 4 次（末尾与第 3 次 size 相同）
    assert len(flush_sizes) >= 3            # 至少中途落盘多次（非只末尾一次）
    assert flush_sizes[0] == 2              # 第一次 flush 时已有 2 条
    assert flush_sizes[-1] == 6             # 末尾全部落盘
    # 大小单调不减（增量积累）
    assert flush_sizes == sorted(flush_sizes)


def test_discover_flush_survives_kill_midway(monkeypatch):
    """模拟"中途被 kill"：在处理第 3 个候选时抛 KeyboardInterrupt，
    断言前 2 个已 flush 持久化（不丢进度）。"""
    candidates = {f"o/r{i}": _item(f"o/r{i}", stars=300 - i) for i in range(5)}
    monkeypatch.setattr(t, "build_known_repos", lambda: set())
    monkeypatch.setattr(t, "load_verify_cache", lambda: {})
    monkeypatch.setattr(t, "VERIFY_CACHE_FLUSH_EVERY", 2)
    monkeypatch.setattr(
        t, "collect_candidates",
        lambda *a, **k: (dict(candidates),
                         {"raw": 5, "prefiltered_known": 0, "below_min_stars": 0}),
    )
    monkeypatch.setattr(
        t, "classify_repo",
        lambda r, b, ls: ("skill", ["skills/x/SKILL.md"], {"total_files": 100, "skill_count": 1}),
    )

    n_built = {"count": 0}

    def fake_build(repo, branch, item, ls):
        n_built["count"] += 1
        if n_built["count"] == 3:
            raise KeyboardInterrupt("simulated CI kill")  # 第 3 个时被 kill
        return [{"id": f"{repo.replace('/', '-')}-skill", "type": "skill",
                 "source": t.SOURCE_ID,
                 "source_url": f"https://github.com/{repo}/tree/{branch}/x"}]

    monkeypatch.setattr(t, "build_skill_entries", fake_build)

    last_flush = {"cache": None}
    monkeypatch.setattr(
        t, "save_verify_cache",
        lambda c: last_flush.update({"cache": dict(c)}),
    )

    # KeyboardInterrupt 不被 per-candidate except 吞（BaseException 非 Exception），
    # 会向上冒泡，但前 2 个的进度已通过增量 flush 持久化
    with pytest.raises(KeyboardInterrupt):
        t.discover("2026-06-16", max_verify=0)

    # 被 kill 前已 flush（处理完前 2 个时触发了一次 FLUSH_EVERY=2 的落盘）
    assert last_flush["cache"] is not None
    assert len(last_flush["cache"]) == 2    # 前 2 个的进度已持久化


def test_save_verify_cache_best_effort_on_write_failure(monkeypatch, tmp_path):
    """cache 写失败要 best-effort 不崩（OSError 被吞）。"""
    bad_dir = tmp_path / "nope"
    bad_path = bad_dir / "verify_cache.json"
    monkeypatch.setattr(t, "CACHE_DIR", "/dev/null/cannot-mkdir")
    monkeypatch.setattr(t, "VERIFY_CACHE_PATH", str(bad_path))
    # 不应抛
    t.save_verify_cache({"o/r": {"kind": "skill"}})
