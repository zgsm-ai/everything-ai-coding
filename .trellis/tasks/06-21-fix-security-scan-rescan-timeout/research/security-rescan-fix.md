# Research: security scan 复发性 6h 超时修复落点

- **Query**: 钉死 A（认 entry 已有 security 字段跳过）+ B（拆 aggregate 让 commit 不被 security 连累）的最小改动落点
- **Scope**: internal
- **Date**: 2026-06-21

## TL;DR（先看这个）

- **关键好消息**：`security` 块**已经记录了 `content_hash` 和 `rubric_version`**（实测样本 `rubric_version: "2.bd55efd5"`, `content_hash: "15f3..."`）。所以 A 方案能做"仅当 content_hash 与当前一致才跳过"的**安全**短路，不必在"保守跳过"和"牺牲新鲜度"之间二选一。
- **A 落点**：`scripts/eval_bridge.py:_run_security_scan`（:1273）在构建 `EvalItem` 之前，加一道 entry-level 预筛——entry 已带合法 `security` 块且 `security["rubric_version"] == 当前 security rubric_version` → 从 `entries` 里剔除、不进 runner。这一步必须在 bridge 层做，因为**runner 的 `_fetch_content` 在 cache 检查之前**（runner.py:314 vs 496），每个 entry 不管 cache 命中都会先打一次 GitHub raw fetch——这就是 10,304 个 429 的来源。只跳 LLM 不跳 fetch 救不了 429。
- **A 的 content_hash 取舍**：security 块**已存** content_hash，但它是 README/SKILL.md fetch 内容的 SHA256，bridge 预筛阶段**没有重新 fetch 不知道当前 content_hash**。两种现实选项：(a) **rubric-only 短路**（认 `rubric_version` 匹配就跳过，不校 content_hash）——简单、彻底避免 fetch，代价是 content 变了这一轮不重扫（下游有 freshness 兜底见 §3）；(b) 想校 content_hash 必须先 fetch，等于没省下 429。**推荐 (a)**，理由见 §1.4 + §4。
- **B 落点**：`.github/workflows/sync.yml` aggregate job 当前顺序是 `... → governance → Run security scan(540min, continue-on-error) → README → commit → bundle-trigger(needs: aggregate, if: success)`。security step 虽是 `continue-on-error: true`，但它**占满 6h job timeout 后整个 job 被 GitHub cancel**（`continue-on-error` 只挡 step 失败、挡不住 job 级 timeout cancel），导致后面的 commit step 根本没机会跑。**推荐把 commit 挪到 security 之前**（最小侵入），或把 security 拆成 `needs: aggregate` 的独立非阻塞 job。

---

## 1. A 方案：security scan 怎么"认 entry 已有 security 字段"跳过

### 1.1 当前每个 entry 的判定/调用流程

入口链：`enrichment_orchestrator.enrich_entries` → `eval_bridge.security_scan_and_map`（:1365）→ `eval_bridge._run_security_scan`（:1273）→ `ai_resource_eval.runner.EvalRunner.run` → 每 entry `_eval_one`（runner.py:298）→ `_eval_one_security`（runner.py:474）。

`_run_security_scan`（eval_bridge.py:1273-1362）当前对每个 entry：
1. type=mcp → `_build_mcp_security_eval_item`（合成 install.config，不远端 fetch）；其他 type → `EvalItem(**e)`（:1320-1334）。
2. 全部塞进 `eval_items`，**无条件**交给 `runner.run`（:1340-1351）。**bridge 层此刻没有任何"已有 security 字段就跳过"的短路**——它只把 entry 转成 EvalItem 就丢给 runner。

runner 内 `_eval_one`（runner.py:298）对每个 entry：
1. **`fetch_result = self._fetch_content(entry)`（:314）** ← **先 fetch**（拉 SKILL.md/README.md raw）。**这是 429 来源**：2820 条恢复 entry 的 content_hash 不在本周冷 SQLite cache，每条都触发一次真实 GitHub fetch。
2. `content, content_hash = fetch_result`（:318）。
3. security 分支 → `_eval_one_security(entry, content, content_hash)`（:328-329）。

