#!/usr/bin/env python3
"""一次性恢复被 sync_skills/sync_plugins_official blanket-overwrite 抹掉的 active-discovery entry。

背景：sync_skills.py / sync_plugins_official.py 历史上用 ``save_index(all_entries)`` 整文件
覆盖 per-type index，每轮抹掉上一轮 triage 写入的 github-trending / 促升 slug entry；triage
又因 known_repos 跳过已入库仓不再产出 → 被抹掉的 entry 永远补不回来（部分仓已掉出 top-300
候选，靠重新发现永远回不来）。

修复（sync_skills/sync_plugins_official 保留 foreign entry）部署后，本脚本从 git 历史
``798e6cf``（促升迁移后、source 已是终态）一次性回灌丢失的 entry：

- 取 ``git show 798e6cf:catalog/{skills,plugins}/index.json`` + ``catalog/index.json``
  里属于 active-discovery 域（source == github-trending 或 source ∈ 促升 slug 集）的 entry。
- merge_preserve 进 **当前** catalog/{skills,plugins}/index.json + catalog/index.json：当前
  entry 优先（先入为主），仅追加 id 不撞的历史 entry。skills 额外按归一 source_url 去重；
  plugins 仅按 id 去重（同 monorepo 多 plugin 合法共享 URL）；merged catalog/index.json
  混合多类型，同样仅按 id 去重（url-dedup 会误删同 monorepo 多 plugin）。
- 幂等：已存在的 id（+skills 的 url）跳过，重复运行不重复回灌。
- ``--dry-run``（默认）只打印命中/将回灌条数，不写盘。

只用标准库。用 ``git show <sha>:<path>`` 读历史版本（不 checkout）。

    python3 scripts/recover_trending_entries.py            # dry-run（默认，只报数）
    python3 scripts/recover_trending_entries.py --apply    # 真写盘
"""

import argparse
import json
import logging
import os
import subprocess
import sys
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from .utils import load_index, save_index, normalize_source_url  # type: ignore
    from .sync_github_trending import load_promoted_repos  # type: ignore
except ImportError:  # pragma: no cover - script-style invocation
    from utils import load_index, save_index, normalize_source_url  # type: ignore
    from sync_github_trending import load_promoted_repos  # type: ignore

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("recover_trending_entries")

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# 从这个 commit 回灌：促升迁移后，9 个促升仓已是促升 slug、220 条仍 github-trending，
# source 已是终态（选它而非上一轮 0db0532，避免回灌 source 不一致的中间态）。
DEFAULT_RECOVER_SHA = "798e6cf"

SKILLS_INDEX = os.path.join(REPO_ROOT, "catalog", "skills", "index.json")
PLUGINS_INDEX = os.path.join(REPO_ROOT, "catalog", "plugins", "index.json")
# merged final index（costrict-web bundle 的源），混合 skills+plugins+其他类型。
CATALOG_INDEX = os.path.join(REPO_ROOT, "catalog", "index.json")


def _load_promoted_slugs() -> set:
    """促升清单的 source_slug 集，文件缺失/损坏 → 空集（不崩）。"""
    try:
        return {r["source_slug"] for r in load_promoted_repos()}
    except Exception as e:  # noqa: BLE001
        logger.warning("加载促升清单失败，active-discovery 域退回仅 github-trending：%s", e)
        return set()


def _is_trending_owned(entry: dict, promoted_slugs: set) -> bool:
    """entry 是否属于 active-discovery 域（triage 唯一写入的 source 集）。"""
    s = entry.get("source")
    return s == "github-trending" or (s is not None and s in promoted_slugs)


