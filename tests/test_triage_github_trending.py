"""triage_github_trending 单测：Stage B 路由（plugin 探测 / LLM is_primary_skill）、
LLM 判 app → 丢弃、survivors 才深拉、增量写 + wall-clock 预算、单仓异常隔离。

全程注入 fake judge / plugin_probe / monkeypatch 深拉构造器，无网络、无 LLM。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import triage_github_trending as tr  # noqa: E402
import sync_github_trending as sgt  # noqa: E402


def _cand(full, stars=100, branch="main", pushed_at="2026-06-01T00:00:00Z",
          topics=None, description="a skill"):
    return {"full_name": full, "stars": stars, "default_branch": branch,
            "pushed_at": pushed_at, "topics": topics or [], "description": description}


class _FakeJudge:
    """注入式 judge：verdicts 是 {full_name: bool}，缺省返回 True（保守放行）。"""

    def __init__(self, verdicts=None):
        self.verdicts = verdicts or {}
        self.calls = []

    def is_primary_skill(self, candidate):
        full = candidate["full_name"]
        self.calls.append(full)
        v = self.verdicts.get(full, True)
        return v, "fake"


def _setup_stage_c(monkeypatch):
    """注入 Stage C 深拉构造器：记录被深拉的 repo；skill 产 1 entry，plugin 产 1 entry。"""
    skill_built = []
    plugin_built = []

    def fake_build_skill(repo, branch, item, last_synced, source_id=sgt.SOURCE_ID):
        skill_built.append(repo)
        return [{"id": f"{repo.replace('/', '-')}-skill", "type": "skill",
                 "source": source_id,
                 "source_url": f"https://github.com/{repo}/tree/{branch}/x"}]

    def fake_sync_plugins(cfgs, last_synced):
        out = []
        for c in cfgs:
            plugin_built.append(c["repo_slug"])
            out.append({"id": f"{c['repo_slug'].replace('/', '-')}-plugin",
                        "type": "plugin",
                        "source_url": f"https://github.com/{c['repo_slug']}.git"})
        return out

    monkeypatch.setattr(sgt, "build_skill_entries", fake_build_skill)
    monkeypatch.setattr(sgt, "sync_plugins", fake_sync_plugins)
    monkeypatch.setattr(sgt, "load_verify_cache", lambda: {})
    saved = {}
    monkeypatch.setattr(sgt, "save_verify_cache", lambda c: saved.update({"cache": dict(c)}))
    return skill_built, plugin_built, saved


def _capture_writes(monkeypatch):
    """捕获 flush_skills / flush_plugins 写入的 entry（不真写盘）。"""
    written = {"skills": [], "plugins": []}
    monkeypatch.setattr(tr, "flush_skills",
                        lambda entries, path: written["skills"].extend(entries) or len(entries))
    monkeypatch.setattr(tr, "flush_plugins",
                        lambda entries, path: written["plugins"].extend(entries) or len(entries))
    return written


# --- Stage B-1：plugin 探测 -------------------------------------------------

def test_probe_plugin_hit():
    """marketplace.json 命中 → True，不拉 Tree（fetch_manifest 注入）。"""
    assert tr.probe_plugin("o/r", _fetch_manifest=lambda repo: {"name": "x", "plugins": []})


def test_probe_plugin_miss():
    assert tr.probe_plugin("o/r", _fetch_manifest=lambda repo: None) is False


def test_probe_plugin_exception_is_not_plugin():
    """探测抛异常 → 保守当非 plugin（交 LLM 判别），不崩。"""
    def boom(repo):
        raise RuntimeError("network")
    assert tr.probe_plugin("o/r", _fetch_manifest=boom) is False


# --- Stage B 路由 + Stage C 深拉 -------------------------------------------

def test_triage_routes_plugin_before_llm(monkeypatch):
    """plugin 探测命中 → plugin 路由，**不调 LLM**，深拉 plugin。"""
    skill_built, plugin_built, saved = _setup_stage_c(monkeypatch)
    _capture_writes(monkeypatch)
    judge = _FakeJudge()
    stats = tr.triage(
        [_cand("o/plug")], "2026-06-16", judge=judge,
        plugin_probe=lambda full: True, wall_budget=999,
    )
    assert plugin_built == ["o/plug"]
    assert skill_built == []
    assert judge.calls == []  # plugin 不走 is_primary_skill
    assert stats["plugin_repos"] == 1
    assert saved["cache"]["o/plug"]["kind"] == "plugin"


def test_triage_llm_app_dropped_before_deep_pull(monkeypatch):
    """LLM 判 is_primary_skill=False（app/framework）→ 丢弃，**不进 Stage C 深拉**。"""
    skill_built, plugin_built, saved = _setup_stage_c(monkeypatch)
    _capture_writes(monkeypatch)
    judge = _FakeJudge(verdicts={"openclaw/app": False, "real/skill": True})
    stats = tr.triage(
        [_cand("openclaw/app", description="agent framework"), _cand("real/skill")],
        "2026-06-16", judge=judge, plugin_probe=lambda full: False, wall_budget=999,
    )
    # app 被 LLM 砍掉，不深拉
    assert "openclaw/app" not in skill_built
    assert skill_built == ["real/skill"]
    assert stats["llm_dropped"] == 1
    assert stats["skill_repos"] == 1
    # app 缓存为 kind=app（避免反复判别），skill 缓存为 kind=skill
    assert saved["cache"]["openclaw/app"]["kind"] == "app"
    assert saved["cache"]["real/skill"]["kind"] == "skill"


def test_triage_survivor_skill_deep_pulled(monkeypatch):
    """LLM 判 true 的 skill 才深拉，写入 skill index。"""
    _setup_stage_c(monkeypatch)
    written = _capture_writes(monkeypatch)
    judge = _FakeJudge(verdicts={"real/skill": True})
    tr.triage([_cand("real/skill")], "2026-06-16", judge=judge,
              plugin_probe=lambda full: False, wall_budget=999)
    assert [e["id"] for e in written["skills"]] == ["real-skill-skill"]


def test_triage_skill_no_entry_not_cached(monkeypatch):
    """skill 深拉无产出（全被 hard_filter 刷掉）→ 不缓存空结果，下次重试。"""
    _, _, saved = _setup_stage_c(monkeypatch)
    _capture_writes(monkeypatch)
    monkeypatch.setattr(sgt, "build_skill_entries", lambda *a, **k: [])
    judge = _FakeJudge(verdicts={"real/skill": True})
    stats = tr.triage([_cand("real/skill")], "2026-06-16", judge=judge,
                      plugin_probe=lambda full: False, wall_budget=999)
    assert stats["skill_no_entry"] == 1
    assert "real/skill" not in saved["cache"]


# --- 增量 cache 命中：跳过深拉 ---------------------------------------------

def test_triage_cache_hit_skips_deep_pull(monkeypatch):
    """verify_cache 命中（pushed_at 未变 + 终态 kind）→ 不重判、不深拉。"""
    skill_built, plugin_built, _ = _setup_stage_c(monkeypatch)
    _capture_writes(monkeypatch)
    monkeypatch.setattr(sgt, "load_verify_cache", lambda: {
        "real/skill": {"pushed_at": "2026-06-01T00:00:00Z", "kind": "skill"},
        "o/app": {"pushed_at": "2026-06-01T00:00:00Z", "kind": "app"},
    })
    judge = _FakeJudge()
    judge_called = []
    judge.is_primary_skill = lambda c: (judge_called.append(c["full_name"]), (True, "x"))[1]
    stats = tr.triage(
        [_cand("real/skill"), _cand("o/app")], "2026-06-16", judge=judge,
        plugin_probe=lambda full: pytest.fail("cache 命中不应探测 plugin"),
        wall_budget=999,
    )
    assert stats["cache_hit"] == 2
    assert skill_built == []
    assert judge_called == []


def test_triage_cache_miss_on_pushed_at_change(monkeypatch):
    """pushed_at 变了 → cache 不命中，重新判别 + 深拉。"""
    skill_built, _, _ = _setup_stage_c(monkeypatch)
    _capture_writes(monkeypatch)
    monkeypatch.setattr(sgt, "load_verify_cache", lambda: {
        "real/skill": {"pushed_at": "2020-01-01T00:00:00Z", "kind": "skill"},
    })
    judge = _FakeJudge(verdicts={"real/skill": True})
    tr.triage([_cand("real/skill", pushed_at="2026-06-01T00:00:00Z")],
              "2026-06-16", judge=judge, plugin_probe=lambda full: False, wall_budget=999)
    assert skill_built == ["real/skill"]


# --- wall-clock 预算：到点 flush 退出 --------------------------------------

def test_triage_wall_budget_flushes_and_exits(monkeypatch):
    """wall-clock 预算用尽 → 已处理的保住、剩余不处理，budget_exhausted=True。"""
    skill_built, _, _ = _setup_stage_c(monkeypatch)
    _capture_writes(monkeypatch)
    judge = _FakeJudge()  # 全部 True

    # fake clock：每次调用前进 10s；wall_budget=15 → 处理完第 1 个后第 2 轮检查即超
    ticks = {"t": 0}

    def fake_now():
        cur = ticks["t"]
        ticks["t"] += 10
        return cur

    cands = [_cand("a/one", stars=300), _cand("b/two", stars=200),
             _cand("c/three", stars=100)]
    stats = tr.triage(cands, "2026-06-16", judge=judge,
                      plugin_probe=lambda full: False, wall_budget=15,
                      flush_every=0, now=fake_now)
    assert stats["budget_exhausted"] is True
    # 至少处理了第一个，没处理全部三个
    assert 0 < stats["processed"] < 3
    assert len(skill_built) == stats["processed"]


def test_triage_incremental_flush_every(monkeypatch):
    """flush_every=2 → 每处理 2 个 flush 一次（中途落盘，非只末尾）。"""
    _setup_stage_c(monkeypatch)
    _capture_writes(monkeypatch)
    flush_sizes = []

    def track_save(c):
        flush_sizes.append(len(c))

    monkeypatch.setattr(sgt, "save_verify_cache", track_save)
    judge = _FakeJudge()
    cands = [_cand(f"o/r{i}", stars=200 - i) for i in range(4)]
    tr.triage(cands, "2026-06-16", judge=judge, plugin_probe=lambda full: False,
              wall_budget=999, flush_every=2)
    # 4 个 / 每 2 个 flush = 2 次中途 + 1 次末尾
    assert len(flush_sizes) >= 2
    assert flush_sizes[-1] == 4  # 末尾全部落盘


# --- 单仓异常隔离 ----------------------------------------------------------

def test_triage_isolates_per_repo_exception(monkeypatch):
    """某候选深拉抛异常 → triage 不崩，其他照常，errored 计数，崩溃仓不缓存。"""
    _, _, saved = _setup_stage_c(monkeypatch)
    _capture_writes(monkeypatch)

    def build(repo, branch, item, last_synced, source_id=sgt.SOURCE_ID):
        if repo == "boom/repo":
            import http.client
            raise http.client.RemoteDisconnected("boom")
        return [{"id": f"{repo.replace('/', '-')}-skill", "type": "skill",
                 "source": source_id,
                 "source_url": f"https://github.com/{repo}/tree/{branch}/x"}]

    monkeypatch.setattr(sgt, "build_skill_entries", build)
    judge = _FakeJudge()
    stats = tr.triage(
        [_cand("good/skill"), _cand("boom/repo")], "2026-06-16", judge=judge,
        plugin_probe=lambda full: False, wall_budget=999,
    )
    assert stats["errored"] == 1
    assert stats["skill_repos"] == 1
    assert "boom/repo" not in saved["cache"]
    assert "good/skill" in saved["cache"]


# --- 促升清单：per-repo source 覆盖 + 跳过 is_primary_skill ------------------

def _setup_stage_c_capture_source(monkeypatch):
    """注入 Stage C 深拉构造器，记录 build_skill_entries 收到的 source_id +
    sync_plugins 收到的 cfg["id"]。"""
    captured = {"skill_source": [], "plugin_cfg_id": []}

    def fake_build_skill(repo, branch, item, last_synced, source_id=sgt.SOURCE_ID):
        captured["skill_source"].append((repo, source_id))
        return [{"id": f"{repo.replace('/', '-')}-skill", "type": "skill",
                 "source": source_id,
                 "source_url": f"https://github.com/{repo}/tree/{branch}/x"}]

    def fake_sync_plugins(cfgs, last_synced):
        out = []
        for c in cfgs:
            captured["plugin_cfg_id"].append((c["repo_slug"], c["id"]))
            out.append({"id": f"{c['repo_slug'].replace('/', '-')}-plugin",
                        "type": "plugin", "source": c["id"],
                        "source_url": f"https://github.com/{c['repo_slug']}.git"})
        return out

    monkeypatch.setattr(sgt, "build_skill_entries", fake_build_skill)
    monkeypatch.setattr(sgt, "sync_plugins", fake_sync_plugins)
    monkeypatch.setattr(sgt, "load_verify_cache", lambda: {})
    monkeypatch.setattr(sgt, "save_verify_cache", lambda c: None)
    return captured


def test_triage_promoted_skill_per_repo_source(monkeypatch):
    """促升仓 skill：带专属 per-repo source slug（非 github-trending），不调 LLM 判别。"""
    captured = _setup_stage_c_capture_source(monkeypatch)
    written = _capture_writes(monkeypatch)
    judge = _FakeJudge()
    stats = tr.triage(
        [_cand("Google/Skills")], "2026-06-16", judge=judge,
        plugin_probe=lambda full: False, wall_budget=999,
        promoted_map={"google/skills": "google/skills"},
    )
    # source_id 传入专属 slug；entry 的 source == slug
    assert captured["skill_source"] == [("Google/Skills", "google/skills")]
    assert written["skills"][0]["source"] == "google/skills"
    # 促升仓**跳过** is_primary_skill（手工精选可信）
    assert judge.calls == []
    assert stats["promoted"] == 1
    assert stats["skill_repos"] == 1


def test_triage_promoted_plugin_per_repo_source(monkeypatch):
    """促升仓 plugin：cfg id 换成专属 slug → entry source == slug，不调 LLM。"""
    captured = _setup_stage_c_capture_source(monkeypatch)
    written = _capture_writes(monkeypatch)
    judge = _FakeJudge()
    stats = tr.triage(
        [_cand("Browserbase/Skills")], "2026-06-16", judge=judge,
        plugin_probe=lambda full: True, wall_budget=999,
        promoted_map={"browserbase/skills": "browserbase/skills"},
    )
    assert captured["plugin_cfg_id"] == [("Browserbase/Skills", "browserbase/skills")]
    assert written["plugins"][0]["source"] == "browserbase/skills"
    assert judge.calls == []
    assert stats["promoted"] == 1
    assert stats["plugin_repos"] == 1


def test_triage_non_promoted_still_github_trending(monkeypatch):
    """非促升仓不受影响：仍走 LLM 判别 + 默认 github-trending source。"""
    captured = _setup_stage_c_capture_source(monkeypatch)
    _capture_writes(monkeypatch)
    judge = _FakeJudge(verdicts={"random/repo": True})
    tr.triage(
        [_cand("random/repo")], "2026-06-16", judge=judge,
        plugin_probe=lambda full: False, wall_budget=999,
        promoted_map={"google/skills": "google/skills"},  # 不含 random/repo
    )
    # 非促升仓：source_id 用默认 SOURCE_ID，LLM 判别被调用
    assert captured["skill_source"] == [("random/repo", sgt.SOURCE_ID)]
    assert judge.calls == ["random/repo"]


def test_triage_promoted_skips_llm_even_if_app_verdict(monkeypatch):
    """促升仓即便 LLM 会判 app，也不调 LLM（白名单豁免）→ 不被丢弃，照常深拉。"""
    captured = _setup_stage_c_capture_source(monkeypatch)
    _capture_writes(monkeypatch)
    # judge 配置 verdict=False（若被调用会丢弃）；促升仓应根本不调它
    judge = _FakeJudge(verdicts={"google/skills": False})
    judge.is_primary_skill = lambda c: pytest.fail("促升仓不该调 is_primary_skill")
    stats = tr.triage(
        [_cand("google/skills")], "2026-06-16", judge=judge,
        plugin_probe=lambda full: False, wall_budget=999,
        promoted_map={"google/skills": "google/skills"},
    )
    assert stats["llm_dropped"] == 0
    assert stats["skill_repos"] == 1
    assert captured["skill_source"] == [("google/skills", "google/skills")]


def test_triage_llm_unavailable_conservative_pass(monkeypatch):
    """LLM 不可用（judge 返回 llm-unavailable）→ 保守放行（当 skill 深拉），计入降级。"""
    skill_built, _, _ = _setup_stage_c(monkeypatch)
    _capture_writes(monkeypatch)

    class Unavail:
        def is_primary_skill(self, c):
            return True, "llm-unavailable"

    stats = tr.triage([_cand("real/skill")], "2026-06-16", judge=Unavail(),
                      plugin_probe=lambda full: False, wall_budget=999)
    assert skill_built == ["real/skill"]
    assert stats["llm_unavailable"] == 1
    assert stats["skill_repos"] == 1