`_eval_one_security`（runner.py:474-546）：
1. `if self._incremental:` → `_check_cache(entry.id, content_hash)`（:495-498）——**SQLite cache 命中才跳 LLM**。命中条件 = `make_key("__full__", content_hash, rubric_version, namespace="security")` 在 SQLite 里存在且未过期（runner.py:842-848）。
2. cache miss → `build_security_user_prompt` + `judge.judge`（:500-508）调 LLM。
3. 失败兜底：LLM 异常 / 返回 None / `SecurityScanResult` 校验失败（verdict↔risk_level mismatch）→ 返回 None，**不写 cache、不写 security 字段**，下轮重试（:509-527）。
4. 成功 → 组装 `EvalResult`（`content_hash=content_hash`, `rubric_version=self._rubric_version`，:529-544）→ `_cache_result` 写 SQLite → 返回。

**决定"调 LLM 还是复用"的那一步 = `_eval_one_security` 的 `_check_cache`（runner.py:496）**，它**只查 SQLite cache，完全不看 entry 上已有的 `security` 字段**。而即便 cache 命中，**fetch 在它之前已经发生了**（runner.py:314），429 已经打出去了。

> 结论：A 方案必须在 **eval_bridge 层、构建 EvalItem 之前**剔除已带合法 security 的 entry（让它根本不进 runner，从而既不 fetch 也不调 LLM）。在 runner 内补救来不及——fetch 早于 cache 检查。

### 1.2 security 块 schema（真实样本）

从 `catalog/index.json` 抓的真实样本（已脱长）：

```json
{
  "id": "007-agskill",
  "type": "skill",
  "source": "antigravity-skills",
  "security": {
    "risk_level": "medium",
    "verdict": "caution",
    "red_flags": ["..."],
    "permissions": {"files": ["..."], "network": [], "commands": ["..."]},
    "summary": "...",
    "recommendations": ["..."],
    "scan_model": "__cached__",
    "rubric_version": "2.bd55efd5",
    "content_hash": "15f3da75d7198d1e2ba2523389b2014674e5b2a0aa774b8805ceb4d4e8cc3632",
    "scanned_at": "2026-05-20T10:32:15.856597Z"
  }
}
```

字段（写入逻辑见 `eval_bridge._map_security_to_entry`，:1237-1270）：
- 6 个 LLM 字段：`risk_level` / `verdict` / `red_flags` / `permissions` / `summary` / `recommendations`
- 4 个审计字段：`scan_model`（= `result.model_id`，cache 命中时为 `"__cached__"`）/ **`rubric_version`**（如 `"2.bd55efd5"`，= `major.sha8(system_prompt)`）/ **`content_hash`**（README/SKILL.md fetch 内容的 SHA256）/ `scanned_at`

**关键确认**：
- ✅ **security 块记录了 `content_hash`**（PRD §Technical Notes 的疑问"research 确认是否含 content_hash"——**含**）。
- ✅ **security 块记录了 `rubric_version`**（完整版 `major.sha8`，不只是 major version）。
- 全库 17262/17278 entry 已带 security 字段（实测）。

`security` 字段能跨 rebuild 保留，因为 `catalog_lifecycle.PRESERVED_TOP_LEVEL_FIELDS=("security",)`（PRD 已注，A 方案与之天然契合——保留下来的字段正好够判跳过）。

### 1.3 当前 security rubric_version（匹配确认）

- YAML：`ai-resource-eval/ai_resource_eval/tasks/security_scan.yaml:30` → `rubric_major_version: 2`（**注意：CLAUDE.md / PRD 写"当前 1"是过期描述，实际 YAML 已是 2**）。
- 完整 `rubric_version = f"{major}.{sha8(system_prompt)}"`（runner.py:147-148），当前实测为 `"2.bd55efd5"`，与库内 entry 的 `security.rubric_version` 一致。
- bridge 已有现成 helper 复算它：`_compute_rubric_version_for_task("security_scan")`?  → **不能直接用**：`_compute_rubric_version_for_task`（eval_bridge.py:728-760）按普通 task 走 `build_system_prompt`，而 security 用的是 `SECURITY_SCAN_SYSTEM_PROMPT`（runner.py:131）。最稳的复算方式见 §1.5 伪代码（直接 import `SECURITY_SCAN_SYSTEM_PROMPT` + `load_task_config("security_scan").rubric_major_version` 拼 `major.sha8`），与 runner.py:146-148 完全同款。

### 1.4 内容变更安全（核心取舍）

问题：A 短路若"认字段就跳过"，content 变了会不会漏扫？

