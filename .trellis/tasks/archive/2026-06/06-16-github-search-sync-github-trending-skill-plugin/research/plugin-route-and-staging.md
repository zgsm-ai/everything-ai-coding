# Research: plugin 端到端路线 + github-trending 分阶段重构落地可行性

- **Query**: ① github-trending 里 plugin 候选的端到端处理路线（与 skill 路线对比）+ "上传 marketplace" 的真实含义 + plugin bundle 检测为什么慢；② 把 `discover()` 单体拆成 Stage A 搜索 / Stage B 廉价预筛+LLM 判断 / Stage C 深拉的可行性，重点是 LLM 判断放哪
- **Scope**: internal
- **Date**: 2026-06-17

---

## 任务 1 — plugin 端到端路线（与 skill 路线对比）

### 1.1 github-trending 里 plugin 候选的逐步走向

入口在 `scripts/sync_github_trending.py`。流程是「search → classify(整树) → 按 kind 分流」。

**两路共享的前半段**（search + classify，都在 `discover()` 里）：

| 步骤 | file:line | 说明 |
|---|---|---|
| search 召回 | `sync_github_trending.py:159-208` (`search_repos` / `collect_candidates`) | 跑 `SKILL_QUERIES`+`PLUGIN_QUERIES`（:91-104），`sort=stars`，每查询翻 `MAX_PAGES`=3 页 |
| known_repos 预过滤 | `:123-154` (`build_known_repos`) + `:201-203` | 已在任意 catalog index 的仓直接挡掉 |
| 按 stars 降序、限量 `MAX_VERIFY`=300 | `:445-458` | 本轮只验证前 300 个 net-new 候选 |
| **classify_repo（瓶颈所在）** | `:284-308` | 对**每个**候选调一次 `list_repo_files(repo, branch)` = `utils.py:393` 的 `repos/<slug>/git/trees/<branch>?recursive=1`，**拉整棵递归树**。判定：含 `.claude-plugin/marketplace.json` 或根 `marketplace.json` → `"plugin"`；否则含任意 `SKILL.md` → `"skill"`；都无 → `None` |

**分流（`discover()` 主循环 `:474-557`）**：

- **kind == "plugin"**（`:496-508`）：**不**跑 megaapp 廉价过滤（marketplace.json 是强结构正信号），只把一个 `source_cfg` dict 追加进 `plugin_cfgs`（`id=github-trending`、`repo_slug`、`branch`、`source_priority=600`）。**plugin entry 不在 discover() 里构造**（schema 复杂，交下游 `sync_one_source`）。
- **kind == "skill"**（`:509-533`）：先跑 `is_megaapp()`（`:261-281`）廉价过滤（巨型 app 恰好捆 skill → 丢），过了再 `build_skill_entries()`（`:313-351`）→ 复用 `skill_registry.scan_repo_via_api`（**第二次 Tree API + 逐 SKILL.md raw fetch**）+ `hard_filter`，产出 skill entry。

**plugin 路线后半段**（`sync_github_trending.py:565-592` `sync_plugins`，在 `main()` `:620` 调用，`discover()` 之后）：

1. 初始化一个 `spo.PluginContentFetcher()`（来自 ai-resource-eval 包，`:570-574`）、`load_plugin_blacklist()`、`marketplace_verifier.load_cache()`。
2. 对每个 `plugin_cfg` 调 `spo.sync_one_source(cfg, ...)`（`sync_plugins_official.py:813`）。
3. `sync_one_source` → 拉 `.claude-plugin/marketplace.json`（`_marketplace_json_url` `:231`）→ 遍历 `plugins[]` → 对每个 plugin 调 `_entry_from_plugin`（`:629-806`）。

`_entry_from_plugin` 内部对**每个 plugin**做：
- `_plugin_manifest_candidate_urls` + `_http_get_json` 拉子 plugin 的 `plugin.json`（`:673-677`）
- `_resolve_layout_repo_and_root` + `_build_bundle_from_layout`（`:694-706`）→ 调 `layout_fetcher.detect_plugin_layout(repo, plugin_root, ref)`（**又一次 Tree API**，见 1.3）
- `_fetch_repo_meta(source_url)` 补抓 stars/pushed_at（`:735`，同 repo 跨 plugin 走内存 cache `:175`）
- `marketplace_verifier.verify_marketplace(repo_slug, name, cache)`（`:769`，产生 `marketplace_name` / `marketplace_verified`）
- 组装 entry，`install.method="plugin_marketplace"`、`type="plugin"`（`:775-805`）

