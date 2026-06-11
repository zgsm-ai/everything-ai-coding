"""Bridge between ai-resource-eval harness and the catalog pipeline.

Reads catalog entries, delegates evaluation to the local harness package
(ai-resource-eval), and maps results back as flattened score-only
fields (no evidence/missing/suggestion).
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

# Sibling-module imports (work whether the caller invokes ``python scripts/X.py``
# from the repo root — which puts ``scripts/`` on sys.path — or imports
# ``scripts.eval_bridge`` from the repo root with the package layout.)
try:
    from enrichment_checkpoint import Checkpoint
    from eval_failure_log import FailureLog
except ImportError:  # pragma: no cover - exercised in tests/explicit package use
    from scripts.enrichment_checkpoint import Checkpoint  # type: ignore[no-redef]
    from scripts.eval_failure_log import FailureLog  # type: ignore[no-redef]

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ai_resource_eval.runner import EvalRunner

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Skills.sh 增量评估短路（Section 6）
# ---------------------------------------------------------------------------
#
# 设计意图：
#   skills.sh 上游每周输出的 install_count 抖动通常 < 20%，且 README 内容
#   长期稳定（Tier 1 源条目均为成熟仓库）。对这类 stable 条目，可避免重复
#   fetch + LLM 调用——直接复用 SQLite cache 中的 EvalResult。
#
# 缓存键完整性（P1 修复）：
#   短路 lookup 复用 runner 的标准 cache key 语义：
#       cache_key = SHA256("__full__" : content_hash : rubric_version)
#   实现上以 (entry_id, rubric_version) 在 SQLite 中定位最近一条 row，
#   读出其 content_hash，再用 EvalCache.make_key() 重建 cache_key + cache.get()
#   走 expiry 校验。这保证：
#     1. rubric v1→v2 升级后，旧 row 的 rubric_version 与当前不匹配 → 不复用
#     2. 已过期 row 由 cache.get() 自然 miss
#     3. 若 install_count 漂移在 ±20% 内，diff.json 视为「内容稳定」信号，
#        允许复用历史 content_hash 对应的结果（这是 skills.sh 源的契约：
#        当 install drift 小，README 大概率未变；上游真改 README 时通常伴随
#        install 数量重新分布，会被 diff 识别为 changed）
#
# 触发条件（全部满足才短路）：
#   1. entry 由 skills.sh 派生（具备 skills_sh_url 字段；merge_index 合并到
#      高优先级 entry 后 source 字段会变，但 skills_sh_url 仍保留）
#   2. 由 skills_sh_url 反推的 raw skills_sh id 不在 diff.json 的
#      added/changed/removed 集合中
#   3. SQLite cache 命中（含 rubric_version 校验 + expiry 校验）
# ---------------------------------------------------------------------------

INSTALL_COUNT_DRIFT_THRESHOLD = 0.20  # ±20% 视为 stable

_DIFF_PATH_DEFAULT = Path(__file__).resolve().parent.parent / ".skills_sh_cache" / "diff.json"

# Section 8: 新增源（mcp_registry / windsurfrules）的短路 sidecar 路径
_MCP_REGISTRY_DIFF_PATH_DEFAULT = (
    Path(__file__).resolve().parent.parent / ".mcp_registry_cache" / "diff.json"
)
_WINDSURFRULES_REPO_HOSTS = (
    "schneidersam/awesome-windsurfrules",
    "balqaasem/awesome-windsurfrules",
)

# skills.sh raw id 反推：与 sync_skills_sh._sanitize_id_segment / _make_id 同款逻辑
# 必须与 sync_skills_sh.py 保持一致，否则 short-circuit 与 diff.json 比对不上
_ID_INVALID_RE = re.compile(r"[^a-z0-9-]+")

# ---------------------------------------------------------------------------
# Config resolution
# ---------------------------------------------------------------------------

_TYPE_TO_TASK = {
    "mcp": "mcp_server",
    "skill": "skill",
    "rule": "rule",
    "prompt": "prompt",
    # plugin 类型走 health-only task config（无 LLM 维度，4 健康信号 + enrichment）
    "plugin": "plugin",
}


def resolve_task_name(resource_type: str) -> str:
    """Return the built-in task config name for a resource type."""
    return _TYPE_TO_TASK.get(resource_type, "skill")


# ---------------------------------------------------------------------------
# Skills.sh 增量短路 helpers（Section 6）
# ---------------------------------------------------------------------------

def _install_count_drift_within(
    old: int | float | None,
    new: int | float | None,
    threshold: float = INSTALL_COUNT_DRIFT_THRESHOLD,
) -> bool:
    """判断 install_count 漂移是否 ≤ ±threshold（默认 ±20%）。

    约定：
    - 任一侧为 None / 0 / 负数：视为「不可比较」，返回 False（不短路）
    - 两侧均为正数：按 |new-old|/old 计算
    """
    try:
        o = float(old) if old is not None else 0.0
        n = float(new) if new is not None else 0.0
    except (TypeError, ValueError):
        return False
    if o <= 0 or n <= 0:
        return False
    return abs(n - o) / o <= threshold


def load_skills_sh_diff(diff_path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """读取 .skills_sh_cache/diff.json；不存在或损坏返回空 dict。

    返回结构（来自 sync_skills_sh.compute_diff）：
      {
        "added": [id, ...],
        "changed_install_count": [{id, old, new, pct}, ...],
        "removed": [id, ...],
        "stable": <int>
      }
    """
    path = Path(diff_path) if diff_path else _DIFF_PATH_DEFAULT
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        return data
    except (OSError, json.JSONDecodeError) as exc:
        logger.debug("Failed to read skills_sh diff at %s: %s", path, exc)
        return {}


def _diff_unstable_ids(diff: dict[str, Any]) -> set[str]:
    """从 diff.json 提取「不稳定」id 集合（added / changed / removed 并集）。"""
    if not diff:
        return set()
    unstable: set[str] = set()
    unstable.update(diff.get("added") or [])
    unstable.update(diff.get("removed") or [])
    for item in diff.get("changed_install_count") or []:
        if isinstance(item, dict) and item.get("id"):
            unstable.add(item["id"])
    return unstable


def _sanitize_id_segment(s: str) -> str:
    """与 sync_skills_sh._sanitize_id_segment 保持一致的清洗逻辑。"""
    s = (s or "").lower().strip()
    s = re.sub(r"[\s_]+", "-", s)
    s = _ID_INVALID_RE.sub("-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s


def _make_skills_sh_raw_id(skill_id: str, owner: str, repo: str = "") -> str:
    """与 sync_skills_sh._make_id 保持一致：<skillId>-<owner>[-<repo>]。

    必须复用相同算法，否则 short-circuit 与 diff.json 的 id 集合无法对应。
    """
    sk = _sanitize_id_segment(skill_id) or "skill"
    ow = _sanitize_id_segment(owner) or "unknown"
    rp = _sanitize_id_segment(repo)
    parts = [sk, ow]
    if rp and rp != sk:
        parts.append(rp)
    return "-".join(parts)


def _skills_sh_raw_id_from_entry(entry: dict[str, Any]) -> str | None:
    """从 entry.skills_sh_url 反推 skills.sh raw id（diff.json 的同款 id）。

    P2-1 修复点：merge_index 把 skills.sh row 合并到更高优先级 winner 后，
    winner 的 id/source 已变（不再是 skills-sh），但 _merge_skills_sh_fields
    会把 skills_sh_url 拷贝到 winner 上。因此用 skills_sh_url 反推的 raw id
    是判定「这条 entry 是否对应某个 skills.sh row」的唯一稳定 key。

    skills_sh_url 形态：``https://skills.sh/{owner}/{repo}/{skillId}``
    返回 None 表示 entry 非 skills.sh 派生（无 url 或解析失败）。
    """
    url = entry.get("skills_sh_url") or ""
    if not url:
        return None
    try:
        parsed = urlparse(url)
    except (TypeError, ValueError):
        return None
    if parsed.netloc.lower() != "skills.sh":
        return None
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 3:
        return None
    owner, repo, skill_id = parts[0], parts[1], parts[2]
    return _make_skills_sh_raw_id(skill_id, owner, repo)


def _is_skills_sh_derived(entry: dict[str, Any]) -> bool:
    """判定 entry 是否承载 skills.sh 派生数据。

    放宽自原 ``source == "skills-sh"``：merge 后 winner 的 source 字段会被
    高优先级源覆盖，但 skills_sh_url 字段会保留（见 utils._SKILLS_SH_MERGE_FIELDS）。
    任何携带 skills_sh_url 的 entry 都视为 skills.sh 派生候选。
    """
    if (entry.get("source") or "") == "skills-sh":
        return True
    return bool(entry.get("skills_sh_url"))


# 向后兼容别名：保持已有测试 / 外部调用点可用
_is_skills_sh_entry = _is_skills_sh_derived


def _lookup_cached_result(
    cache: Any,
    entry_id: str,
    rubric_version: str | None = None,
) -> dict[str, Any] | None:
    """根据 entry_id (+ rubric_version) 在 SQLite cache 中复用历史 EvalResult。

    P1 修复：先通过 (entry_id, rubric_version) 定位最近一条 row 的
    content_hash，再用 EvalCache.make_key("__full__", content_hash, rubric_version)
    重建标准 cache_key，最后调 cache.get() 走完整 expiry 校验。这样：

    - rubric_version 不匹配（v1→v2 升级）→ 第一步 SELECT 为空 → 返回 None
    - rubric 匹配但 row 已过期 → cache.get() 失败 → 返回 None
    - 全部匹配 → 复用 result_json，标记 model_id="__cached__"

    rubric_version 为 None 时退化为旧行为（仅按 entry_id 取最新），保留给
    单元测试中无 runner 上下文的场景。
    """
    try:
        from datetime import datetime, timezone

        from ai_resource_eval.cache import EvalCache  # 延迟 import，避免硬依赖

        conn = cache._conn()  # noqa: SLF001 — bridge 内部短路，访问私有连接

        # 优先按 (entry_id, rubric_version) 定位；无 rubric 时退化为按 entry_id
        if rubric_version:
            row = conn.execute(
                """
                SELECT cache_key, content_hash, result_json, expires_at
                FROM eval_cache
                WHERE entry_id = ? AND rubric_version = ?
                ORDER BY evaluated_at DESC
                LIMIT 1
                """,
                (entry_id, rubric_version),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT cache_key, content_hash, result_json, expires_at
                FROM eval_cache
                WHERE entry_id = ?
                ORDER BY evaluated_at DESC
                LIMIT 1
                """,
                (entry_id,),
            ).fetchone()
        if row is None:
            return None

        # 当 rubric 已知，重建 runner 标准 cache_key 并通过 cache.get() 走 expiry 校验。
        # 这与 runner._check_cache 保持完全一致的失效语义。
        if rubric_version:
            content_hash = row["content_hash"]
            cache_key = EvalCache.make_key(
                metric="__full__",
                content_hash=content_hash,
                rubric_version=rubric_version,
            )
            cached_entry = cache.get(cache_key)
            if cached_entry is None:
                return None
            try:
                result = json.loads(cached_entry.result_json)
            except (TypeError, ValueError):
                return None
        else:
            # 兼容路径：手动做过期判定 + 解析 result_json
            expires_at_str = row["expires_at"]
            if expires_at_str:
                ts = (
                    expires_at_str.replace("Z", "+00:00")
                    if expires_at_str.endswith("Z")
                    else expires_at_str
                )
                try:
                    expires_dt = datetime.fromisoformat(ts)
                    if expires_dt.tzinfo is None:
                        expires_dt = expires_dt.replace(tzinfo=timezone.utc)
                    if expires_dt < datetime.now(timezone.utc):
                        return None
                except ValueError:
                    return None
            try:
                result = json.loads(row["result_json"])
            except (TypeError, ValueError):
                return None

        if not isinstance(result, dict):
            return None
        # 标记 cached 复用（与 runner 内部 `__cached__` 对齐，便于下游统计）
        result["model_id"] = "__cached__"
        return result
    except Exception as exc:  # noqa: BLE001
        logger.debug("Cache lookup failed for %s: %s", entry_id, exc)
        return None