- security 块**存了** content_hash，理论上可"仅当 content_hash 与当前一致才跳过"。
- **但 bridge 预筛阶段拿不到当前 content_hash**——当前 content_hash 是 `_fetch_content` 拉 README/SKILL.md 后算的（runner.py:318 / fetch path :754,773,790 用 `EvalCache.content_hash(content)`）。**要算它就得 fetch，fetch 就是 429 源**。所以"校 content_hash"和"避免 fetch"互斥。
- 两条路：
  - **(a) rubric-only 短路（推荐）**：entry 有合法 security 块 + `security.rubric_version == 当前 rubric_version` → 跳过（不 fetch、不校 content_hash）。**代价**：若上游 README 变了，这一轮 security 不重扫。**为什么可接受**：
    1. security 不影响 accept/reject 决策（`security_scan.yaml` 注释明确 threshold 在 security 路径未用；governor 不读 security 改 decision）——过时的 security 块不会错杀/错收 entry。
    2. 内容真变的 entry，其**质量评分侧**（6 维 enrich，独立 cache）会因 content_hash 变而重扫，下游有自然的"内容变更被识别"信号；security 可在后续周期靠"主动失效"补扫（见下条建议）。
    3. 真要强制重扫某批，bump `rubric_major_version`（2→3）即可让全库 security 失效重扫——这是设计内的总闸。
  - **(b) 校 content_hash**：必须先 fetch → 无法解决 429 → 否决。
- **额外建议（可选，降低 (a) 的新鲜度损失）**：若想让"内容变了的 entry"也重扫又不全量 fetch，可复用质量评分侧已算出的新鲜度信号——但这超出本任务最小改动范围，列为 follow-up。MVP 取 (a)。

### 1.5 最小改动（落点 + 伪代码）

**落点：`scripts/eval_bridge.py:_run_security_scan`（:1273），在 `for e in entries:` 构建 EvalItem 的循环之前插入预筛。**

```python
# eval_bridge.py，_run_security_scan 内，约 :1314（eval_items=[] 之前）

# A 方案短路：已带合法 security 块且 rubric_version 匹配 → 不进 runner
# （既省 GitHub fetch=429 源，也省 LLM 调用）。
current_rubric = _compute_security_rubric_version()  # 新 helper，见下
to_scan: list[dict] = []
skipped = 0
for e in entries:
    sec = e.get("security")
    if (
        current_rubric is not None
        and isinstance(sec, dict)
        and sec.get("rubric_version") == current_rubric
        and _is_security_block_complete(sec)  # 6 字段齐 + verdict/risk_level 合法
    ):
        skipped += 1
        continue
    to_scan.append(e)
logger.info("security_scan: skipping %d entries with valid security block", skipped)
entries = to_scan
if not entries:
    return {}
# ……下面原有 for e in entries 构建 EvalItem 不变……
```

新 helper（复算 security rubric_version，与 runner.py:146-148 同款）：

```python
def _compute_security_rubric_version() -> str | None:
    try:
        import hashlib
        from ai_resource_eval.metrics.security_scan_prompt import SECURITY_SCAN_SYSTEM_PROMPT
        from ai_resource_eval.tasks.loader import load_task_config
        cfg = load_task_config("security_scan")
        sha8 = hashlib.sha256(SECURITY_SCAN_SYSTEM_PROMPT.encode()).hexdigest()[:8]
        return f"{cfg.rubric_major_version}.{sha8}"
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to compute security rubric_version: %s", exc)
        return None  # 复算失败 → 不短路，全量走老路（保守）
```

`_is_security_block_complete` 校验 6 字段存在 + `verdict`∈{safe,caution,reject} + `risk_level`∈{clean,low,medium,high,extreme}（避免半截/脏块被误判已扫）。

**warm SQLite cache（PRD AC 可选项）**：跳过命中的 entry，可顺手用 `security` 块里的 content_hash + 6 字段，按 `make_key(..., namespace="security")` 回写一条 SQLite row，使两条短路（cache + entry 字段）一致。但**注意**：bridge 没有当前 content_hash（同 §1.4），只能拿 `security["content_hash"]`（历史值）回写。若上游内容已变，回写的 cache 也是旧 hash 的——和"认字段跳过"语义一致（都不重扫）。所以 warm cache 是"锦上添花、保持两短路一致"，**不是正确性必需**；可作为可选单测项实现，也可不做（A 的 entry-field 短路已足够拦住批量）。

---

## 2. B 方案：拆 aggregate 让 commit 不被 security 连累

