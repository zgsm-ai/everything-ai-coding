# Research: github-trending / 促升 entry 跨轮持久化 bug — 根因与修复方案

- **Date**: 2026-06-18
- **Scope**: internal
- **方法**: 主 session 实测（git show 跨 commit 对比 + 代码精读），research agent 首次 dispatch 流超时未落盘，本文件由主 session 内联只读诊断产出。

## 结论速览

1. **根因（双侧对称）**：`sync_skills.py:1003` 和 `sync_plugins_official.py:1064` 都用 `save_index(all_entries, output_path)` **整文件覆盖** per-type index，`all_entries` 只含各自的产出（skills=Tier1/2；plugins=official/dev/csc）。`overlay_added_at` 只搬 `added_at` 字段、**不搬 entry 本身**（`catalog_lifecycle.py:63-77`：只遍历 `regenerated`，existing-only entry 被丢）。CI 里 sync_skills / sync_plugins 跑在 triage **之前**，triage 又因 `known_repos` 跳过已入库仓不再产出 → 上轮 triage 写的 github-trending/促升 entry 每轮开头被覆盖、永不补回。
2. **实测铁证**：
   - skills：`0db0532` github-trending 54 仓 1508 条 vs `f47daa7` 33 仓 852 条，**0 重叠**；9 个促升仓 + mattpocock 之外全没。
   - plugins：`0db0532` 有 browserbase(5)/dotnet(13)/jeffallan 等 github-trending plugin；`f47daa7` 换成 buildwithclaude(66)/microsoft-skills(7) 等全新集，**browserbase 促升 plugin 已没**。
   - 连**未被 06-18 迁移**的 220 条 github-trending skill 也消失 → 与迁移无关，是无差别覆盖。
3. **不是其他写入点**：`sync_skills_sh` 写独立文件 `catalog/skills/skills_sh_index.json`（`:38`），不碰 index.json。`merge_index.py:985-1002` 的 per-type 写是"synthesized plugin children"同步，**保留 existing**（`merged = [existing 去掉 child_ids] + children`，且先 filter 掉 `_PLUGIN_BUNDLED_SOURCES`），不是 blanket overwrite、不丢 github-trending。`merge_index.py:1437` 写 `catalog/index.json` 是从 per-type 重生成 → per-type 修好后它自然正确。

## 修复方案（推荐）

### 核心：sync_skills / sync_plugins 覆盖前保留"triage 域"的 existing entry

两侧对称改。以 sync_skills 为例（`sync_skills.py:991-1003`）：

```python
all_entries = deduplicate(all_entries)
output_path = os.path.join(CATALOG_DIR, "index.json")
existing_entries = load_index(output_path)
if not all_entries and existing_entries:
    ...  # 0-entry clobber 守卫，保持不变
    return
all_entries = overlay_added_at(all_entries, existing_entries, today=TODAY)
# ★ 新增：保留 triage 写入域（active-discovery）的 existing entry，sync_skills 不产出它们
preserved_foreign = [e for e in existing_entries if _is_trending_owned(e)]
# 与 all_entries 按 id 去重后并入（all_entries 优先；理论上不会撞，因 source 域不交）
all_entries = _merge_keep_foreign(all_entries, preserved_foreign)
save_index(all_entries, output_path)
```

**`_is_trending_owned(entry)` 判据（推荐方案 b：按 source 显式判 active-discovery 域）**：
```python
PROMOTED_SLUGS = {r["source_slug"] for r in load_promoted_repos()}  # 复用 sync_github_trending.load_promoted_repos
def _is_trending_owned(e):
    s = e.get("source")
    return s == "github-trending" or s in PROMOTED_SLUGS
```
- **为何 (b) 而非 (a)正向白名单**：sync_skills 的产出 source 是动态集（Tier2 per-repo repo_slug 来自 skill_repos.json，会变），正向"只删自己 source"难以稳定枚举。而 active-discovery 域恰好是 **triage 唯一写入的 source 集** = `{github-trending} ∪ 促升 slug`，定义清晰、DRY（直接复用 `load_promoted_repos`）。
- **不会误伤 Tier2**：Tier2 per-repo source（如 `ComposioHQ/awesome-claude-skills`）由 sync_skills 自己 regenerate（在 all_entries 里），不在 PROMOTED_SLUGS（促升清单是特定 10 项），所以既不被 `_is_trending_owned` 命中、也不会被丢。促升 slug（如 `mattpocock/skills`）与 Tier2 不重叠（mattpocock 不在 skill_repos.json）。
- **撞 id 兜底**：`_merge_keep_foreign` 按 id 去重，all_entries 优先；正常情况下两域 source 不交、id 不撞，仅作防御。