4. 回到 `main()` `:645-650`：plugin entry 走 `merge_preserve(..., dedup_url=False)` 写 `catalog/plugins/index.json`（id-only dedup，因同 monorepo 多 plugin 合法共享 repo URL）。

### 1.2 skill vs plugin 路线差异（一张表）

| 维度 | skill 路线 | plugin 路线 |
|---|---|---|
| entry 在哪构造 | `discover()` 内 `build_skill_entries` (`:313-351`) | **不在 discover()**，延后到 `sync_plugins`→`sync_one_source`→`_entry_from_plugin` |
| 复用的上游脚本 | `skill_registry.scan_repo_via_api` (`skill_registry.py:138`) | `sync_plugins_official.sync_one_source` (`sync_plugins_official.py:813`) |
| 廉价过滤 | 跑 `is_megaapp` (`:511`) | **不跑**（marketplace.json = 强正信号） |
| LLM 真伪判断 | 有（`resource_authenticity.is_primary_skill`，在 eval 层，见任务 2.2） | **无**（plugin 是 bundle，`is_primary_skill` 框架不适用，权威信号是 `marketplace_verified`） |
| 额外网络成本 | classify 整树 + scan 再整树 + 每 SKILL.md raw | classify 整树 + **每子 plugin** 拉 plugin.json + detect_plugin_layout 整树 + hooks/mcp 探测 + stars |
| 写入 index | `catalog/skills/index.json`，`dedup_url=True` (`:639`) | `catalog/plugins/index.json`，`dedup_url=False` (`:647`) |
| source_priority | （走 skill schema，无此字段）| 600（低于 official 1000 / superpowers 950 / ECC 900 / dev 700） |

### 1.3 plugin bundle 检测为什么慢 + 能否解耦

**慢的根因**——`_entry_from_plugin` 对 marketplace 里**每个**子 plugin 都做整树级探测：

- `detect_plugin_layout(repo, plugin_root, ref)` (`ai-resource-eval/.../fetcher/plugin.py:165`) → `_fetch_tree` (`:389`) 调 `repos/<repo>/git/trees/<ref>?recursive=1` **拉整棵递归树**。虽然 `_tree_cache` 按 `(repo, ref)` 缓存（`:158, :391-393`），同一 monorepo 多 plugin 只拉一次树；但**跨 repo**（dotnet/skills 这种一个仓 13 个 plugin 仍是同 repo→共享一棵树，真正爆炸的是**不同 source repo** 各拉一棵）。
- `_extract_hooks` + `_extract_mcp_servers` (`fetcher/plugin.py:302-305`) 对**每个** plugin 额外 raw-fetch `hooks.json` / `mcp.json` / `plugin.json`（`_raw_cache` `:159` 缓存，但仍是 per-plugin 的多次 HTTP）。
- `_plugin_manifest_candidate_urls` (`sync_plugins_official.py:673`) 每子 plugin 试 2 个 plugin.json URL。
- `_fetch_repo_meta` (`:735`) 每 source_url 一次 GitHub API（同 repo cache）。

**能否延后/解耦**：可以。bundle 计数 + marketplace_verified 都不是「能否安装」的硬前提——`_build_bundle_from_layout` 在 fetcher 缺失时整体置零、`sync_plugins` 在 `PluginContentFetcher is None` 时 bundle 全零仍正常出 entry（`sync_github_trending.py:570-574` + `sync_plugins_official.py:945-951` 已有此降级路径）。也就是说 Stage C 里 plugin 完全可以「先只用 marketplace.json 的 `plugins[]` 出最小 entry，bundle/hooks/mcp 探测延到 enrich 层或后续轮次」。注意：现有官方 plugin sync 把这部分放在 sync 层（带可选 ai-resource-eval），所以 github-trending 沿用同一路径只是「成本叠加」，并非架构强制。

---

## 任务 1 续 — "上传 marketplace" 到底指什么（完整链路）

**关键结论：本仓 sync 不发布任何 marketplace.json。"上传 marketplace" 指的是一条独立的 release 链路，把 catalog 打成 bundle → 触发外部仓 `costrict-plugin-marketplace` 重新发布它自己的 marketplace 镜像。** 它跟「github-trending 发现一个 plugin」之间是**异步、解耦**的：trending 只负责把 plugin entry 写进 `catalog/plugins/index.json`，剩下全靠 catalog → bundle → 外部发布。