### 2.1 aggregate job 当前 step 顺序（sync.yml）

aggregate job（`needs: [sync-data, enrich]`, `if: always()`, **`timeout-minutes: 600`**，:492-505），相关 step 先后：

1. Download catalog data layer（:526）
2. Download enrichment artifacts（:534）
3. Stage partial artifacts（:545）
4. Merge failure ledgers（:573）
5. **Aggregate enrichment into catalog**（:700）← 真正的 merge/stitch
6. **Apply reject governance**（:708）← catalog/index.json 此刻已是"最终数据"
7. Restore security eval cache（:751）
8. **Run security scan**（:763, **`timeout-minutes: 540`**, **`continue-on-error: true`**）← **元凶**
9. Save security eval cache（:872, `if: always()`）
10. Generate catalog sub-directory READMEs（:880）
11. Update bilingual README（:890）
12. Audit popular coverage（:895, continue-on-error）
13. **Commit and push if changed**（:906, `id: commit`，输出 `catalog_changed` / `committed`）

`trigger-catalog-bundle-release` job（:942）：`needs: aggregate`，`if: needs.aggregate.result == 'success' && needs.aggregate.outputs.catalog_changed == 'true'`。

### 2.2 为什么 commit / bundle 当前被跳过（实测故障链）

- security step 是 `continue-on-error: true`，但它跑满 step timeout 540min + 前面 step 累计后，**整个 aggregate job 撞 600min job timeout → GitHub job-level cancel**。`continue-on-error` 只让"step 失败"不 fail job，**挡不住 job 级 timeout cancel**（`##[error]The operation was canceled`）。
- job 被 cancel → step 10-13（README / **commit**）根本没执行 → catalog 没提交。
- commit step 没跑 → `steps.commit.outputs.catalog_changed` 为空 → `trigger-catalog-bundle-release` 的 `if` 不满足 + `needs.aggregate.result != 'success'`（是 cancelled）→ bundle 也被跳过。
- 复发：security cache save step（:872）也没跑（job 已 cancel）→ 下轮 2820 条仍冷 → 又超时。

### 2.3 拆分方案（两选一）

#### 方案 B1：把 commit 挪到 security 之前（最小侵入，推荐）

把 README 生成 + commit + bundle 触发**移到 security scan step 之前**，security 变成 aggregate 的**最后一个 step**（且仍 continue-on-error）。这样：
- catalog（不含本轮新 security，但含上轮保留的 security 字段——`PRESERVED_TOP_LEVEL_FIELDS`）+ README 先 commit + push + 触发 bundle。
- 再跑 security scan（即便它超时被 cancel，commit 已经发生了）。
- security 写回的 catalog 增量在**下一轮**随 cron 一起提交（因为它写 catalog/index.json 后没有第二个 commit step——需补一个 security 后的 commit，见下"风险"）。

**改动量**：sync.yml 内 step 重排（把 :880-940 的 README/commit/bundle 区块移到 :751 之前）。约 60 行移动，**无新 job、无 artifact 传递**。

**风险/注意**：
- 重排后 security 的写回**不会被提交**（commit 在它之前）。要么接受"security 增量延后一轮提交"（A 方案已让 security 几乎全命中跳过、增量极小，可接受），要么在 security step 之后再加一个轻量 commit step（只 `git add catalog/ && commit && push`）——但这第二个 commit 仍可能因 security 超时而不执行，回到老问题。**最干净的组合 = B1（commit 前置）+ A（security 几乎不再产生新写回）**：A 落地后 security 每轮只扫极少数真·新增 entry，几分钟跑完，"延后一轮"实际无感。
- `catalog_changed` 判定基于 commit 时的 staged diff，需确认前置后仍能正确产出 output 给 bundle job——重排不改 commit step 内部逻辑，OK。

#### 方案 B2：security 独立成 `needs: aggregate` 的非阻塞 job

新增 job `security-scan`：`needs: aggregate`, `if: always() && inputs.security_scan_enabled != 'false'`，单独 timeout（如 540min），自己 download catalog artifact → 跑 security → **自己 commit + push** catalog 的 security 增量。

**改动量**：较大。需要：
- aggregate 把 commit 后的 catalog 作为 artifact 上传（或 security job 直接 `git pull` 最新 main——更简单，因为 aggregate 已 push）。
- security job 自己 checkout + pull main → 跑 security → commit security 增量 → push（同样要 `pull --rebase --strategy-option=theirs` 防竞争）。
- `trigger-catalog-bundle-release` 维持 `needs: aggregate`（bundle 不等 security，security 是慢通道）。

