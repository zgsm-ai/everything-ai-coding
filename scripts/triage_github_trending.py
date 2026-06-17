#!/usr/bin/env python3
"""GitHub trending triage（Stage B + Stage C）—— 把 sync_github_trending.py 产出的
候选表（``.github_trending_cache/candidates.json``）逐条判别后深拉，写入
``catalog/{skills,plugins}/index.json``。

**为什么独立成脚本**：CLAUDE.md「sync 脚本仅用标准库」是硬约束，sync_github_trending
保持 stdlib-only（Stage A 纯搜索）。本脚本是 **non-stdlib** 阶段，可 import
ai_resource_eval（judge / GitHubFetcher / EvalCache）做 LLM 真伪判别，因此从 sync 脚本
拆出来单独跑（带 LLM secrets + 独立 timeout）。

**分阶段（拉树前置 LLM 判别，主修 CI 超时）**：

  Stage B（拉树前，无整树）：
    1. plugin 探测：廉价探 .claude-plugin/marketplace.json / 根 marketplace.json
       （固定路径 raw GET，复用 marketplace_verifier._fetch_manifest，**不拉 Tree**）。
       命中 → plugin 路由（marketplace_verified 是权威信号，不跑 LLM is_primary_skill）。
    2. 否则 LLM 判别：拉 README（raw，不拉树）→ 复用 eval_bridge._authenticity_one
       的 is_primary_skill 判断（它 fetch 的就是 ["SKILL.md","README.md"]、不拉整树）。
       判 false（app/framework）→ **丢弃，不进 Stage C**；判 true → skill 路由。

  Stage C（仅存活者深拉）：
    - skill：sync_github_trending.build_skill_entries → skill_registry.scan_repo_via_api
      （Tree + 逐 SKILL.md raw）+ hard_filter + filter_canonical_skill_paths。
    - plugin：sync_github_trending.sync_plugins → sync_plugins_official.sync_one_source
      / _entry_from_plugin。**bundle 检测可降级**（PluginContentFetcher 缺省 → bundle
      置零，加速，下游 enrich/下轮补）——优先保证不超时。

  写盘：merge-preserve 写 catalog/{skills,plugins}/index.json，**边处理边增量写 +
  wall-clock 时间预算**（到点 flush 退出），超时也保住已完成的。

增量：跨轮靠 known_repos（上轮入库的下轮 Stage A 预过滤）+ triage verify_cache
（按 full_name + pushed_at 命中跳过昂贵判别 + 深拉）。失败仓不缓存（下次重试）。
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sync_github_trending as sgt  # noqa: E402  Stage A 产物 + Stage C 构造器
from utils import load_index, save_index  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("triage_github_trending")

# --- 参数（env 可覆盖）-----------------------------------------------------
# wall-clock 时间预算（秒）：到点 flush 已完成的 entry 并退出，避免被 CI 硬 kill 全丢。
# 默认 1800s = 30min，比 triage CI step timeout（建议 40min）短，留 10min 给写盘 + cache save。
WALL_BUDGET_SECONDS = int(os.environ.get("TRIAGE_WALL_BUDGET", "1800"))
# 每处理 N 个存活候选 flush 一次 index + verify_cache（增量保险）。
FLUSH_EVERY = int(os.environ.get("TRIAGE_FLUSH_EVERY", "10"))
EVAL_CACHE_DIR = os.environ.get("EVAL_CACHE_DIR", ".eval_cache")
EVAL_INCREMENTAL = os.environ.get("EVAL_INCREMENTAL", "true").lower() != "false"


# --- Stage B-1：plugin 探测（廉价 raw GET，不拉 Tree）-----------------------

def probe_plugin(repo_slug, _fetch_manifest=None):
    """探测仓库是否含 marketplace.json（plugin 标志）。命中返回 True。

    复用 marketplace_verifier._fetch_manifest 的 4 候选路径 raw 探测
    （.claude-plugin/marketplace.json / marketplace.json × main / master），
    **不拉 Tree**。``_fetch_manifest`` 可注入便于测试。
    """
    if _fetch_manifest is None:
        import marketplace_verifier
        _fetch_manifest = marketplace_verifier._fetch_manifest
    try:
        manifest = _fetch_manifest(repo_slug)
    except Exception as e:  # noqa: BLE001 - 探测失败保守当非 plugin，交 LLM 判别
        logger.debug("plugin 探测 %s 失败：%s", repo_slug, e)
        return False
    return isinstance(manifest, dict)


# --- Stage B-2：LLM is_primary_skill 判别（拉 README，不拉 Tree）------------

class _LLMJudge:
    """封装 eval_bridge 的 judge + fetcher + cache，对单候选做 is_primary_skill 判别。

    懒加载 ai_resource_eval（non-stdlib）；无 LLM key / 包缺失时 ``available`` 为 False，
    triage 退化为「保守放行」（判 True，交 eval 层 authenticity backstop + governor）。
    """

    def __init__(self, cache_dir=EVAL_CACHE_DIR, incremental=EVAL_INCREMENTAL):
        self.available = False
        self.incremental = incremental
        try:
            import eval_bridge
            from ai_resource_eval.cache import EvalCache
            from ai_resource_eval.fetcher import GitHubFetcher
        except ImportError as e:
            logger.warning("ai-resource-eval 不可用，LLM 判别跳过（保守放行）：%s", e)
            return
        self._eval_bridge = eval_bridge
        judge = eval_bridge._build_judge()
        if judge is None:
            logger.warning("未配置 LLM API key，LLM 判别跳过（保守放行）")
            return
        from pathlib import Path
        cp = Path(cache_dir)
        cp.mkdir(parents=True, exist_ok=True)
        self._judge = judge
        self._cache = EvalCache(db_path=cp / "eval_cache.db")
        self._rubric_version = eval_bridge._authenticity_rubric_version()
        self._fetcher = GitHubFetcher(content_paths=["SKILL.md", "README.md"])
        self.available = True

    def is_primary_skill(self, candidate):
        """返回 ``(verdict, reason)``：verdict ∈ {True, False, None}。

        True=主体就是 skill（存活）；False=app/framework（丢弃）；None=判别不可用 /
        失败 → 保守放行（当 True 处理，但标注 reason 让调用方记账）。
        """
        if not self.available:
            return True, "llm-unavailable"
        full = candidate["full_name"]
        # 合成最小 entry 喂 _authenticity_one（它 fetch README/SKILL.md，不拉树）。
        entry = {
            "id": full,
            "name": full.split("/", 1)[-1],
            "type": "skill",
            "description": candidate.get("description") or "",
            "source_url": f"https://github.com/{full}",
            "tags": candidate.get("topics") or [],
        }
        try:
            result = self._eval_bridge._authenticity_one(
                entry, self._judge, self._fetcher, self._cache,
                self._rubric_version, self.incremental,
            )
        except Exception as e:  # noqa: BLE001 - 判别失败保守放行，不缓存
            logger.debug("LLM 判别 %s 失败（保守放行）：%s", full, e)
            return True, "llm-error"
        if result is None:
            # 内容不足 / LLM 失败 → 保守放行（交 eval 层 backstop）
            return True, "llm-no-result"
        return bool(result.get("is_primary_skill")), str(result.get("reason") or "")


# --- 写盘（merge-preserve，复用 sync_github_trending.merge_preserve）---------

def flush_skills(skill_entries, path):
    """把累计的 skill entry merge-preserve 写入 index。返回新接受数。"""
    if not skill_entries:
        return 0
    existing = load_index(path) if os.path.exists(path) else []
    combined, accepted = sgt.merge_preserve(skill_entries, existing, dedup_url=True)
    if accepted:
        save_index(combined, path)
    return accepted


def flush_plugins(plugin_entries, path):
    """把累计的 plugin entry merge-preserve（id-only）写入 index。返回新接受数。"""
    if not plugin_entries:
        return 0
    existing = load_index(path) if os.path.exists(path) else []
    combined, accepted = sgt.merge_preserve(plugin_entries, existing, dedup_url=False)
    if accepted:
        save_index(combined, path)
    return accepted


# --- 主 triage 流程 --------------------------------------------------------

def triage(candidates, last_synced, judge=None, plugin_probe=probe_plugin,
           skills_output=sgt.SKILLS_INDEX, plugins_output=sgt.PLUGINS_INDEX,
           wall_budget=WALL_BUDGET_SECONDS, flush_every=FLUSH_EVERY,
           now=time.monotonic):
    """对候选表逐条 Stage B 判别 + Stage C 深拉，增量写 index。返回 stats。

    judge：``_LLMJudge`` 实例（None 则内部构造）。``now`` 注入便于测试 wall-clock。
    """
    if judge is None:
        judge = _LLMJudge()

    verify_cache = sgt.load_verify_cache()
    new_cache = dict(verify_cache)  # 先并入旧 cache，增量落盘不丢未碰条目

    stats = {
        "total": len(candidates), "processed": 0,
        "plugin_repos": 0, "skill_repos": 0,
        "llm_dropped": 0, "skill_no_entry": 0, "errored": 0,
        "cache_hit": 0, "budget_exhausted": False, "llm_unavailable": 0,
    }
    pending_skills = []  # 累计待 flush 的 skill entry
    pending_plugin_cfgs = []  # 累计待 build 的 plugin source_cfg
    written_skills = 0
    written_plugins = 0
    start = now()

    def _do_flush():
        nonlocal pending_skills, pending_plugin_cfgs, written_skills, written_plugins
        if pending_skills:
            written_skills += flush_skills(pending_skills, skills_output)
            pending_skills = []
        if pending_plugin_cfgs:
            plugin_entries = sgt.sync_plugins(pending_plugin_cfgs, last_synced)
            written_plugins += flush_plugins(plugin_entries, plugins_output)
            pending_plugin_cfgs = []
        sgt.save_verify_cache(new_cache)

    for cand in candidates:
        # wall-clock 预算：到点 flush 已完成的并退出，超时也保住进度。
        if now() - start >= wall_budget:
            stats["budget_exhausted"] = True
            logger.warning(
                "triage wall-clock 预算 %ds 用尽，已处理 %d/%d，flush 退出",
                wall_budget, stats["processed"], stats["total"],
            )
            break

        full = cand.get("full_name")
        if not full or "/" not in full:
            continue
        branch = cand.get("default_branch") or "main"
        pushed_at = cand.get("pushed_at") or ""

        try:
            # 增量 cache：pushed_at 未变且有终态 kind → 跳过昂贵判别/深拉。
            cached = verify_cache.get(full)
            if (cached and cached.get("pushed_at") == pushed_at
                    and cached.get("kind") in ("plugin", "skill", "app", "none")):
                stats["cache_hit"] += 1
                # plugin/skill 上轮已入库（known_repos 下轮预过滤）；此处只需不重复深拉。
                stats["processed"] += 1
                continue

            # Stage B-1：plugin 探测（廉价，不拉树）
            if plugin_probe(full):
                stats["plugin_repos"] += 1
                pending_plugin_cfgs.append({
                    "id": sgt.SOURCE_ID,
                    "repo_slug": full,
                    "branch": branch,
                    "source_priority": sgt.PLUGIN_SOURCE_PRIORITY,
                })
                new_cache[full] = {"pushed_at": pushed_at, "kind": "plugin"}
                stats["processed"] += 1
                if flush_every and stats["processed"] % flush_every == 0:
                    _do_flush()
                continue

            # Stage B-2：LLM is_primary_skill 判别（拉 README，不拉树）
            verdict, reason = judge.is_primary_skill(cand)
            if reason in ("llm-unavailable", "llm-error", "llm-no-result"):
                stats["llm_unavailable"] += 1
            if verdict is False:
                # app/framework → 丢弃，不进 Stage C。缓存为 app 避免反复判别。
                stats["llm_dropped"] += 1
                logger.info("LLM 判 app 丢弃 %s：%s", full, reason)
                new_cache[full] = {"pushed_at": pushed_at, "kind": "app"}
                stats["processed"] += 1
                continue

            # Stage C：skill 深拉（仅存活者）
            item = {
                "stargazers_count": cand.get("stars") or 0,
                "pushed_at": pushed_at,
            }
            built = sgt.build_skill_entries(full, branch, item, last_synced)
            if built:
                stats["skill_repos"] += 1
                pending_skills.extend(built)
                new_cache[full] = {"pushed_at": pushed_at, "kind": "skill"}
            else:
                # 无 SKILL.md / 全被 hard_filter 刷掉 → 不缓存空结果，下次重试。
                stats["skill_no_entry"] += 1
            stats["processed"] += 1
            if flush_every and stats["processed"] % flush_every == 0:
                _do_flush()
        except Exception as e:  # noqa: BLE001 - 单仓失败不拖垮整轮，不缓存（下次重试）
            stats["errored"] += 1
            logger.warning("候选仓 %s triage 失败（跳过，下次重试）：%s", full, e)

    # 末尾 flush 剩余 pending + cache
    _do_flush()
    stats["written_skills"] = written_skills
    stats["written_plugins"] = written_plugins
    return stats


# --- main ------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", default=sgt.CANDIDATES_PATH,
                        help="Stage A 候选表路径")
    parser.add_argument("--skills-output", default=sgt.SKILLS_INDEX)
    parser.add_argument("--plugins-output", default=sgt.PLUGINS_INDEX)
    parser.add_argument("--wall-budget-seconds", type=int, default=WALL_BUDGET_SECONDS)
    args = parser.parse_args(argv)

    candidates = sgt.load_candidates(args.candidates)
    if not candidates:
        logger.warning("候选表为空 / 缺失（%s），triage 无事可做", args.candidates)
        return 0

    last_synced = date.today().isoformat()
    stats = triage(
        candidates, last_synced,
        skills_output=args.skills_output, plugins_output=args.plugins_output,
        wall_budget=args.wall_budget_seconds,
    )

    # WARN 汇总：一轮 triage 健康度在 CI 日志可见（不静默）。
    logger.warning(
        "GitHub trending triage 健康度：候选=%d｜已处理=%d｜plugin 仓=%d｜skill 仓=%d"
        "（写入 skill=%d / plugin=%d）｜LLM 判 app 丢弃=%d｜skill 无产出=%d｜异常=%d"
        "｜cache 命中=%d｜LLM 不可用降级=%d｜预算耗尽=%s",
        stats["total"], stats["processed"], stats["plugin_repos"], stats["skill_repos"],
        stats.get("written_skills", 0), stats.get("written_plugins", 0),
        stats["llm_dropped"], stats["skill_no_entry"], stats["errored"],
        stats["cache_hit"], stats["llm_unavailable"], stats["budget_exhausted"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