### 2.1 plugin entry 里的 marketplace 字段怎么产生

全部在 `sync_plugins_official._entry_from_plugin` 的 `install` 块（`:788-795`）：

- `install.marketplace_repo` = `source_cfg["repo_slug"]`（trending 时 = 被发现的那个 GitHub `owner/repo`，`:791`）
- `install.marketplace_name` / `install.marketplace_verified` ← `marketplace_verifier.verify_marketplace(repo_slug, name, cache)` (`:769`)：
  - `verify_marketplace` (`marketplace_verifier.py:197-245`) 拉该 repo 的 `marketplace.json`（4 个 URL 候选：`.claude-plugin/marketplace.json` / `marketplace.json` × `main` / `master`，`:147-167`）
  - `marketplace_name` = manifest 的 `name` 字段，且必须匹配 `^[A-Za-z0-9._-]+$`（`:55, :177-180`），否则 None
  - `marketplace_verified` = True **当且仅当** 有合法 `marketplace_name` **且** `plugin_name` 真在 manifest 的 `plugins[]` 数组里（`:241-244`）
- `install.marketplace`（`:794`）= repo_slug，display-only，UI 后向兼容

这些字段**只是元数据**，标记「这个 plugin 来自哪个 marketplace、该 marketplace 是否可验证」。它们**不产生**任何新的 marketplace.json。

### 2.2 真正「生成/发布 marketplace」的链路（catalog bundle release）

链路三跳，全在 CI / 外部仓：

**跳 1 — Weekly Sync 触发 release**（`.github/workflows/sync.yml:892-915`，job `trigger-catalog-bundle-release`）：
- 条件：`aggregate` 成功 **且** `catalog/index.json` 真的变了（`:894` `catalog_changed == 'true'`，由 `:864-867` 的 git diff 判定）
- 动作（`:904-910`）：`gh workflow run release-catalog-bundle.yaml -f services_to_download=...,plugins -f publish_plugin_marketplace=true`

**跳 2 — Release Catalog Bundle**（`.github/workflows/release-catalog-bundle.yaml`）：
- `build-and-release` job：`download_catalog.py` 把每条 entry 的内容文件拉到 `catalog-download/` → `build_catalog_bundle.py` (`scripts/build_catalog_bundle.py`) 打成 `dist/catalog-bundle.tar.gz`（含 `manifest.json` + 过滤后的 `index.json` + `catalog-download/` 全树，`build()` `:152-271`）→ `gh release create/upload`（`:221-235`）做成 GitHub Release asset
- tag 规则（`:148-161`）：push `catalog-bundle-v*` tag → 用该 tag；**workflow_dispatch（trending 这条就是 dispatch）→ tag = `catalog-bundle-manual-<short-sha>`**（这正是用户提到的 `catalog-bundle-manual-*` tag 的来源，是「无 SemVer tag 的 ad-hoc 重建」路径）
- bundle 内 plugin entry 走 `_prune_plugin_child_parent_consistency`（`build_catalog_bundle.py:274-323`）保证 parent/child 引用一致；plugin 的内容文件落 `catalog-download/plugins/<id>/.plugin.json`（`TYPE_DIR_AND_FILE` `:53-59`）

**跳 3 — Publish plugin marketplace（真正"上传 marketplace"）**（`release-catalog-bundle.yaml:240-252`，job `publish-plugin-marketplace`）：
- 条件：`push` 事件 或 `inputs.publish_plugin_marketplace`（trending 触发时传的就是 `true`）
- 动作：**调外部仓的 reusable workflow** `costrict-plugins-repo/costrict-plugin-marketplace/.github/workflows/publish-marketplace.yml@main`（`:243`），把 `catalog_bundle_url`（刚发布的 GitHub Release tar.gz）+ `bundle_sha` + `index_sha` + `version` + `publish=true` 传过去
- **这一步才是「上传/发布 marketplace」**：外部仓 `costrict-plugin-marketplace` 消费 catalog bundle，生成/更新它自己的**面向 costrict 用户的 plugin marketplace 镜像**。本仓代码里看不到它的实现（在外部仓）。

### 2.3 用户最终怎么安装一个 github-trending 发现的 plugin