**风险**：新 job 重复 checkout/install/cache-restore 样板；security job 单独 push 引入第二个 push 点，需处理与 aggregate push 的竞争（已有 `-X theirs` 范式可复用）。隔离性最好（security 再炸完全不碰主提交），但侵入面大。

### 2.4 推荐：B1（commit 前置）

配合 A 后，security 每轮工作量趋近于 0，"commit 前置 + security 殿后 + 增量延后一轮"是最小改动且彻底解耦的组合。B2 隔离更彻底但样板/竞争成本高，A 已让 security 不再爆，不需要 B2 的重武器。

---

## 3. content_hash 与 security 块的关系

### 3.1 security content_hash 怎么算 / 促升迁移改 source 会不会改它

- security 的 content_hash = `EvalCache.content_hash(content)`（sqlite_cache.py:332-334，纯 `sha256(content)`），其中 `content` = `_fetch_content` 拉到的 README/SKILL.md 文本（runner.py:318；fetch path :754/773/790）。fetch 失败回退 description（`content_fallback: description`，security_scan.yaml:21）。
- type=mcp 例外：`_build_mcp_security_eval_item`（eval_bridge.py:1198-1234）把 `source_url` 置 None、把序列化的 `install.config` 塞进 `description`，走 description 路径 → content_hash = `sha256(synth install.config)`，**不远端 fetch**（mcp 不贡献 429）。
- **促升迁移改 `source` 会不会改 content_hash？** 直接看：content_hash 只 hash fetch 到的 README 内容，**与 `source` 字段无关**——单看 hash 公式，改 source 不改 hash。**但** PRD 实测根因里"促升迁移改过 `source` 可能变了 hash"指的是更隐蔽的链路：促升/恢复可能改了 entry 的 `id` 或 `source_url`（fetch 的目标 URL），URL 变 → fetch 到的内容可能变/拉不到 → content_hash 变；且 SQLite cache 的复用 `_lookup_cached_result` 按 `(entry_id, rubric_version)` 定位历史 row（eval_bridge.py:255-265），**entry_id 变了就定位不到旧 row** → cache miss。这解释了为何 2820 条恢复 entry 全判冷。
  - **A 方案绕开了这整条**：A 不依赖 SQLite cache、不依赖 entry_id 稳定，只看 entry 自带的 `security.rubric_version`，所以 id/source/url 怎么变都不影响"已扫过就跳过"。这正是 A 比"warm SQLite cache"更鲁棒的原因。

### 3.2 security SQLite cache key 如何与质量评分隔离

- security cache key：`EvalCache.make_key(metric="__full__", content_hash, rubric_version, namespace="security")`（runner.py:842-847，`self._cache_namespace = "security"`，runner.py:153）。
- `make_key` 的 namespace 行为（sqlite_cache.py:296-329）：raw = `f"{metric}:{content_hash}:{rubric_version}"`，namespace 非空时 prepend → `f"security|{raw}"`，再 `sha256`。
- 质量评分路径 `namespace=None`（runner.py:153 else 分支），key = `sha256("__full__:hash:rubric")`，**不带 `security|` 前缀**。
- 结果：**同一个 SQLite 文件（`.eval_cache/`）、同一张 `eval_cache` 表**，security row 与质量评分 row 因 cache_key 前缀不同而天然隔离，互不命中、互不失效（bump security rubric_major_version 不影响质量 cache，反之亦然）。`authenticity` namespace 同理第三隔离（eval_bridge.py:1604-1605）。

---

## 4. 推荐方案（给 trellis-implement 的照做清单）

### 是否都做 / 先后

**A 和 B 都做。A 是根治（不再产生无谓 fetch+LLM），B 是防爆兜底（即便将来别处再炸也不挡 commit）。** 先做 A（直接消灭批量），再做 B（结构性解耦）。两者独立、可分别落地、分别单测。

A 的 content_hash 处理：**采纳 §1.4 (a) rubric-only 短路**（认 `security.rubric_version == 当前 rubric_version` + 块完整就跳过，不校 content_hash、不 fetch）。理由：security 不影响 decision、bump rubric_major_version 是总闸、(b) 校 hash 必须 fetch 自相矛盾。warm SQLite cache 列为**可选**单测项，非必需。