def _select_short_circuit_entries(
    entries: list[dict[str, Any]],
    cache: Any,
    diff: dict[str, Any] | None,
    rubric_version: str | None = None,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """对 skills.sh 派生条目预筛短路：返回 (短路命中的 results, 仍需评估的 entries)。

    短路条件（Section 6.1 + P1/P2-1 修复）：
    - entry 携带 skills_sh_url（merge 后 winner 也保留此字段）
    - 由 skills_sh_url 反推的 raw skills.sh id 不在 diff.json 的 unstable 集合
    - cache 命中：rubric_version 匹配 + 未过期（走 runner 标准 cache_key）

    cache 中查询使用 entry 的 catalog id（即 winner 的 id），因为 cache 在首次
    评估时是用 catalog id 写入的；diff lookup 才使用 raw skills_sh id。
    """
    if cache is None:
        return {}, list(entries)

    unstable = _diff_unstable_ids(diff or {})
    short_circuit: dict[str, dict[str, Any]] = {}
    remaining: list[dict[str, Any]] = []

    for entry in entries:
        eid = entry.get("id")
        if not eid:
            remaining.append(entry)
            continue
        if not _is_skills_sh_derived(entry):
            remaining.append(entry)
            continue
        # diff.json 提供时优先使用；缺失（首次 sync）则跳过短路、走完整评估
        if not diff:
            remaining.append(entry)
            continue
        # 优先用 skills_sh_url 反推的 raw id 比对 diff（覆盖 merged entry）；
        # 若反推失败则退化用 catalog id（向后兼容尚未合并的 skills.sh-only entry）
        raw_id = _skills_sh_raw_id_from_entry(entry) or eid
        if raw_id in unstable:
            remaining.append(entry)
            continue
        cached = _lookup_cached_result(cache, eid, rubric_version=rubric_version)
        if cached is None:
            remaining.append(entry)
            continue
        short_circuit[eid] = cached

    return short_circuit, remaining


# ---------------------------------------------------------------------------
# Section 8: mcp_registry 增量短路
# ---------------------------------------------------------------------------
#
# 设计意图（与 skills.sh 同款，但用 registry 自身的 diff 信号）：
#   sync_mcp_registry.py 写出 .mcp_registry_cache/diff.json，结构如下：
#       {
#         "added":           [<entry_id>, ...],
#         "removed":         [<entry_id>, ...],
#         "status_changed":  [{"id": <entry_id>, "old": "...", "new": "..."}, ...],
#         "version_bumped":  [{"id": <entry_id>, "old": "...", "new": "..."}, ...],
#         "stable":          <int>,
#       }
#
#   其中 id 即 normalize_entry 生成的 catalog entry id（kebab + sha8）。
#   这意味着对 registry 主索引中的 entry，diff id 与 entry.id 一一对应；
#   对 merge 后被高优先级 GitHub 源覆盖的 winner，winner.id 与 registry id
#   不相等——这些 entry 的 short-circuit 命中率较低（diff 查不到 → 视为
#   unstable，走完整评估），属于安全 fallback。
#
# 触发条件（全部满足才短路）：
#   1. entry 由 mcp_registry 派生：source_url 是 registry URL，或携带
#      mcp_registry_status 字段（merge 后 winner 也保留）
#   2. entry.id 不在 diff 的 added / removed / status_changed.id /
#      version_bumped.id 集合中（合并集 = unstable）
#   3. SQLite cache 命中（同款 _lookup_cached_result）
# ---------------------------------------------------------------------------


def load_mcp_registry_diff(diff_path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """读取 .mcp_registry_cache/diff.json；不存在或损坏返回空 dict。"""
    path = Path(diff_path) if diff_path else _MCP_REGISTRY_DIFF_PATH_DEFAULT
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        return data
    except (OSError, json.JSONDecodeError) as exc:
        logger.debug("Failed to read mcp_registry diff at %s: %s", path, exc)
        return {}


def _mcp_registry_unstable_ids(diff: dict[str, Any]) -> set[str]:
    """从 mcp_registry diff.json 提取「不稳定」entry id 集合。

    合并 added / removed / status_changed[].id / version_bumped[].id 四类。
    """
    if not diff:
        return set()
    unstable: set[str] = set()
    unstable.update(diff.get("added") or [])
    unstable.update(diff.get("removed") or [])
    for item in diff.get("status_changed") or []:
        if isinstance(item, dict) and item.get("id"):
            unstable.add(item["id"])
    for item in diff.get("version_bumped") or []:
        if isinstance(item, dict) and item.get("id"):
            unstable.add(item["id"])
    return unstable


def _is_mcp_registry_derived(entry: dict[str, Any]) -> bool:
    """判定 entry 是否承载 mcp_registry 派生数据。

    §14 修复 A 后：sync_mcp_registry 优先用 server.repository.url 写 source_url
    （GitHub URL），所以不能再单纯以 source_url 含 ``registry.modelcontextprotocol.io``
    判别。改用 ``entry.get("source") == "registry.modelcontextprotocol.io"``，
    sync_mcp_registry 始终把 source 字段写为该值——这才是稳定的派生标识。

    条件：source == "registry.modelcontextprotocol.io"。

    merge 后的 GitHub winner 即使携带 mcp_registry_status 字段也不算 mcp_registry
    派生——因为 registry diff 用 registry id 标记 unstable，winner.id 是 GitHub id，
    二者不对应；若也短路这类 winner 会在 status_changed 场景下误复用旧评分
    （codex review §8 finding #2）。
    """
    return (entry.get("source") or "") == "registry.modelcontextprotocol.io"


def _select_mcp_registry_short_circuit_entries(
    entries: list[dict[str, Any]],
    cache: Any,
    diff: dict[str, Any] | None,
    rubric_version: str | None = None,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """对 mcp_registry 派生条目预筛短路。

    返回 (短路命中的 results, 仍需评估的 entries)。

    短路条件（Section 8.1.1）：
    - entry 是 mcp_registry 派生
    - entry.id 不在 diff 的 unstable 集合中
    - cache 命中（rubric_version 匹配 + 未过期）

    注意：merge 后 winner.id 通常 ≠ registry id，diff 查不到 → 视为 unstable，
    走完整评估，属安全 fallback（不会把不该短路的条目漏评）。
    """
    if cache is None:
        return {}, list(entries)

    unstable = _mcp_registry_unstable_ids(diff or {})
    short_circuit: dict[str, dict[str, Any]] = {}
    remaining: list[dict[str, Any]] = []

    for entry in entries:
        eid = entry.get("id")
        if not eid:
            remaining.append(entry)
            continue
        if not _is_mcp_registry_derived(entry):
            remaining.append(entry)
            continue
        # 首次 sync 无 diff.json → 全部走完整评估（安全 default）
        if not diff:
            remaining.append(entry)
            continue
        if eid in unstable:
            remaining.append(entry)
            continue
        cached = _lookup_cached_result(cache, eid, rubric_version=rubric_version)
        if cached is None:
            remaining.append(entry)
            continue
        short_circuit[eid] = cached

    return short_circuit, remaining


# ---------------------------------------------------------------------------
# Section 8: windsurfrules 增量短路
# ---------------------------------------------------------------------------
#
# 设计意图：
#   sync_windsurfrules.py 没有写 diff.json（content_hash 由 cache 自动按
#   runner.evaluate 时算出，rubric_version 升级会自动失效旧 row）。因此
#   windsurfrules 的短路策略最简：只要 entry 是 windsurfrules 派生 + cache
#   命中（rubric 匹配 + 未过期），即可复用——底层 EvalCache 的 content_hash
#   语义保证 README 内容真变了时旧 row 自动 miss（runner 写入新 row 用新 hash）。
#
#   触发条件：
#     1. entry source/source_url 指向 awesome-windsurfrules（两个仓库之一）
#     2. cache 命中（同款 _lookup_cached_result）
# ---------------------------------------------------------------------------


def _is_windsurfrules_derived(entry: dict[str, Any]) -> bool:
    """判定 entry 是否承载 windsurfrules 派生数据。

    条件（任一满足）：
      - source == "awesome-windsurfrules"
      - source_url owner/repo 命中两个 windsurfrules 镜像之一
    """
    if (entry.get("source") or "") == "awesome-windsurfrules":
        return True
    su = (entry.get("source_url") or "").lower()
    if not su:
        return False
    for slug in _WINDSURFRULES_REPO_HOSTS:
        if f"github.com/{slug}/" in su or f"github.com/{slug}#" in su or su.endswith(
            f"github.com/{slug}"
        ):
            return True
    return False


def _select_windsurfrules_short_circuit_entries(
    entries: list[dict[str, Any]],
    cache: Any,
    rubric_version: str | None = None,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """对 windsurfrules 派生条目预筛短路。

    返回 (短路命中的 results, 仍需评估的 entries)。

    短路条件（Section 8.1.2）：
    - entry 是 windsurfrules 派生
    - cache 命中（rubric_version 匹配 + 未过期 + content_hash 由底层 cache 校验）

    与 skills.sh / mcp_registry 不同：不依赖 diff.json，因为 sync_windsurfrules
    没有维护 diff，且 EvalCache 的 content_hash 已能识别 README 变更——内容真变
    了 cache 中的旧 row 不会被 runner 复用（runner 用新 hash 写入新 row），
    本短路也只会复用同 hash 的历史 row。
    """
    # 保守策略（codex review §8 finding #1）：windsurfrules 没有 diff 文件，
    # _lookup_cached_result 会按 entry_id+rubric_version 命中"任意历史 content_hash"
    # 的旧 row，可能在上游 README 变更时复用 stale eval。规模又小（~108 条），
    # 全量重评的成本极低，因此本短路路径直接禁用，所有 windsurfrules 走完整评估。
    # 待 sync_windsurfrules 引入 content_hash 维护机制后再开启。
    if cache is None:
        return {}, list(entries)
    return {}, list(entries)


# ---------------------------------------------------------------------------
# Result → Entry mapping
# ---------------------------------------------------------------------------

def map_result_to_entry(entry: dict[str, Any], result: dict[str, Any] | None) -> None:
    """Map an EvalResult dict onto a catalog entry (in-place).

    Flattens metric scores to integers (no evidence/missing/suggestion).
    Maps enrichment fields (tags, summary, etc.) when present.
    Converts health signals to README-compatible format.
    Preserves existing evaluation if result is None (harness skipped entry).
    """
    if result is None:
        return

    # Build flattened evaluation sub-object
    evaluation: dict[str, Any] = {}
    for metric_name, metric_data in result.get("metrics", {}).items():
        # Store only the score integer, discard evidence/missing/suggestion
        if isinstance(metric_data, dict):
            evaluation[metric_name] = metric_data.get("score", 0)
        else:
            evaluation[metric_name] = metric_data

    # Copy governance fields
    evaluation["final_score"] = round(result.get("final_score", 0))
    evaluation["decision"] = result.get("decision", "review")
    evaluation["model_id"] = result.get("model_id")
    evaluation["rubric_version"] = result.get("rubric_version")
    evaluation["evaluated_at"] = result.get("evaluated_at")

    # content_quality: the LLM-only weighted subtotal (内容质量) — the α term of
    # the blend `final = α·llm + (1-α)·health`. Persisted so consumers display it
    # directly instead of re-deriving it from the metric dimensions with the
    # wrong (per-task) weights.
    llm_score = result.get("llm_score")
    if llm_score is not None:
        evaluation["content_quality"] = round(llm_score)

    entry["evaluation"] = evaluation

    # ── Map enrichment fields ──────────────────────────────────────────
    enrichment = result.get("enrichment")
    if enrichment and isinstance(enrichment, dict):
        if enrichment.get("tags"):
            entry["tags"] = enrichment["tags"]
        if enrichment.get("tech_stack"):
            entry["tech_stack"] = enrichment["tech_stack"]
        if enrichment.get("summary_zh"):
            entry["description_zh"] = enrichment["summary_zh"]
        if enrichment.get("search_terms"):
            entry["search_terms"] = enrichment["search_terms"]
        if enrichment.get("highlights"):
            entry["highlights"] = enrichment["highlights"]
        if enrichment.get("summary"):
            entry["description_original"] = entry.get("description", "")
            entry["description"] = enrichment["summary"]

    # ── Map MCP installability fields ─────────────────────────────────
    mcp_installability = result.get("mcp_installability")
    if entry.get("type") == "mcp":
        if not isinstance(mcp_installability, dict):
            mcp_installability = {
                "mcp_schema_valid": False,
                "mcp_install_state": "unknown",
                "mcp_validation_tags": ["insufficient_evidence"],
                "mcp_installability_reason": "本轮评估未返回有效的 MCP 可用性判断。",
            }
        if "mcp_schema_valid" in mcp_installability:
            entry["mcp_schema_valid"] = mcp_installability["mcp_schema_valid"]
        if mcp_installability.get("mcp_install_state"):
            entry["mcp_install_state"] = mcp_installability["mcp_install_state"]
        if mcp_installability.get("mcp_validation_tags") is not None:
            entry["mcp_validation_tags"] = mcp_installability[
                "mcp_validation_tags"
            ]
        if mcp_installability.get("mcp_installability_reason"):
            entry["mcp_installability_reason"] = mcp_installability[
                "mcp_installability_reason"
            ]

    # ── Map health signals (convert to README-compatible format) ──────
    raw_health = result.get("health")
    if raw_health and isinstance(raw_health, dict):
        freshness = raw_health.get("freshness", 0.0)
        popularity = raw_health.get("popularity", 0.0)
        source_trust = raw_health.get("source_trust", 0.0)
        # install_popularity：skills.sh 派生信号，默认权重 0 仅采集；缺失则视作 0
        install_popularity = raw_health.get("install_popularity", 0.0)

        # Compute aggregate score (mean of three signals, rounded)
        # install_popularity 不参与 health.score 聚合（保留旧含义不变）
        health_score = round((freshness + popularity + source_trust) / 3)

        # Derive freshness label
        if freshness > 70:
            freshness_label = "active"
        elif freshness > 30:
            freshness_label = "stale"
        else:
            freshness_label = "abandoned"

        # effective_score: the (1-α) blend term — the weighted + star-routing
        # redistributed health the final_score ACTUALLY uses, distinct from the
        # simple-mean `score` above. Recovered exactly from the blend identity
        # `final = α·llm + (1-α)·health` (α=0.85 across all task configs); the
        # raw, un-rounded final_score and llm_score carry full precision here.
        # Health-only entries (no llm_score) blend to `final = health`.
        final_score_raw = result.get("final_score", 0.0) or 0.0
        alpha = 0.85
        if llm_score is not None:
            effective_health = (final_score_raw - alpha * llm_score) / (1.0 - alpha)
        else:
            effective_health = final_score_raw

        # excluded_signals: weighted health signals dropped from the blend, so the
        # UI can explain why effective_score is below the simple-mean radar.
        excluded_signals: list[str] = []
        if result.get("star_weight", 1.0) == 0.0:
            excluded_signals.append("popularity")
        if entry.get("pushed_at") is None:
            excluded_signals.append("freshness")

        signals: dict[str, Any] = {
            "freshness": round(freshness),
            "popularity": round(popularity),
            "source_trust": round(source_trust),
            "install_popularity": round(install_popularity),
        }
        # manifest_completeness is a plugin-only signal (plugin.yaml weight 0.10);
        # surface it (0-100) so the UI can render it, e.g. a 4th health-radar axis.
        if entry.get("type") == "plugin":
            signals["manifest_completeness"] = round(
                raw_health.get("manifest_completeness", 0.0)
            )

        entry["health"] = {
            "score": health_score,
            "effective_score": round(effective_health),
            "excluded_signals": excluded_signals,
            "freshness_label": freshness_label,
            "last_commit": entry.get("pushed_at"),
            "signals": signals,
        }

    # Top-level promotion (consumed by sort + downstream scripts)
    entry["final_score"] = round(result.get("final_score", 0))
    entry["decision"] = result.get("decision", "review")


# ---------------------------------------------------------------------------
# Harness invocation
# ---------------------------------------------------------------------------

def _compute_rubric_version_for_task(task_name: str) -> str | None:
    """复算 task 当前 rubric_version（与 runner 内部计算保持一致）。

    runner 在 __init__ 时算 ``rubric_version = f"{major}.{sha8(system_prompt)}"``，
    这里复用同样的 prompt builder 和哈希方法，避免实例化完整 runner。
    失败返回 None（短路改走 fallback：仅按 entry_id 取最新 row）。
    """
    try:
        import hashlib

        from ai_resource_eval.metrics.prompt_builder import (
            build_system_prompt,
            metric_registry,
        )
        from ai_resource_eval.tasks.loader import load_task_config
    except ImportError:
        return None

    try:
        cfg = load_task_config(task_name)
    except (FileNotFoundError, ValueError):
        return None
    try:
        metrics = [metric_registry.get(mw.metric) for mw in cfg.metrics]
        prompt = build_system_prompt(
            metrics,
            enrichment=cfg.enrichment,
            mcp_installability=getattr(cfg, "mcp_installability", False),
        )
        sha8 = hashlib.sha256(prompt.encode()).hexdigest()[:8]
        return f"{cfg.rubric_major_version}.{sha8}"
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to compute rubric_version for %s: %s", task_name, exc)
        return None


def _format_elapsed(seconds: float) -> str:
    """Format an elapsed-second count as ``{m}m{s}s`` for progress lines."""
    total = max(0, int(seconds))
    return f"{total // 60}m{total % 60}s"


def _run_runner_with_telemetry(
    runner: "EvalRunner",
    eval_items: list[Any],
    resource_type: str,
    failure_log: "FailureLog | None" = None,
    checkpoint: "Checkpoint | None" = None,
    chunk_size: int = 50,
) -> list[Any]:
    """Run ``runner.run`` in chunks while recording telemetry.

    For each chunk:
      * Call ``runner.run(chunk)`` so the underlying concurrency is preserved.
      * Successes (entry ids returned by the runner) are recorded via
        ``failure_log.record_success`` and ``checkpoint.mark_completed``.
      * Failures (entry ids in the chunk input but absent from the runner's
        output — the runner's ``on_fail="skip"`` path silently drops these)
        are written to the ledger as ``error_kind="EvalRunnerSkip"``.
      * After each chunk, ``failure_log.save()`` and ``checkpoint.flush()``
        are invoked for durability and a flushed progress line is printed.

    A startup banner is printed once before the loop, and a final summary
    line is printed once after the loop. ``chunk_size`` defaults to 50 to
    align with :class:`scripts.enrichment_checkpoint.Checkpoint` flush
    granularity. When ``failure_log`` or ``checkpoint`` is ``None`` the
    corresponding bookkeeping is skipped (no-op).

    Returns the aggregated list of ``EvalResult`` objects across all chunks.
    """
    n = len(eval_items)
    start = time.monotonic()
    print(
        f"[type={resource_type}] starting: {n} to_evaluate elapsed=0s",
        flush=True,
    )

    aggregated: list[Any] = []
    succeeded = 0
    failed = 0
    done = 0

    if n == 0:
        elapsed = time.monotonic() - start
        print(
            f"[type={resource_type}] done: succeeded={succeeded} "
            f"failed={failed} wall_clock={_format_elapsed(elapsed)}",
            flush=True,
        )
        return aggregated

    chunk = max(1, int(chunk_size))
    for offset in range(0, n, chunk):
        batch = eval_items[offset : offset + chunk]

        # Capture the input ids for diff against runner output.
        input_ids: list[str] = []
        for item in batch:
            iid = getattr(item, "id", None)
            if iid is None and isinstance(item, dict):
                iid = item.get("id")
            input_ids.append(str(iid) if iid is not None else "")

        chunk_failed_already_recorded = False
        try:
            results = runner.run(batch)
        except Exception as exc:  # noqa: BLE001 - bubble per-batch failures into ledger
            logger.warning(
                "[type=%s] runner.run raised on chunk offset=%d size=%d: %s",
                resource_type,
                offset,
                len(batch),
                exc,
            )
            results = []
            chunk_failed_already_recorded = True
            if failure_log is not None:
                error_message = f"{type(exc).__name__}: {exc}"
                for iid in input_ids:
                    if iid:
                        failure_log.record_failure(
                            iid,
                            type_=resource_type,
                            error_kind="EvalRunnerException",
                            error_message=error_message,
                        )

        # Compute success / failure id sets for ledger + checkpoint updates.
        returned_ids: set[str] = set()
        for r in results:
            rd = r.model_dump(mode="json") if hasattr(r, "model_dump") else r
            rid = rd.get("entry_id") if isinstance(rd, dict) else None
            if rid:
                returned_ids.add(str(rid))
            aggregated.append(r)

        for iid in input_ids:
            if not iid:
                continue
            if iid in returned_ids:
                if failure_log is not None:
                    failure_log.record_success(iid)
                if checkpoint is not None:
                    checkpoint.mark_completed(iid)
                succeeded += 1
            else:
                # Skip ledger write when the whole-batch exception handler
                # already recorded this id as EvalRunnerException — otherwise
                # one batch failure would advance attempt_count by 2.
                if failure_log is not None and not chunk_failed_already_recorded:
                    failure_log.record_failure(
                        iid,
                        type_=resource_type,
                        error_kind="EvalRunnerSkip",
                        error_message="runner returned no result for entry",
                    )
                failed += 1
            done += 1

        # Persist failure ledger + checkpoint after each chunk for durability.
        if failure_log is not None:
            try:
                failure_log.save()
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[type=%s] failure_log.save() failed: %s", resource_type, exc
                )
        if checkpoint is not None:
            try:
                checkpoint.flush()
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[type=%s] checkpoint.flush() failed: %s", resource_type, exc
                )

        elapsed = time.monotonic() - start
        pct = int(done * 100 / n) if n else 100
        print(
            f"[type={resource_type}] progress: {done}/{n} ({pct}%) "
            f"succeeded={succeeded} failed={failed} "
            f"elapsed={_format_elapsed(elapsed)}",
            flush=True,
        )

    elapsed = time.monotonic() - start
    print(
        f"[type={resource_type}] done: succeeded={succeeded} failed={failed} "
        f"wall_clock={_format_elapsed(elapsed)}",
        flush=True,
    )
    return aggregated


def run_eval(
    entries: list[dict[str, Any]],
    cache_dir: str = ".eval_cache",
    incremental: bool = True,
    concurrency: int = 4,
    skills_sh_diff_path: str | os.PathLike[str] | None = None,
    mcp_registry_diff_path: str | os.PathLike[str] | None = None,
    failure_log: "FailureLog | None" = None,
    checkpoints_by_type: "dict[str, Checkpoint] | None" = None,
) -> dict[str, dict[str, Any]]:
    """Run the eval harness and return {entry_id: result_dict}.

    Groups entries by type and runs each group with its task config.
    Returns only entries that were successfully evaluated.

    增量短路（incremental=True 时按顺序应用三种 short-circuit，互不重叠）：

    - Section 6 — skills.sh：``.skills_sh_cache/diff.json`` 存在时，对携带
      skills_sh_url 且 raw id 不在 unstable 集合的 skill 条目复用 cache。
    - Section 8 — mcp_registry：``.mcp_registry_cache/diff.json`` 存在时，对
      registry 派生的 mcp 条目（id 不在 added/removed/status_changed/version_bumped
      集合）复用 cache。
    - Section 8 — windsurfrules：无 diff，对 windsurfrules 派生的 rule 条目
      只要 cache 命中（rubric_version 匹配 + content_hash 一致）即复用。

    任一短路都会按当前 task 的 rubric_version 重建标准 cache_key 校验失效，
    rubric 升级后旧 row 自然 miss，runner 会重评。
    """
    try:
        from ai_resource_eval.api.types import EvalItem
        from ai_resource_eval.cache import EvalCache
        from ai_resource_eval.runner import EvalRunner
        from ai_resource_eval.tasks.loader import load_task_config
    except ImportError:
        logger.warning(
            "ai-resource-eval package not found. "
            "Ensure ai-resource-eval is installed: "
            "pip install -e ai-resource-eval"
        )
        return {}

    # 先按 type 分组（短路 / runner 都需要按 type 选 task config）
    groups: dict[str, list[dict]] = {}
    for entry in entries:
        t = entry.get("type", "skill")
        groups.setdefault(t, []).append(entry)

    # ── Section 6/8 短路：按 type 计算 rubric_version 后依次应用三种短路 ──
    short_circuit_results: dict[str, dict[str, Any]] = {}
    remaining_by_type: dict[str, list[dict]] = {t: list(g) for t, g in groups.items()}

    if incremental:
        skills_sh_diff = load_skills_sh_diff(skills_sh_diff_path)
        mcp_registry_diff = load_mcp_registry_diff(mcp_registry_diff_path)

        # 任一 sidecar 存在 / windsurfrules 短路（无 diff 也跑）都需要打开 cache
        cache_path = Path(cache_dir)
        cache_path.mkdir(parents=True, exist_ok=True)
        try:
            pre_cache = EvalCache(db_path=cache_path / "eval_cache.db")
        except Exception as exc:  # noqa: BLE001
            logger.debug("Failed to open cache for short-circuit: %s", exc)
            pre_cache = None

        if pre_cache is not None:
            skills_sh_hits = 0
            mcp_registry_hits = 0
            windsurfrules_hits = 0

            for resource_type, group in groups.items():
                task_name = resolve_task_name(resource_type)
                rubric_version = _compute_rubric_version_for_task(task_name)
                current = list(group)

                # 1. skills.sh 短路（依赖 diff.json）
                if skills_sh_diff:
                    short, current = _select_short_circuit_entries(
                        current, pre_cache, skills_sh_diff, rubric_version=rubric_version
                    )
                    if short:
                        short_circuit_results.update(short)
                        skills_sh_hits += len(short)

                # 2. mcp_registry 短路（依赖 diff.json，仅 mcp 类型典型适用，
                #    但通用代码不强行限制 type；非 registry 派生的 entry 在
                #    _is_mcp_registry_derived 内会被过滤掉）
                if mcp_registry_diff:
                    short, current = _select_mcp_registry_short_circuit_entries(
                        current, pre_cache, mcp_registry_diff, rubric_version=rubric_version
                    )
                    if short:
                        short_circuit_results.update(short)
                        mcp_registry_hits += len(short)

                # 3. windsurfrules 短路（无 diff，仅 cache 命中即复用）
                short, current = _select_windsurfrules_short_circuit_entries(
                    current, pre_cache, rubric_version=rubric_version
                )
                if short:
                    short_circuit_results.update(short)
                    windsurfrules_hits += len(short)

                remaining_by_type[resource_type] = current

            if short_circuit_results:
                total_remaining = sum(len(v) for v in remaining_by_type.values())
                logger.info(
                    "增量短路：skills.sh=%d / mcp_registry=%d / windsurfrules=%d "
                    "（剩余待评估 %d 条）",
                    skills_sh_hits,
                    mcp_registry_hits,
                    windsurfrules_hits,
                    total_remaining,
                )

    # ── 1.11: failure-ledger 过滤（quarantine + backoff 未到期跳过） ──
    if failure_log is not None:
        for resource_type in list(remaining_by_type.keys()):
            kept: list[dict] = []
            deferred = 0
            quarantined = 0
            for entry in remaining_by_type[resource_type]:
                entry_id = entry.get("id")
                if entry_id is None:
                    kept.append(entry)
                    continue
                if failure_log.is_quarantined(entry_id):
                    quarantined += 1
                    continue
                if not failure_log.should_retry_now(entry_id):
                    deferred += 1
                    continue
                kept.append(entry)
            remaining_by_type[resource_type] = kept
            if deferred or quarantined:
                logger.info(
                    "[type=%s] failure-ledger filter: kept=%d deferred=%d quarantined=%d",
                    resource_type,
                    len(kept),
                    deferred,
                    quarantined,
                )

    # 仍需评估的条目（按 type 已分组）
    remaining_total = sum(len(v) for v in remaining_by_type.values())

    # 全部短路命中：直接返回，节省 judge 初始化
    if remaining_total == 0:
        return short_circuit_results

    # Resolve judge from environment
    judge = _build_judge()
    if judge is None:
        logger.warning("No LLM API key configured, skipping evaluation")
        # 即使无 key，仍可返回短路命中的 cache 结果
        return short_circuit_results

    all_results: dict[str, dict[str, Any]] = dict(short_circuit_results)

    for resource_type, group in remaining_by_type.items():
        if not group:
            continue
        task_name = resolve_task_name(resource_type)
        try:
            task_config = load_task_config(task_name)
        except (FileNotFoundError, ValueError) as exc:
            logger.warning("Failed to load config for %s: %s, using skill fallback", resource_type, exc)
            task_config = load_task_config("skill")

        # Convert dicts to EvalItem
        eval_items = []
        for e in group:
            try:
                eval_items.append(EvalItem(**e))
            except Exception as exc:
                logger.debug("Skipping entry %s: %s", e.get("id"), exc)

        runner = EvalRunner(
            task_config=task_config,
            judge=judge,
            cache_dir=cache_dir,
            concurrency=concurrency,
            incremental=incremental,
            interactive=False,
            on_fail="skip",
        )

        checkpoint = None
        if checkpoints_by_type is not None:
            checkpoint = checkpoints_by_type.get(resource_type)

        results = _run_runner_with_telemetry(
            runner,
            eval_items,
            resource_type=resource_type,
            failure_log=failure_log,
            checkpoint=checkpoint,
            chunk_size=50,
        )
        for r in results:
            rd = r.model_dump(mode="json") if hasattr(r, "model_dump") else r
            all_results[rd["entry_id"]] = rd

    return all_results


def _build_judge():
    """Build a judge instance from environment variables."""
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("JUDGE_API_KEY")
    if not api_key:
        return None

    base_url = os.environ.get("LLM_BASE_URL") or os.environ.get("JUDGE_BASE_URL", "")
    model = os.environ.get("LLM_MODEL") or os.environ.get("JUDGE_MODEL", "")

    # Try DeepSeek first (cheapest)
    if not base_url or "deepseek" in base_url:
        from ai_resource_eval.judges.deepseek import DeepSeekJudge
        return DeepSeekJudge(api_key=api_key, model=model or "deepseek-chat")

    # Generic OpenAI-compatible
    from ai_resource_eval.judges.openai_compat import OpenAICompatJudge
    return OpenAICompatJudge(base_url=base_url, api_key=api_key, model=model)


# ---------------------------------------------------------------------------
# Pipeline entry point (called from enrichment_orchestrator)
# ---------------------------------------------------------------------------

def eval_and_map(
    entries: list[dict[str, Any]],
    cache_dir: str = ".eval_cache",
    incremental: bool = True,
    concurrency: int = 4,
    skills_sh_diff_path: str | os.PathLike[str] | None = None,
    mcp_registry_diff_path: str | os.PathLike[str] | None = None,
    failure_log: "FailureLog | None" = None,
    checkpoints_by_type: "dict[str, Checkpoint] | None" = None,
) -> None:
    """Run eval harness on entries and map results back in-place.

    This is the main entry point called from the pipeline.

    skills_sh_diff_path 可选：默认读取项目根 ``.skills_sh_cache/diff.json``。
    mcp_registry_diff_path 可选：默认读取 ``.mcp_registry_cache/diff.json``。
    windsurfrules 短路无 diff 依赖，自动启用（仅靠 cache 命中）。

    failure_log / checkpoints_by_type 可选：当传入时启用 1.10/1.11/1.12 行为
    （EvalRunner 包装层 + should_retry_now 过滤 + 检查点记录）。两者均默认
    None，保持与既有调用点的向后兼容。
    """
    results = run_eval(
        entries,
        cache_dir=cache_dir,
        incremental=incremental,
        concurrency=concurrency,
        skills_sh_diff_path=skills_sh_diff_path,
        mcp_registry_diff_path=mcp_registry_diff_path,
        failure_log=failure_log,
        checkpoints_by_type=checkpoints_by_type,
    )

    mapped = 0
    for entry in entries:
        result = results.get(entry.get("id"))
        map_result_to_entry(entry, result)
        if result:
            mapped += 1

    logger.info("Eval bridge: mapped %d / %d entries", mapped, len(entries))


# ---------------------------------------------------------------------------
# Security scan pipeline stage (add-security-risk-eval)
# ---------------------------------------------------------------------------


def _build_mcp_security_eval_item(entry: dict[str, Any], EvalItemCls):
    """Construct an EvalItem for an MCP entry whose evaluation content is the
    serialized install.config (no remote fetch).

    Per spec, the runner needs to evaluate MCP entries on their install.config
    JSON rather than a README. We achieve this by:

      * dropping ``source_url`` so the runner's fetcher doesn't try to pull a
        README from GitHub,
      * stuffing the serialized install.config into ``description`` so the
        ``content_fallback: description`` path returns that text,
      * keeping ``install`` so :func:`build_security_user_prompt` can also
        surface it inline in the user prompt.

    The content_hash that downstream code reads from the EvalResult is the
    SHA-256 of this synthesized description (taken automatically by
    ``EvalCache.content_hash`` via the fetcher's description path).
    """
    try:
        from ai_resource_eval.metrics.security_scan_prompt import (
            build_security_synth_content_for_mcp,
        )
    except ImportError:  # pragma: no cover - only fails if package missing
        return None

    install = entry.get("install") if isinstance(entry.get("install"), dict) else None
    synth = build_security_synth_content_for_mcp(install)

    raw = dict(entry)
    raw["source_url"] = None
    raw["description"] = synth
    raw["install"] = install
    try:
        return EvalItemCls(**raw)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to build MCP security EvalItem for %s: %s", entry.get("id"), exc)
        return None


def _map_security_to_entry(entry: dict[str, Any], result: dict[str, Any] | None) -> None:
    """Map a security-scan EvalResult onto a catalog entry.

    Writes the entry's top-level ``security`` block with the 6 LLM fields plus
    audit metadata (``scan_model`` / ``rubric_version`` / ``content_hash`` /
    ``scanned_at``). On failure the field is left missing — per spec, absent
    ``security`` means "not yet evaluated this cycle".
    """
    if result is None:
        return

    security = result.get("security")
    if not isinstance(security, dict):
        return

    scanned_at = result.get("evaluated_at")
    if scanned_at is None:
        from datetime import datetime, timezone

        scanned_at = datetime.now(timezone.utc).isoformat()

    entry["security"] = {
        "risk_level": security.get("risk_level"),
        "verdict": security.get("verdict"),
        "red_flags": security.get("red_flags") or [],
        "permissions": security.get("permissions")
        or {"files": [], "network": [], "commands": []},
        "summary": security.get("summary") or "",
        "recommendations": security.get("recommendations") or [],
        "scan_model": result.get("model_id"),
        "rubric_version": result.get("rubric_version"),
        "content_hash": result.get("content_hash"),
        "scanned_at": scanned_at,
    }


def _run_security_scan(
    entries: list[dict[str, Any]],
    cache_dir: str = ".eval_cache",
    incremental: bool = True,
    concurrency: int = 4,
) -> dict[str, dict[str, Any]]:
    """Run the security_scan task across entries and return {entry_id: result}.

    Routing:
      * MCP entries are pre-processed by :func:`_build_mcp_security_eval_item`
        so the runner evaluates their install.config JSON (no remote fetch).
      * skill / rule / prompt / plugin entries are passed through unchanged;
        the runner's existing fetcher pulls README/SKILL.md and falls back to
        description if needed (per spec D3, fetcher behaviour is NOT extended
        for security).

    The same ``security_scan`` task config is used for every type — only the
    user prompt content differs. Cache namespace ``"security"`` keeps these
    rows isolated from the quality / enrichment cache.
    """
    try:
        from ai_resource_eval.api.types import EvalItem
        from ai_resource_eval.runner import EvalRunner
        from ai_resource_eval.tasks.loader import load_task_config
    except ImportError:
        logger.warning(
            "ai-resource-eval package not found; skipping security scan stage"
        )
        return {}

    try:
        task_config = load_task_config("security_scan")
    except (FileNotFoundError, ValueError) as exc:
        logger.warning("Failed to load security_scan task config: %s", exc)
        return {}

    judge = _build_judge()
    if judge is None:
        logger.warning("No LLM API key configured; skipping security scan stage")
        return {}

    eval_items: list[Any] = []
    id_for_item: list[str] = []
    for e in entries:
        eid = e.get("id")
        if not eid:
            continue
        if e.get("type") == "mcp":
            item = _build_mcp_security_eval_item(e, EvalItem)
        else:
            try:
                item = EvalItem(**e)
            except Exception as exc:  # noqa: BLE001
                logger.debug(
                    "Skipping entry %s for security scan (EvalItem failed): %s",
                    eid,
                    exc,
                )
                item = None
        if item is None:
            continue
        eval_items.append(item)
        id_for_item.append(eid)

    if not eval_items:
        return {}

    runner = EvalRunner(
        task_config=task_config,
        judge=judge,
        cache_dir=cache_dir,
        concurrency=concurrency,
        incremental=incremental,
        interactive=False,
        on_fail="skip",
    )

    try:
        results = runner.run(eval_items)
    except Exception as exc:  # noqa: BLE001 - never bubble up from security stage
        logger.warning("security_scan runner raised: %s", exc)
        return {}

    out: dict[str, dict[str, Any]] = {}
    for r in results:
        rd = r.model_dump(mode="json") if hasattr(r, "model_dump") else r
        rid = rd.get("entry_id") if isinstance(rd, dict) else None
        if rid:
            out[rid] = rd
    return out


def security_scan_and_map(
    entries: list[dict[str, Any]],
    cache_dir: str = ".eval_cache",
    incremental: bool = True,
    concurrency: int = 4,
) -> None:
    """Run security_scan across entries and map results in-place to entry.security.

    Failure-safe: any exception from the security stage is logged but does NOT
    propagate to the main pipeline. Entries whose evaluation fails simply lack
    the ``security`` block in the output (per spec D7 — missing means
    "未评估"; the next cycle will retry).
    """
    try:
        results = _run_security_scan(
            entries,
            cache_dir=cache_dir,
            incremental=incremental,
            concurrency=concurrency,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Security scan stage failed: %s", exc)
        return

    mapped = 0
    for entry in entries:
        result = results.get(entry.get("id"))
        _map_security_to_entry(entry, result)
        if result is not None and entry.get("security") is not None:
            mapped += 1

    logger.info("Security scan: mapped %d / %d entries", mapped, len(entries))
