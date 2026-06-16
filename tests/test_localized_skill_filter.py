"""Tests for the localized (i18n) SKILL.md copy filter.

A repo like ``affaan-m/ECC`` ships 519 / 881 translated copies of every skill
under ``docs/<locale>/skills/.../SKILL.md`` (locales: ja-JP / zh-CN / zh-TW /
ko-KR / es / tr). Naively scanning by filename pulls each skill in N times.

``utils.is_localized_skill_path`` / ``filter_canonical_skill_paths`` drop those
copies with a HIGH-PRECISION bias (never drop a canonical skill). This module
exercises the shared function directly + the three application points:

  1. ``skill_registry.scan_repo_via_api``
  2. ``sync_github_trending.classify_repo`` (skill_count / megaapp density)
  3. ``merge_index._apply_bundled_in_annotations`` (plugin bundle synthesis)
"""

import pathlib
import sys

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from utils import (  # noqa: E402
    is_localized_skill_path,
    filter_canonical_skill_paths,
)


# ---------------------------------------------------------------------------
# 1. Shared discriminator: drop / keep / no-false-positive
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        # region-form locale anywhere in path
        "docs/ja-JP/skills/accessibility/SKILL.md",
        "docs/zh-CN/skills/api-design/SKILL.md",
        "docs/zh-TW/skills/backend-patterns/SKILL.md",
        "docs/ko-KR/skills/backend-patterns/SKILL.md",
        "docs/pt-BR/skills/x/SKILL.md",
        "docs/de-DE/skills/x/SKILL.md",
        "docs/vi-VN/skills/x/SKILL.md",
        # region-form not directly under docs but still anywhere
        "i18n/zh-CN/skills/x/SKILL.md",
        "translations/pt-BR/SKILL.md",
        # bare two-letter locale directly under an i18n root
        "docs/es/skills/api-design/SKILL.md",
        "docs/tr/skills/api-design/SKILL.md",
        "docs/fr/skills/x/SKILL.md",
        "i18n/de/SKILL.md",
        "locales/ru/SKILL.md",
        "lang/ja/skills/x/SKILL.md",
    ],
)
def test_drop_localized(path):
    assert is_localized_skill_path(path) is True


@pytest.mark.parametrize(
    "path",
    [
        # canonical ECC locations — never dropped
        ".agents/skills/api-design/SKILL.md",
        ".agents/skills/accessibility/SKILL.md",
        ".kiro/skills/api-design/SKILL.md",
        ".cursor/skills/api-design/SKILL.md",
        ".claude/skills/api-design/SKILL.md",
        "skills/api-design/SKILL.md",
        "skills/backend-patterns/SKILL.md",
        # native single-language repo layouts
        "SKILL.md",
        "my-skill/SKILL.md",
        "plugins/foo/skills/bar/SKILL.md",
        # bare two-letter that LOOKS like a locale but is NOT under an i18n root
        "skills/go/SKILL.md",      # "go" the language, not a locale dir
        "skills/es/SKILL.md",      # a skill literally named "es"
        "src/de/SKILL.md",         # "de" not under recognised i18n root
        # ambiguous codes never treated as locales even under i18n root
        "docs/go/SKILL.md",
        "docs/id/SKILL.md",
        "docs/no/SKILL.md",
    ],
)
def test_keep_canonical(path):
    assert is_localized_skill_path(path) is False


def test_filter_canonical_preserves_order_and_drops_localized():
    paths = [
        ".agents/skills/api-design/SKILL.md",
        "docs/es/skills/api-design/SKILL.md",
        "skills/backend-patterns/SKILL.md",
        "docs/ja-JP/skills/backend-patterns/SKILL.md",
    ]
    kept = filter_canonical_skill_paths(paths)
    assert kept == [
        ".agents/skills/api-design/SKILL.md",
        "skills/backend-patterns/SKILL.md",
    ]


def test_filter_handles_empty_and_none():
    assert filter_canonical_skill_paths([]) == []
    assert filter_canonical_skill_paths(None) == []
    assert is_localized_skill_path("") is False