def git_show_index(sha: str, rel_path: str) -> list:
    """``git show <sha>:<rel_path>`` 读历史版本 index（不 checkout）。

    缺失 / 解析失败 → 返回空 list（不崩，由调用方决定是否致命）。
    """
    try:
        out = subprocess.run(
            ["git", "show", f"{sha}:{rel_path}"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as e:
        logger.error("调用 git show 失败（%s:%s）：%s", sha, rel_path, e)
        return []
    if out.returncode != 0:
        logger.error(
            "git show %s:%s 失败（rc=%d）：%s",
            sha, rel_path, out.returncode, (out.stderr or "").strip(),
        )
        return []
    body = out.stdout
    if not body.strip():
        return []
    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        logger.error("解析历史 index 失败（%s:%s）：%s", sha, rel_path, e)
        return []
    return data if isinstance(data, list) else []


def merge_recover(
    historical_trending: list, current: list, dedup_url: bool
) -> tuple:
    """把 historical_trending 中 id（+可选归一 url）不撞 current 的 entry 追加进 current。

    current 优先（先入为主，绝不覆盖本轮新 entry）。返回 ``(combined, added, skipped)``。
    """
    seen_ids = set()
    seen_urls = set()
    for e in current:
        if e.get("id"):
            seen_ids.add(e["id"])
        if dedup_url:
            nu = normalize_source_url(e.get("source_url") or "")
            if nu:
                seen_urls.add(nu)
    combined = list(current)
    added = 0
    skipped = 0
    for e in historical_trending:
        eid = e.get("id") or ""
        if eid and eid in seen_ids:
            skipped += 1
            continue
        if dedup_url:
            nu = normalize_source_url(e.get("source_url") or "")
            if nu and nu in seen_urls:
                skipped += 1
                continue
            if nu:
                seen_urls.add(nu)
        if eid:
            seen_ids.add(eid)
        combined.append(e)
        added += 1
    return combined, added, skipped


def recover_one(
    label: str,
    index_path: str,
    rel_path: str,
    sha: str,
    promoted_slugs: set,
    dedup_url: bool,
    apply: bool,
) -> int:
    """恢复单个 per-type index。返回回灌（将回灌）的 entry 数。"""
    historical = git_show_index(sha, rel_path)
    hist_trending = [e for e in historical if _is_trending_owned(e, promoted_slugs)]
    current = load_index(index_path)

    combined, added, skipped = merge_recover(hist_trending, current, dedup_url=dedup_url)
    logger.info(
        "[%s] 历史 %d 条（其中 active-discovery %d 条），当前 %d 条 → 将回灌 %d 条"
        "（id%s 撞库跳过 %d 条）",
        label,
        len(historical),
        len(hist_trending),
        len(current),
        added,
        "+url" if dedup_url else "",
        skipped,
    )
    if added == 0:
        logger.info("[%s] 无需回灌（全部已在库 / 历史无 active-discovery）。", label)
        return 0

    # 排序保持 by-id 稳定（与 sync 写盘一致，便于 git diff 审阅）。
    combined.sort(key=lambda e: e.get("id", ""))
    if apply:
        save_index(combined, index_path)
        logger.info("[%s] 已写盘：%d 条（回灌 %d 条）。", label, len(combined), added)
    else:
        logger.info(
            "[%s] DRY-RUN：不写盘。加 --apply 真写盘（会把 %d 条 active-discovery entry "
            "回灌进 %s）。",
            label, added, index_path,
        )
    return added


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "一次性从 git 历史回灌被 blanket-overwrite 抹掉的 active-discovery "
            "(github-trending + 促升 slug) skill/plugin entry。"
        ),
    )
    parser.add_argument(
        "--sha",
        default=DEFAULT_RECOVER_SHA,
        help=f"从哪个 commit 回灌（默认 {DEFAULT_RECOVER_SHA}，促升迁移后 source 终态）。",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="真写盘（默认 dry-run，只打印命中 / 将回灌条数）。",
    )
    parser.add_argument(
        "--skills-index",
        default=SKILLS_INDEX,
        help=f"skills per-type index 路径（默认 {SKILLS_INDEX}）。",
    )
    parser.add_argument(
        "--plugins-index",
        default=PLUGINS_INDEX,
        help=f"plugins per-type index 路径（默认 {PLUGINS_INDEX}）。",
    )
    parser.add_argument(
        "--catalog-index",
        default=CATALOG_INDEX,
        help=f"merged final index 路径（默认 {CATALOG_INDEX}）。",
    )
    args = parser.parse_args(argv)

    promoted_slugs = _load_promoted_slugs()
    logger.info(
        "从 %s 回灌 active-discovery entry；促升 slug 集 %d 项；模式=%s。",
        args.sha, len(promoted_slugs), "APPLY" if args.apply else "DRY-RUN",
    )

    total = 0
    # skills 按 id+url 去重（对齐 sync_skills 的 _merge_keep_foreign(dedup_url=True)）。
    total += recover_one(
        "skills", args.skills_index, "catalog/skills/index.json",
        args.sha, promoted_slugs, dedup_url=True, apply=args.apply,
    )
    # plugins 仅按 id 去重——同 monorepo 多 plugin 合法共享 URL。
    total += recover_one(
        "plugins", args.plugins_index, "catalog/plugins/index.json",
        args.sha, promoted_slugs, dedup_url=False, apply=args.apply,
    )
    # merged catalog/index.json 混合多类型，仅按 id 去重（url-dedup 会误删同 monorepo 多 plugin）。
    total += recover_one(
        "catalog", args.catalog_index, "catalog/index.json",
        args.sha, promoted_slugs, dedup_url=False, apply=args.apply,
    )

    logger.info(
        "完成。合计%s回灌 %d 条 active-discovery entry。%s",
        "（将）" if not args.apply else "",
        total,
        "（dry-run，未写盘；加 --apply 落地）" if not args.apply else "",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
