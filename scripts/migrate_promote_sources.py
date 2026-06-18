#!/usr/bin/env python3
"""一次性迁移脚本：把 catalog 里命中促升清单的仓、``source==github-trending`` 的
**旧** entry 的 ``source`` 字段改写为对应专属 per-repo slug。

**为什么需要**：促升只影响 triage **新构造**的 entry；catalog 现存 1500+ 条
``source=github-trending``（其中促升目标仓占大头）因 triage 走 merge-preserve
（按 id 跳过已存在，不覆盖字段）仍挂 github-trending。不迁移就会出现"同仓旧 entry
挂 github-trending、新 entry 挂专属 slug"的 source 分裂。

**安全性**：
- 仅改写 entry 当前 ``source == "github-trending"`` 且 ``source_url`` 反解的
  ``owner/repo`` **大小写不敏感**命中促升清单的条目。
- 非促升仓、非 github-trending 来源的 entry 一律不动（不误伤）。
- **幂等**：重跑不再改动（已是目标 slug 的 source != github-trending，自然跳过）。
- ``--dry-run`` 只打印改写计划，不写盘。

**对 dedup / eval cache 无影响**：``source`` 字段不进 dedup identity-key
（utils.deduplicate 按 id / source_url / identity-key），也不进 content_hash
（eval cache 命中不重评）。迁移 per-type index 后可重跑 merge_index.py 重生成
catalog/index.json，或直接迁移本脚本覆盖的三个文件（推荐，省一次 merge）。

仅用标准库（只读写 json）。
"""

import argparse
import json
import logging
import os
import re
import sys

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPTS_DIR, ".."))
CATALOG_DIR = os.path.join(REPO_ROOT, "catalog")
PROMOTED_REPOS_PATH = os.path.join(SCRIPTS_DIR, "trending_promoted_repos.json")

# 迁移覆盖的三个文件：per-type skills/plugins index + 全量 catalog/index.json。
DEFAULT_TARGETS = [
    os.path.join(CATALOG_DIR, "skills", "index.json"),
    os.path.join(CATALOG_DIR, "plugins", "index.json"),
    os.path.join(CATALOG_DIR, "index.json"),
]

GITHUB_TRENDING_SOURCE = "github-trending"

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("migrate_promote_sources")


def owner_repo_from_url(url):
    """从任意 GitHub URL 提取小写 ``owner/repo``；非 GitHub / 无法解析返回 None。

    与 sync_github_trending.owner_repo_from_url 同款解析（去 .git 后缀、小写归一），
    但本脚本 stdlib-only 不引入镜像归一（促升清单不含镜像仓）。
    """
    if not url:
        return None
    m = re.search(r"github\.com/([^/]+)/([^/#?]+)", url, re.IGNORECASE)
    if not m:
        return None
    repo = m.group(2)
    if repo.endswith(".git"):
        repo = repo[:-4]
    return f"{m.group(1).lower()}/{repo.lower()}"


def load_promoted_map(path=PROMOTED_REPOS_PATH):
    """加载促升清单，返回 ``{repo.lower(): source_slug}`` map（大小写不敏感命中）。

    写入值永远是清单里（已小写的）``source_slug``。文件缺失 / 损坏 → 空 map（无迁移）。
    """
    if not os.path.exists(path):
        logger.warning("促升清单不存在，无可迁移：%s", path)
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.error("促升清单读取失败：%s", e)
        return {}
    raw = data.get("repos") if isinstance(data, dict) else data
    if not isinstance(raw, list):
        return {}
    out = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        repo = (item.get("repo") or "").strip()
        slug = (item.get("source_slug") or "").strip()
        if "/" in repo and "/" in slug:
            out[repo.lower()] = slug
    return out


def migrate_entries(entries, promoted_map):
    """对一组 entry 原地改写 source。返回改写条数。

    仅当 entry 当前 ``source == github-trending`` 且 source_url 反解的 owner/repo
    命中促升清单时改写为对应 slug。已是目标 slug / 非 github-trending / 非促升仓不动。
    """
    changed = 0
    for e in entries:
        if not isinstance(e, dict):
            continue
        if (e.get("source") or "") != GITHUB_TRENDING_SOURCE:
            continue
        slug = owner_repo_from_url(e.get("source_url") or "")
        if not slug:
            continue
        target = promoted_map.get(slug)
        if target and e["source"] != target:
            e["source"] = target
            changed += 1
    return changed


def migrate_file(path, promoted_map, dry_run=False):
    """迁移单个 index.json 文件。返回改写条数（文件缺失返回 0）。"""
    if not os.path.exists(path):
        logger.warning("目标文件不存在，跳过：%s", path)
        return 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            entries = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.error("读取失败，跳过 %s：%s", path, e)
        return 0
    if not isinstance(entries, list):
        logger.warning("文件结构非数组，跳过：%s", path)
        return 0
    changed = migrate_entries(entries, promoted_map)
    rel = os.path.relpath(path, REPO_ROOT)
    if changed and not dry_run:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
            f.write("\n")
        logger.info("%s：改写 %d 条 source（已写盘）", rel, changed)
    elif changed:
        logger.info("%s：将改写 %d 条 source（--dry-run，不写盘）", rel, changed)
    else:
        logger.info("%s：无可改写条目", rel)
    return changed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="只打印改写计划，不写盘")
    parser.add_argument("--targets", nargs="*", default=DEFAULT_TARGETS,
                        help="要迁移的 index.json 路径（默认 skills/plugins/catalog 三个）")
    parser.add_argument("--promoted", default=PROMOTED_REPOS_PATH,
                        help="促升清单路径")
    args = parser.parse_args(argv)

    promoted_map = load_promoted_map(args.promoted)
    if not promoted_map:
        logger.warning("促升清单为空，迁移无事可做")
        return 0
    logger.info("促升清单加载 %d 个仓", len(promoted_map))

    total = 0
    for path in args.targets:
        total += migrate_file(path, promoted_map, dry_run=args.dry_run)
    logger.info("迁移完成：共改写 %d 条 source%s",
                total, "（--dry-run，未写盘）" if args.dry_run else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