plugin 侧同理，在 `sync_plugins_official.py:1064` 前对 `existing`（`load_index(args.output)`）做同样的 `_is_trending_owned` 保留再并入。注意 plugin 的 url-dedup 语义（同 monorepo 多 plugin 共享 URL）——并入时**按 id 去重即可，不要按 url 去重**（对齐 `merge_preserve(dedup_url=False)`）。

### 一次性恢复已丢失数据（推荐做）

已丢的 1508 skill + 38 plugin 在 git 历史里：**从 `798e6cf`（促升迁移后）回灌最优**——那时 9 仓已是促升 slug、220 条仍 github-trending，source 已是终态。

- 写一次性脚本 `scripts/recover_trending_entries.py`：从 `git show 798e6cf:catalog/skills/index.json` / `:catalog/plugins/index.json` 取出 `_is_trending_owned` 的 entry，**merge_preserve 进当前 catalog/{skills,plugins}/index.json**（按 id；plugin 不按 url）。
- **冲突评估**：`798e6cf` 的 active-discovery 仓集与 `f47daa7` 本轮新集 **0 重叠**（实测），故无 id 撞、无 deduplicate 误合并风险。本轮新增的 mattpocock(32) 是促升 slug，`798e6cf` 无 mattpocock（那时还没入库）→ 不冲突。
- **顺序铁律**：必须**先部署 sync_skills/sync_plugins 修复**，再跑恢复脚本，否则下一轮 CI 又把回灌的抹掉。恢复脚本本地跑 + 结果一并 commit。
- dry-run + 幂等（已存在的 id 跳过）。

## 防回归

- CI 顺序（CLAUDE.md CI 段）确认：`sync_skills … sync_plugins(official→dev→csc) … sync_github_trending → triage → … merge_index`。triage（`flush_skills`/plugin flush 走 `merge_preserve`）是 per-type index 的**最后**写入者且本就保留 existing —— 问题纯在 sync_skills/sync_plugins 的**前置**覆盖，修好前置即闭环。
- **回归测试思路**：构造 existing index 含 1 条 `source=github-trending` + 1 条 `source=mattpocock/skills`（促升）+ 正常 Tier1 entry → 跑 sync_skills 的写盘逻辑（mock 掉网络发现，all_entries=仅 Tier1）→ 断言写盘后 github-trending/促升两条**仍在**、Tier1 正常更新、0-entry 守卫与 overlay_added_at 不回归。plugin 侧对称测试（含同 monorepo 多 plugin 共享 url 不被误删）。
- CLAUDE.md 数据流水线段补一句：sync_skills/sync_plugins 覆盖 per-type index 时**必须保留 active-discovery（github-trending + 促升 slug）外来 entry**。

## 关键文件 / 行号

| 文件 | 行 | 作用 |
|---|---|---|
| `scripts/sync_skills.py` | 991-1003 | ★ blanket overwrite（skills 根因） |
| `scripts/sync_plugins_official.py` | 79, 1064 | ★ blanket overwrite（plugins 根因，OUTPUT_PATH + save_index） |
| `scripts/catalog_lifecycle.py` | 46-77 | overlay_added_at 只搬 added_at 不搬 entry |
| `scripts/sync_github_trending.py` | 514-545 | merge_preserve（triage 写入，已正确，可复用其去重思路） |
| `scripts/sync_github_trending.py` | `load_promoted_repos` | 促升 slug 集来源（DRY） |
| `scripts/triage_github_trending.py` | 148-166 | flush_skills（per-type 最后写入者，已正确） |
| `scripts/merge_index.py` | 985-1002 | synthesized plugin children（保留 existing，非 churn 点） |
| `scripts/sync_skills_sh.py` | 38 | 写独立 skills_sh_index.json（无关） |

## Caveats

- plugin 侧 `sync_plugins_superpowers.py` / `sync_plugins_registry.py` 是否也各自 save_index 覆盖 catalog/plugins/index.json？本文件只确认了 official（OUTPUT_PATH+save_index:1064）。实现时需确认 dev/registry 两个脚本的写入目标——若它们写同一 index.json 且各自 overwrite，则**最后一个跑的**决定 existing；CI 顺序 official→dev→csc，需保证**链条上每个 plugin sync 都保留 foreign**，或只让最后一个保留（取决于它们是否互相 merge_preserve）。这是实现阶段必须先核实的点。