# ---------------------------------------------------------------------------
# ECC real-sample regression: 519 localized drop, 362 canonical keep
# ---------------------------------------------------------------------------


def _ecc_sample_paths():
    """Reconstruct ECC's SKILL.md path distribution.

    Mirrors the real tree shape (verified against the live repo on 2026-06-16):
    519 localized copies under docs/<locale>/skills/<name>/SKILL.md across 6
    locales, and 362 canonical copies under .agents / .kiro / .cursor / .claude
    / skills roots. Skill name set is shared across locales (translation copies).
    """
    locales = ["es", "ja-JP", "ko-KR", "tr", "zh-CN", "zh-TW"]
    # 6 locales x ~86.5 skills => 519. Use a deterministic per-locale split so
    # the localized total is exactly 519 and canonical exactly 362.
    localized = []
    # distribute 519 across 6 locales
    per = [87, 87, 87, 86, 86, 86]  # sums to 519
    for loc, n in zip(locales, per):
        for i in range(n):
            localized.append(f"docs/{loc}/skills/skill-{i:03d}/SKILL.md")
    assert len(localized) == 519

    canonical = []
    # .agents/skills x 37, .kiro/skills x 43, .cursor/skills x 10,
    # .claude/skills x 1, skills/<name> x 271 => 362
    roots = [
        (".agents/skills", 37),
        (".kiro/skills", 43),
        (".cursor/skills", 10),
        (".claude/skills", 1),
        ("skills", 271),
    ]
    for root, n in roots:
        for i in range(n):
            canonical.append(f"{root}/skill-{i:03d}/SKILL.md")
    assert len(canonical) == 362

    return localized, canonical


def test_ecc_519_drop_362_keep():
    localized, canonical = _ecc_sample_paths()
    all_paths = localized + canonical
    kept = filter_canonical_skill_paths(all_paths)
    dropped = [p for p in all_paths if is_localized_skill_path(p)]

    assert len(all_paths) == 881
    assert len(dropped) == 519, "all 519 localized copies must be dropped"
    assert len(kept) == 362, "exactly the 362 canonical copies survive"
    # no canonical path got dropped
    assert all(not is_localized_skill_path(p) for p in canonical)
    # every localized path got dropped
    assert all(is_localized_skill_path(p) for p in localized)


# ---------------------------------------------------------------------------
# 2. Application point: skill_registry.scan_repo_via_api
# ---------------------------------------------------------------------------


def test_scan_repo_via_api_drops_localized(monkeypatch):
    import skill_registry

    localized, canonical = _ecc_sample_paths()
    all_paths = localized + canonical

    monkeypatch.setattr(
        skill_registry, "list_repo_files", lambda repo, branch, pattern="": list(all_paths)
    )

    fetched = []

    def fake_fetch(repo, path, branch):
        fetched.append(path)
        name = path.rsplit("/", 2)[-2]
        return f"---\nname: {name}\ndescription: a real coding skill for {name}\n---\nbody"

    monkeypatch.setattr(skill_registry, "fetch_raw_content", fake_fetch)

    entries = skill_registry.scan_repo_via_api("affaan-m/ECC", "HEAD")

    # Only canonical paths should have been fetched + parsed.
    assert len(fetched) == 362
    assert all(not is_localized_skill_path(p) for p in fetched)
    assert len(entries) == 362


# ---------------------------------------------------------------------------
# 3. Application point: sync_github_trending.classify_repo
# ---------------------------------------------------------------------------


def test_classify_repo_uses_canonical_skill_count():
    import sync_github_trending as sgt

    localized, canonical = _ecc_sample_paths()
    all_paths = localized + canonical

    def fake_list_files(repo, branch):
        return list(all_paths)

    kind, skill_paths, meta = sgt.classify_repo(
        "affaan-m/ECC", "HEAD", api_list_files=fake_list_files
    )

    assert kind == "skill"
    # total_files counts the whole tree, but skill_count must be canonical only
    assert meta["total_files"] == 881
    assert meta["skill_count"] == 362
    assert len(skill_paths) == 362
    assert all(not is_localized_skill_path(p) for p in skill_paths)