两条独立安装语义，取决于客户端：

1. **Claude Code 路径**（直接用 entry 的 `install` 块）：entry `install.method="plugin_marketplace"`、`platforms=["claude-code"]`（`sync_plugins_official.py:787-795`）。安装命令引用的是 **`install.marketplace_repo`（原始 GitHub repo）** + `install.marketplace_name`（manifest name），形如 `enabledPlugins["<plugin_name>@<marketplace_name>"]`（marketplace_verifier 模块 docstring `:8-12` + CLAUDE.md「Marketplace 字段」段）。**前提是 `marketplace_verified=True`**，否则前端显示 unverified banner、install 命令拒绝（CLAUDE.md 同段）。这条**不经过** catalog-bundle release——直接指向上游原始 repo 的 marketplace.json。
2. **costrict 路径**：用户从 `costrict-plugin-marketplace`（跳 3 发布的镜像）安装。这条**经过** catalog-bundle release。

**所以「上传 marketplace」对 github-trending 发现的 plugin 的实际意义**：trending 把 plugin 写进 catalog → 下个 aggregate 若 catalog 变了 → 自动 dispatch release → 把整个 catalog（含这个新 plugin）打 bundle → 推给外部 costrict-plugin-marketplace 重新发布。trending 脚本本身**只到「写 catalog/plugins/index.json」为止**，发布是全 catalog 级的下游副作用，**不是 plugin 专属、也不在 sync 脚本里**。

---

## 任务 2 — 分阶段重构落地可行性

### 2.1 现有 discover() 结构能否拆成 A/B/C

现状：`discover()`（`sync_github_trending.py:413-560`）是单体——search→排序限量→**逐候选 classify(拉整树)→megaapp 预筛→build**。瓶颈正是循环内 `classify_repo`（`:494`）对每个候选拉整棵递归树（CLAUDE.md/PRD 实测 ~21min）。

**拆解可行性：现有代码已天然切出三段，重构主要是「把循环内的 Tree 拉取从 classify 时机推迟」**：

- **Stage A 搜索（零 Tree）**：`collect_candidates` (`:183-208`) 已经是纯 search API、零 Tree。**已具备**，无需改。产物：`candidates = {full_name: search_item}`，search_item 自带 size/topics/desc/stars 等（见 2.3）。
- **Stage B 廉价预筛（不拉巨型树）+ LLM 判断**：当前 `is_megaapp` (`:261-281`) **依赖** `meta.total_files`/`skill_count`，而这两个数**只能从已 fetch 的整树拿到**（`classify_repo:295-302`）。这是核心矛盾——**现有 megaapp 过滤不是「廉价」的，它寄生在昂贵的 classify 整树之后**。要做成真·零-Tree 预筛，必须改用 search_item 自带字段（`size`/`topics`/`description`，见 2.3）替代 `total_files`。LLM 判断当前**完全不在这个阶段**（在 eval 层，见 2.2）。
- **Stage C 逐条深拉**：`classify_repo`(整树) + `build_skill_entries`(scan 再整树) + plugin 的 `sync_plugins`/`detect_plugin_layout`。**已具备**，是现在循环体的内容，只需改成「只对 Stage B 留下的候选跑」。

**中间表落点**：现成的 `verify_cache`（`VERIFY_CACHE_PATH = .github_trending_cache/verify_cache.json`，`:59`，`load_verify_cache`/`save_verify_cache` `:392-408`）已经是一个按 `full_name` keyed、含 `pushed_at`/`kind`/`total_files`/`skill_count` 的中间表，且有增量落盘（`VERIFY_CACHE_FLUSH_EVERY` `:86, :552-557`）。Stage A/B 的候选表可直接复用这个 cache 文件格式扩展（加 `size`/`topics`/`prefilter_verdict` 等列），CI 已为它配了独立 weekly cache block（`sync.yml:124-133, 327-333`）。

### 2.2 LLM 判断放哪——两条路线对比（核心矛盾）

**事实澄清：LLM 判断（is_primary_skill）已经存在，且已在 eval 层，不在 sync 层。** 不是要新建，而是要决定「是否前移到拉表阶段」。

