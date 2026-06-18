"""source_registry 促升登记单测：促升清单每仓登记进 SOURCE_REGISTRY（key 逐字等于
source_slug），登记后 build_sources_payload 对这些 source 不再 WARNING、count>0 时
出现在 sources.json。

无网络；用真实仓内促升清单 + tmp 临时清单两路验证。
"""

import io
import json
import os
import sys
from contextlib import redirect_stdout

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import source_registry as sr  # noqa: E402


# --- 真实促升清单登记 ------------------------------------------------------

def test_promoted_slugs_registered():
    """仓内促升清单每仓在 SOURCE_REGISTRY 有 entry，key 逐字等于 source_slug。"""
    # skill 仓 → Skills；plugin 仓 → Plugins；trust=3
    assert sr.SOURCE_REGISTRY["google/skills"]["type"] == "Skills"
    assert sr.SOURCE_REGISTRY["google/skills"]["trust"] == 3
    assert sr.SOURCE_REGISTRY["composiohq/awesome-codex-skills"]["type"] == "Skills"
    assert sr.SOURCE_REGISTRY["browserbase/skills"]["type"] == "Plugins"
    assert sr.SOURCE_REGISTRY["browserbase/skills"]["trust"] == 3
    # mattpocock 也登记（首次入库即带 slug + 展示名）
    assert "mattpocock/skills" in sr.SOURCE_REGISTRY
    # label 来自清单
    assert sr.SOURCE_REGISTRY["google/skills"]["label"] == "Google Skills"


def test_registered_keys_match_source_slug_lowercase():
    """slug 一致性铁律：registry key 必须逐字等于清单 source_slug（小写 owner/repo）。"""
    with open(sr._PROMOTED_REPOS_PATH, encoding="utf-8") as f:
        promoted = json.load(f)["repos"]
    for item in promoted:
        slug = item["source_slug"]
        assert slug == slug.lower()
        assert slug in sr.SOURCE_REGISTRY
        assert sr.SOURCE_REGISTRY[slug]["type"] in sr.TYPE_ORDER


# --- build_sources_payload：登记后不再 WARNING、count>0 出现 ----------------

def test_promoted_source_no_warning_and_appears():
    """促升仓的 entry source 命中后：build_sources_payload 不再 WARN，且出现在 sources。"""
    items = [
        {"source": "google/skills"},
        {"source": "google/skills"},
        {"source": "browserbase/skills"},
    ]
    buf = io.StringIO()
    with redirect_stdout(buf):
        payload = sr.build_sources_payload(items)
    out = buf.getvalue()
    # 不再对已登记的促升 source WARN
    assert "google/skills" not in out
    assert "browserbase/skills" not in out
    by_slug = {s["slug"]: s for s in payload["sources"]}
    assert by_slug["google/skills"]["count"] == 2
    assert by_slug["browserbase/skills"]["count"] == 1
    # trust=3 → Tier 3 分级出现
    assert 3 in {t["score"] for t in payload["tiers"]}


def test_unregistered_source_still_warns():
    """未登记的 source 仍 WARN（确认 promote 登记没误关掉 WARNING 机制）。"""
    buf = io.StringIO()
    with redirect_stdout(buf):
        sr.build_sources_payload([{"source": "totally-unknown-source"}])
    assert "totally-unknown-source" in buf.getvalue()


# --- _register_promoted_sources DRY 注入逻辑 -------------------------------

def test_register_promoted_sources_from_temp_file(tmp_path):
    """_register_promoted_sources 从清单文件注入：skill→Skills, plugin→Plugins。"""
    p = tmp_path / "promote.json"
    p.write_text(json.dumps({"repos": [
        {"repo": "Foo/Bar", "source_slug": "foo/bar", "label": "Foo Bar",
         "url": "https://github.com/Foo/Bar", "type": "skill", "trust": 3},
        {"repo": "baz/qux", "source_slug": "baz/qux", "type": "plugin"},
    ]}), encoding="utf-8")
    reg = {}
    sr._register_promoted_sources(reg, str(p))
    assert reg["foo/bar"] == {
        "label": "Foo Bar", "url": "https://github.com/Foo/Bar",
        "type": "Skills", "trust": 3,
    }
    assert reg["baz/qux"]["type"] == "Plugins"
    assert reg["baz/qux"]["label"] == "baz/qux"  # 缺省回填


def test_register_promoted_sources_missing_file_noop(tmp_path):
    """清单缺失 → 不崩、不注入。"""
    reg = {}
    sr._register_promoted_sources(reg, str(tmp_path / "nope.json"))
    assert reg == {}
