"""Tests for the resource_authenticity (is_primary_skill) stage in eval_bridge.

镜像 security_scan 的测试方式：注入 fake judge / fake fetcher，用临时 cache 目录，
全程无网络、无真实 LLM key。覆盖：
  - 仅作用于 source=='github-trending'（其他源零成本跳过）
  - is_primary_skill true/false 都写入 entry['resource_authenticity']
  - 失败兜底（无 key / LLM 异常 / 解析失败 / 无内容）= 不写字段
  - 独立 cache namespace + 第二次命中 cache 不再调 LLM
  - prompt / schema 契约
"""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import eval_bridge  # noqa: E402


# --- fakes -----------------------------------------------------------------

class _FakeJudgeResult:
    def __init__(self, structured, model_id="fake-model"):
        self.structured = structured
        self.model_id = model_id
        self.cost_usd = 0.0


class _FakeJudge:
    """记录每次 judge 调用，返回预设 structured（或抛异常）。"""

    def __init__(self, structured=None, raise_exc=None):
        self._structured = structured
        self._raise = raise_exc
        self.calls = []

    def judge(self, system_prompt, user_prompt, schema=None, pydantic_model=None):
        self.calls.append({"system": system_prompt, "user": user_prompt, "schema": schema})
        if self._raise is not None:
            raise self._raise
        return _FakeJudgeResult(self._structured)


class _FakeFetcher:
    """返回固定内容，记录被 fetch 的 url。"""

    def __init__(self, content="some skill content"):
        self._content = content
        self.fetched = []

    def fetch(self, url):
        self.fetched.append(url)
        if self._content is None:
            return None
        return (self._content, "hash")


def _gt_entry(eid="gt-1", **kw):
    base = {
        "id": eid,
        "name": "Test Skill",
        "type": "skill",
        "source": "github-trending",
        "source_url": "https://github.com/foo/bar/tree/main/skills/x",
        "description": "a coding skill",
    }
    base.update(kw)
    return base


def _patch_judge_and_fetcher(monkeypatch, judge, fetcher):
    monkeypatch.setattr(eval_bridge, "_build_judge", lambda: judge)
    # GitHubFetcher 在 _authenticity_one 内由 _run_authenticity_scan 实例化；
    # patch 模块级 import 点。
    import ai_resource_eval.fetcher as fmod
    monkeypatch.setattr(fmod, "GitHubFetcher", lambda content_paths=None: fetcher)


# --- scope：仅 github-trending ---------------------------------------------

def test_only_github_trending_scanned(monkeypatch, tmp_path):
    judge = _FakeJudge({"is_primary_skill": True, "reason": "主体是 skill"})
    fetcher = _FakeFetcher()
    _patch_judge_and_fetcher(monkeypatch, judge, fetcher)

    entries = [
        _gt_entry("gt-1"),
        {"id": "other-1", "name": "x", "type": "skill", "source": "skills-sh",
         "source_url": "https://github.com/a/b", "description": "d"},
    ]
    eval_bridge.authenticity_scan_and_map(entries, cache_dir=str(tmp_path), incremental=False)

    # github-trending 被判定并写字段；其他源完全不碰（零成本）
    assert entries[0]["resource_authenticity"]["is_primary_skill"] is True
    assert "resource_authenticity" not in entries[1]
    # judge 只被 github-trending 的那一条调用
    assert len(judge.calls) == 1


def test_no_github_trending_entries_no_judge_built(monkeypatch, tmp_path):
    """没有 github-trending entry 时连 _build_judge 都不应被调（短路省成本）。"""
    built = {"n": 0}

    def _spy():
        built["n"] += 1
        return _FakeJudge({"is_primary_skill": True, "reason": "r"})

    monkeypatch.setattr(eval_bridge, "_build_judge", _spy)
    entries = [{"id": "x", "name": "x", "type": "skill", "source": "skills-sh",
                "source_url": "https://github.com/a/b", "description": "d"}]
    eval_bridge.authenticity_scan_and_map(entries, cache_dir=str(tmp_path), incremental=False)
    assert built["n"] == 0
    assert "resource_authenticity" not in entries[0]


# --- true / false 都写字段 -------------------------------------------------

def test_is_primary_skill_false_written(monkeypatch, tmp_path):
    judge = _FakeJudge({"is_primary_skill": False, "reason": "主体是 agent framework"})
    fetcher = _FakeFetcher()
    _patch_judge_and_fetcher(monkeypatch, judge, fetcher)

    entries = [_gt_entry("gt-app")]
    eval_bridge.authenticity_scan_and_map(entries, cache_dir=str(tmp_path), incremental=False)

    auth = entries[0]["resource_authenticity"]
    assert auth["is_primary_skill"] is False
    assert auth["reason"] == "主体是 agent framework"
    assert auth["rubric_version"].startswith("1.")
    assert auth["content_hash"]
    assert auth["scanned_at"]


# --- 失败兜底：不写字段 -----------------------------------------------------

def test_no_judge_no_field(monkeypatch, tmp_path):
    """无 LLM key（_build_judge → None）→ 不写字段。"""
    monkeypatch.setattr(eval_bridge, "_build_judge", lambda: None)
    entries = [_gt_entry()]
    eval_bridge.authenticity_scan_and_map(entries, cache_dir=str(tmp_path), incremental=False)
    assert "resource_authenticity" not in entries[0]