现状落点（全在 eval 层 / ai-resource-eval，非 stdlib）：
- 判断逻辑：`eval_bridge.py:1506-1668`（`_run_authenticity_scan` / `_authenticity_one`），prompt 在 `:1429-1459`，输出 `{is_primary_skill, reason}` 写进 `entry["resource_authenticity"]`
- scope：**仅 `source=="github-trending" AND type=="skill"`**（`:1531-1536`）；**plugin 刻意排除**（plugin 是 bundle，权威信号是 `marketplace_verified`，`:1517-1525`）
- 独立 cache namespace `"authenticity"`（`:1604-1606`），与质量 6 维 / security cache 隔离
- 调用时机：`enrichment_orchestrator.enrich_entries` `:82-104`（在 enrich matrix job 里，`sync.yml:341-434` 的 `type=skill` cell），**不在 sync-data job**
- 落地为 reject：`scoring_governor._apply_resource_authenticity_to_decision`（`:78-127`）——`is_primary_skill==False` → `decision="reject"`；缺字段 → 保守放行；plugin 不受此闸（`:104-105`）

**为何这是矛盾**：CLAUDE.md「sync 脚本仅用标准库（urllib、json）」。LLM 判断需要 judge + GitHubFetcher + EvalCache（全在 ai-resource-eval，pydantic/httpx）。用户想「拉表时并行做 LLM 判断」= 把上面这套搬进 sync 循环 = 打破 stdlib-only。

**路线①：sync 只产「候选表」，LLM 预筛 + 深处理放进一个新的非 stdlib 阶段**

- sync_github_trending 退化成 Stage A+B-cheap：只 search + size-based 廉价预筛，输出候选表（含 metadata）到 `.github_trending_cache/`，**不调任何 ai-resource-eval、不拉整树**。保持 stdlib-only 不破。
- 新建一个独立脚本（例如 `scripts/triage_github_trending.py`，可 `import ai_resource_eval`）做 Stage B-LLM + Stage C：读候选表 → 对每个候选先 LLM `is_primary_skill` 廉价预筛（**只喂 search desc + README，不拉整树**，正是 `_authenticity_one` 现在 fetch 的 `["SKILL.md","README.md"]` 内容，`eval_bridge.py:1560,1591-1597`）→ 判 false 的直接丢、不进 Stage C → 判 true 的才 `classify_repo`/`scan`/plugin 深拉 → 写 index。
- 复用点：`_run_authenticity_scan`/`_authenticity_one`（`eval_bridge.py:1506,1577`）几乎可直接调，它已自带 fetch+cache+judge，且**目前喂的内容就不需要整树**（只 README/SKILL.md raw）。
- 代价：新增一个 CI step（在 sync-data 之后、或单独 job），且该 step 需 LLM key（与 enrich 同款 secrets，`sync.yml:401-403`）。
- file:line 落点：新脚本调 `eval_bridge._run_authenticity_scan`（`eval_bridge.py:1506`）；Stage C 复用现 `sync_github_trending.classify_repo`/`build_skill_entries`/`sync_plugins`（`:284,313,565`）；CI 在 `sync.yml:224-230`（现 trending step）后插新 step。

**路线②：LLM 判断仍留 eval 层，sync 只做 size-based 廉价预筛**

- sync_github_trending 不动 LLM；只把 `is_megaapp` 从「整树后的 total_files」改成「search_item 自带 size/topics/desc」的**真·零-Tree 预筛**（`:261-281` 改输入源），把明显巨型 app 在拉树前挡掉，剩下的才 classify 整树。LLM `is_primary_skill` 维持现状——在 enrich matrix 的 skill cell 跑、governor reject（`eval_bridge.py:1506` + `scoring_governor.py:78`），**不前移**。
- 优点：改动最小、stdlib-only 不破、LLM 成本仍走已有 enrich/cache 路径，不新增 CI step。
- 缺点：LLM 判断滞后一个 enrich 周期才生效（先入库再下周 reject），且**深拉成本（classify 整树 + scan）仍发生在 LLM 判断之前**——只省了「明显巨型 app」那部分树，省不掉「LLM 才能判出的伪 skill」的深拉。这与用户「边拉表边 LLM 判断、避免深拉」的诉求只部分契合。
- file:line 落点：改 `is_megaapp` 输入（`sync_github_trending.py:261-281` + 调用点 `:511`），新增一个 size-based helper（用 search_item，零网络）；不碰 eval_bridge / orchestrator / governor。