### 照做清单

**A 方案 — `scripts/eval_bridge.py`**
1. 新增 helper `_compute_security_rubric_version() -> str | None`（伪代码见 §1.5）：import `SECURITY_SCAN_SYSTEM_PROMPT` + `load_task_config("security_scan").rubric_major_version`，拼 `f"{major}.{sha8}"`；失败返 None。放在 `_run_security_scan`（:1273）上方。
2. 新增 helper `_is_security_block_complete(sec: dict) -> bool`：校 6 字段存在 + verdict∈{safe,caution,reject} + risk_level∈{clean,low,medium,high,extreme}。
3. 在 `_run_security_scan`（:1273）的 EvalItem 构建循环（约 :1314-1316，`eval_items=[]`/`for e in entries:` 之前）插入预筛：剔除 `isinstance(e.get("security"), dict) and e["security"].get("rubric_version")==current and _is_security_block_complete(...)` 的 entry，`logger.info` 报跳过数；`if not entries: return {}`。
4.（可选）跳过命中时 warm SQLite cache：用 `security["content_hash"]` + `make_key(namespace="security")` 回写一条 row，保持两短路一致。

**B 方案 — `.github/workflows/sync.yml`（aggregate job, :492-940）**
5. 采纳 **B1**：把 "Generate catalog sub-directory READMEs"（:880）、"Update bilingual README"（:890）、"Audit popular coverage"（:895）、"Commit and push if changed"（:906-940）整块**上移到 "Restore security eval cache"（:751）之前**，即放在 "Apply reject governance"（:708-740）之后。让 security scan（:763）+ Save security eval cache（:872）成为 aggregate 的**最后两个 step**。
6. 确认 `trigger-catalog-bundle-release`（:942）的 `needs: aggregate` + `if: needs.aggregate.result=='success' && needs.aggregate.outputs.catalog_changed=='true'` 在 step 重排后仍成立（commit step 仍产出 outputs，job 在 security 殿后超时被 cancel 时 result 会是 cancelled——但 commit 已发生，下游 bundle 仍能在本轮触发，因为 bundle 的判定在 commit step 跑完的瞬间已具备；若担心 job cancel 影响 `needs.aggregate.result`，可将 security 改 B2 独立 job）。**实现期需在干跑/结构验证里确认这一点**——这是 B1 唯一需要盯的边界。
7.（可考虑）security step 把 `timeout-minutes: 540` 调小（如 60-90min），配合 A 后单轮 security 应几分钟内完成；过大 timeout 是上次 6h 的直接帮凶。

**测试 — `tests/`**
8. `tests/test_eval_bridge_security.py`：加 (a) entry 带合法 security + rubric 匹配 → `_run_security_scan` 跳过、不调 judge（mock judge 断言 0 调用）；(b) rubric 不匹配 / 块不完整 → 仍进 runner；(c) 模拟 2820 条已带 security 批量 → 全跳过、judge 0 调用。
9. 回归确认现有 security 测试不破（`test_eval_bridge_security.py` / `test_enrichment_orchestrator_security.py` / `test_merge_index_security.py`）：失败兜底、verdict↔risk_level 校验、chunk write-back、`SECURITY_SCAN_ENABLED` 开关。

**文档 — `CLAUDE.md`**
10. security 段补："认 entry 已有 security 字段（rubric_version 匹配）短路 + aggregate commit 前置（B1）"；顺手修正 security `rubric_major_version` 当前值（文档写 1，YAML 实为 **2**）。

## Caveats / Not Found

- **未实测验证 GitHub Actions 在 step `continue-on-error: true` 但 job timeout 触发时，后续 step 是否 100% 被跳过**——基于 PRD 实测（`##[error]The operation was canceled` 后 merge+commit 没执行）推断为 job-level cancel 跳过所有后续 step。实现期 B1 重排后需用一次带 security 的 CI run 验证 commit 是否在 security 殿后超时时仍发生。
- §1.5 warm-cache 回写用的是历史 content_hash，若上游内容已变，回写的 cache 与"认字段跳过"同样不重扫——这是设计内一致行为，不是 bug，但单测描述需写清。
- `_compute_rubric_version_for_task`（eval_bridge.py:728）**不能**直接复用于 security（它走 `build_system_prompt` 而非 `SECURITY_SCAN_SYSTEM_PROMPT`），必须用 §1.5 的专用 helper。