def test_llm_exception_no_field(monkeypatch, tmp_path):
    """LLM 调用抛异常 → 不写字段（下周期重试），不崩主管线。"""
    judge = _FakeJudge(raise_exc=RuntimeError("boom"))
    fetcher = _FakeFetcher()
    _patch_judge_and_fetcher(monkeypatch, judge, fetcher)
    entries = [_gt_entry()]
    eval_bridge.authenticity_scan_and_map(entries, cache_dir=str(tmp_path), incremental=False)
    assert "resource_authenticity" not in entries[0]


def test_unparseable_response_no_field(monkeypatch, tmp_path):
    """structured 缺 is_primary_skill → 不写字段。"""
    judge = _FakeJudge({"reason": "missing the bool"})
    fetcher = _FakeFetcher()
    _patch_judge_and_fetcher(monkeypatch, judge, fetcher)
    entries = [_gt_entry()]
    eval_bridge.authenticity_scan_and_map(entries, cache_dir=str(tmp_path), incremental=False)
    assert "resource_authenticity" not in entries[0]


def test_non_bool_is_primary_skill_no_field(monkeypatch, tmp_path):
    """is_primary_skill 非 bool（如字符串 'true'）→ 不写字段（严格校验）。"""
    judge = _FakeJudge({"is_primary_skill": "true", "reason": "r"})
    fetcher = _FakeFetcher()
    _patch_judge_and_fetcher(monkeypatch, judge, fetcher)
    entries = [_gt_entry()]
    eval_bridge.authenticity_scan_and_map(entries, cache_dir=str(tmp_path), incremental=False)
    assert "resource_authenticity" not in entries[0]


def test_no_content_no_field(monkeypatch, tmp_path):
    """fetch 返回 None 且无 description → 无内容可判 → 不写字段，不调 LLM。"""
    judge = _FakeJudge({"is_primary_skill": True, "reason": "r"})
    fetcher = _FakeFetcher(content=None)
    _patch_judge_and_fetcher(monkeypatch, judge, fetcher)
    entries = [_gt_entry(description="", source_url="https://github.com/a/b")]
    eval_bridge.authenticity_scan_and_map(entries, cache_dir=str(tmp_path), incremental=False)
    assert "resource_authenticity" not in entries[0]
    assert judge.calls == []  # 无内容 → 不浪费 LLM 调用


def test_description_fallback_when_fetch_fails(monkeypatch, tmp_path):
    """fetch 失败但有 description → 用 description 作内容仍能判定。"""
    judge = _FakeJudge({"is_primary_skill": True, "reason": "据 description 判定"})
    fetcher = _FakeFetcher(content=None)
    _patch_judge_and_fetcher(monkeypatch, judge, fetcher)
    entries = [_gt_entry(description="a reusable coding skill that does X")]
    eval_bridge.authenticity_scan_and_map(entries, cache_dir=str(tmp_path), incremental=False)
    assert entries[0]["resource_authenticity"]["is_primary_skill"] is True
    assert len(judge.calls) == 1


# --- cache：第二次命中不再调 LLM -------------------------------------------

def test_cache_hit_avoids_second_llm_call(monkeypatch, tmp_path):
    judge = _FakeJudge({"is_primary_skill": False, "reason": "app"})
    fetcher = _FakeFetcher(content="stable content")
    _patch_judge_and_fetcher(monkeypatch, judge, fetcher)

    # 第一遍：写 cache
    e1 = [_gt_entry("gt-cache")]
    eval_bridge.authenticity_scan_and_map(e1, cache_dir=str(tmp_path), incremental=True)
    assert e1[0]["resource_authenticity"]["is_primary_skill"] is False
    assert len(judge.calls) == 1

    # 第二遍：同内容（同 content_hash）→ incremental 命中 cache，不再调 LLM
    e2 = [_gt_entry("gt-cache")]
    eval_bridge.authenticity_scan_and_map(e2, cache_dir=str(tmp_path), incremental=True)
    assert e2[0]["resource_authenticity"]["is_primary_skill"] is False
    assert len(judge.calls) == 1  # 没有新增调用


def test_independent_cache_namespace(monkeypatch, tmp_path):
    """authenticity cache key 用独立 namespace，与质量/security 不撞键。"""
    from ai_resource_eval.cache import EvalCache

    rv = eval_bridge._authenticity_rubric_version()
    key = EvalCache.make_key("__authenticity__", "abc", rv, namespace="authenticity")
    # 同 content_hash / rubric 但无 namespace（质量路径）应得到不同 key
    quality_key = EvalCache.make_key("__authenticity__", "abc", rv)
    assert key != quality_key


# --- prompt / schema 契约 --------------------------------------------------

def test_user_prompt_includes_metadata_and_content():
    entry = _gt_entry(tags=["coding", "test"])
    prompt = eval_bridge._build_authenticity_user_prompt(entry, "REPO CONTENT HERE")
    assert "Test Skill" in prompt
    assert "REPO CONTENT HERE" in prompt
    assert "coding, test" in prompt
    assert "github.com/foo/bar" in prompt


def test_user_prompt_truncates_long_content():
    entry = _gt_entry()
    long = "x" * (eval_bridge._AUTHENTICITY_MAX_CONTENT_CHARS + 5000)
    prompt = eval_bridge._build_authenticity_user_prompt(entry, long)
    assert "内容截断" in prompt
    assert len(prompt) < len(long) + 2000


def test_output_schema_requires_two_keys():
    schema = eval_bridge._AUTHENTICITY_OUTPUT_SCHEMA
    assert schema["required"] == ["is_primary_skill", "reason"]
    assert schema["properties"]["is_primary_skill"]["type"] == "boolean"
    assert schema["additionalProperties"] is False