**两条路线的本质区别**：路线① 把「贵的判断」前移到 sync 之后的新阶段，能在深拉前用 LLM 砍候选（最贴合诉求，但破 sync 的 stdlib-only 边界 → 必须用新脚本承接）；路线② 守住 sync stdlib-only、改动小，但 LLM 砍候选发生在深拉之后、且滞后一周期。

### 2.3 search item 里可零成本用于预筛的字段

`collect_candidates` 拿到的 search_item（GitHub `search/repositories` 返回，`sync_github_trending.py:174` `data["items"]`）已被现有代码读取的字段：

| 字段 | 已用处 file:line | 预筛用途 |
|---|---|---|
| `full_name` | `:194,475` | 候选 key / dedup |
| `stargazers_count` | `:198,446` | 已用于 MIN_STARS 过滤 + 排序 |
| `default_branch` | `:476` | classify/scan 的 branch（避免 main 猜错） |
| `pushed_at` | `:477` | freshness + verify_cache 失效判定 |
| `topics` | `:478` | **预筛主力**：`_has_skill_plugin_topic` (`:253-258`) 强正信号 override |
| `description` | `:479` | `_APP_DESC_RE` (`:236-243`) app/agent 负信号；喂 LLM 预筛 |
| **`size`** | **未用** | **零成本 megaapp 代理**：repo KB 大小可替代 `total_files` 做拉树前预判（巨型 app 通常 size 极大）。当前 `is_megaapp` 用的 `total_files` 必须拉树才有；`size` 在 search_item 里免费 |

`size` 是目前**唯一未被利用、但能在零 Tree 成本下近似 megaapp 判断**的字段——这是把 Stage B 做成真·廉价预筛的关键。`topics`/`description` 也都是零成本，且现有 megaapp/override 逻辑已在用它们（只是寄生在整树之后）。

---

## 风险 / 注意点

1. **megaapp 阈值需重新校准**：现有阈值（`MEGAAPP_FILE_THRESHOLD=2000` 文件、密度 10‰，`:225-226`）是用 `total_files` 校准的（样本见 `:215-224`）。换成 `size`(KB) 预筛需要新校准——`size` 与 `total_files` 不线性（大二进制/大文档会撑大 size 但文件数不多），可能误杀「文档多但真 skill 集」的仓。PRD 里的样本（openclaw 20116 文件 / graphify 579 文件等）没有给 `size` 数据，校准前需补采。
2. **路线① 破 stdlib-only 边界**：必须落在**新脚本**而非 sync_github_trending 内（CLAUDE.md 硬约束 + `sync_github_trending.py:19` docstring 自述「仅标准库 + 本仓 utils/...」）。eval_bridge 已是非 stdlib，复用它即可，别把 import 写进 sync 脚本顶层。
3. **LLM 预筛 ≠ 免拉内容**：`_authenticity_one` 仍需 fetch README/SKILL.md raw（`eval_bridge.py:1591-1597`），只是**不拉整棵递归树**。所以「廉价」是相对 classify 整树而言，不是零网络。
4. **plugin 不走 is_primary_skill**：任何重构都要保留 plugin 排除（`eval_bridge.py:1517-1525` + `scoring_governor.py:104`），否则合法 plugin marketplace（ECC 这种 harness+marketplace.json）会被误判 reject。plugin 的把关信号是 `marketplace_verified`。
5. **plugin bundle 探测解耦的副作用**：若把 `detect_plugin_layout`/hooks/mcp 延后，`bundle.*` 计数会暂时为零，前端 Detail 的 bundled chip / `bundled_in` 反向映射（CLAUDE.md「软标注」段）会缺数据，需确认下游能容忍零 bundle（现有 `PluginContentFetcher is None` 降级路径已证明能容忍）。
6. **release 是全 catalog 级、不可按 plugin 触发**：`trigger-catalog-bundle-release` 只看 `catalog_changed`（`sync.yml:894`），无法只为「新发现一个 plugin」单独发 marketplace。重构 trending 不影响这条链路，但也无法让 trending「立即上架」一个 plugin——它必须等下一次 aggregate + release。
7. **verify_cache 作中间表的 schema 演进**：复用 `.github_trending_cache/verify_cache.json` 加列时注意现有读取处（`:486-492`）只认 `pushed_at`/`kind`/`total_files`/`skill_count`，加 `size`/`prefilter_verdict` 等新列要保证旧 cache 行缺列时不崩（现有 `.get(..., 0)` 风格已较稳）。