def test_megaapp_density_uses_canonical_count():
    """A repo whose SKILL.md count is inflated by translations should not be
    credited a falsely-high skill density."""
    import sync_github_trending as sgt

    # 1000 canonical skills among the canonical paths would be high density, but
    # only the canonical count must drive the density signal.
    localized = [f"docs/zh-CN/skills/s{i}/SKILL.md" for i in range(500)]
    canonical = [f"skills/s{i}/SKILL.md" for i in range(50)]
    filler = [f"src/file{i}.py" for i in range(3000)]
    all_paths = localized + canonical + filler

    _, _, meta = sgt.classify_repo(
        "x/y", "HEAD", api_list_files=lambda r, b: list(all_paths)
    )
    assert meta["skill_count"] == 50  # not 550
    density = sgt._skill_density_permille(meta["total_files"], meta["skill_count"])
    # canonical density = 50/3550*1000 ≈ 14.1 ; localized-inflated would be ~155
    assert density < 20.0


# ---------------------------------------------------------------------------
# 4. Application point: merge_index._apply_bundled_in_annotations
# ---------------------------------------------------------------------------


def test_bundle_synthesis_skips_localized_copies():
    from merge_index import _apply_bundled_in_annotations

    # Plugin bundling 1 canonical skill + 2 localized translations of it.
    # Only the canonical orphan should be synthesized into a standalone skill.
    plugin = {
        "id": "ecc",
        "type": "plugin",
        "name": "ECC",
        "source_url": "https://github.com/affaan-m/ECC",
        "bundle": {
            "skills_namespaces": [
                "ecc:api-design",       # canonical
                "ecc:api-design-es",    # localized (es)
                "ecc:api-design-ja",    # localized (ja-JP)
            ],
            "skill_paths": [
                ".agents/skills/api-design/SKILL.md",
                "docs/es/skills/api-design/SKILL.md",
                "docs/ja-JP/skills/api-design/SKILL.md",
            ],
            "source_repo": "affaan-m/ECC",
            "source_ref": "HEAD",
            "skills_count": 3,
        },
    }
    entries = [plugin]

    out = _apply_bundled_in_annotations(entries)

    synthesized = [e for e in out if e.get("source") == "plugin-bundled-skill"
                   or (e.get("type") == "skill" and e.get("bundled_in") == "ecc")]
    # Exactly one canonical skill synthesized; the two localized copies dropped.
    assert len(synthesized) == 1
    syn = synthesized[0]
    assert not is_localized_skill_path(syn.get("source_url", ""))
    assert "/es/" not in syn.get("source_url", "")
    assert "ja-JP" not in syn.get("source_url", "")

    # bundle bookkeeping stays aligned + corrected.
    b = plugin["bundle"]
    assert b["skills_namespaces"] == ["ecc:api-design"]
    assert b["skill_paths"] == [".agents/skills/api-design/SKILL.md"]
    assert b["skills_count"] == 1
    assert len(b["bundled_skill_ids"]) == 1


def test_bundle_synthesis_keeps_all_canonical():
    """No localized paths → nothing dropped, behaviour unchanged."""
    from merge_index import _apply_bundled_in_annotations

    plugin = {
        "id": "p1",
        "type": "plugin",
        "name": "P1",
        "source_url": "https://github.com/owner/p1",
        "bundle": {
            "skills_namespaces": ["p1:alpha", "p1:beta"],
            "skill_paths": [
                "skills/alpha/SKILL.md",
                ".agents/skills/beta/SKILL.md",
            ],
            "source_repo": "owner/p1",
            "source_ref": "HEAD",
            "skills_count": 2,
        },
    }
    out = _apply_bundled_in_annotations([plugin])
    synthesized = [e for e in out if e.get("type") == "skill"
                   and e.get("bundled_in") == "p1"]
    assert len(synthesized) == 2
    assert plugin["bundle"]["skills_namespaces"] == ["p1:alpha", "p1:beta"]
    assert plugin["bundle"]["skills_count"] == 2
