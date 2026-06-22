# Research: 把 github-trending 优质 monorepo 仓促升为一等上游源

- **Query**: 调研把 github-trending 发现的优质 monorepo skill/plugin 仓（google/skills、K-Dense-AI/scientific-agent-skills、Dimillian/Skills、thedaviddias/Front-End-Checklist、ComposioHQ/awesome-codex-skills、mattpocock/skills 等）从「统一 source=github-trending」促升为各自独立的一等源（per-repo source slug + 展示名），让 costrict-web 多展示一批来源。
- **Scope**: internal（含 1 处外部契约确认）
- **Date**: 2026-06-18

---

## 结论速览

1. **source → 展示链路有两条，分别给两个消费者**：
   - **About 页**走 `sources.json`（聚合表）：新 source **必须登记进 `SOURCE_REGISTRY`** 才显示，否则只打 WARNING、被静默丢弃。
   - **costrict-web** 走 catalog bundle 里的 `index.json`（逐 entry 原样带 `source` 字段）：**不读 `sources.json`、不依赖 `SOURCE_REGISTRY`**。所以"让 costrict-web 多展示来源"只需把 entry 的 `source` 字段改成 per-repo slug，**改完即生效**，登记 registry 只是为了我们自己 About 页也显示。
2. **逐仓 source 已有先例**：Tier-2 `skill_registry.discover_skills` 早就给每条 entry 设 `"source": repo_slug`（`owner/repo`），catalog 里 `ComposioHQ/awesome-claude-skills`（285 条）就是活的例子。直接复用此模式即可。
3. **促升机制干净、难度低**：把选定仓挪进一个 per-repo-source 的 curated seed 清单，扫描时设 `source=<专属 slug>` 而非 `github-trending`；再在 `source_registry.py` 批量登记展示名。**dedup 不受影响**（dedup 按 `id`/`source_url`/identity-key，不看 `source`），但**已入库旧 entry 不会自动改 source，需要一次性迁移脚本**。
4. **one-type-per-source 约束真实存在**：`SOURCE_REGISTRY` 每个 slug 只有一个 `type` 字段。skill 仓没问题；`dotnet/skills` 走 plugin 路由会撞这个约束（同 github-trending 现状一样需要"按主体归一个 type"）。
5. **候选清单见 §5**：高 accept 率 + 知名出品方共筛出约 9 个值得促升的仓。

---

## Findings

### 1. source → costrict-web 展示链路（关键）

#### 1a. `source` 字段在哪里被写

| type | 写 source 的位置 | 值 |
|---|---|---|
| skill（github-trending） | `scripts/sync_github_trending.py:434` `"source": SOURCE_ID` | 常量 `github-trending`（定义 `sync_github_trending.py:95`） |
| plugin（github-trending） | `scripts/triage_github_trending.py:238` cfg `"id": sgt.SOURCE_ID` → `sync_plugins_official.py:851` `"source": source_cfg["id"]` | `github-trending` |
| skill（Tier-2 发现） | `scripts/skill_registry.py:358` `"source": repo_slug` | **per-repo `owner/repo`** ← 先例 |
| plugin（各 marketplace） | `sync_plugins_official.py:851` `"source": source_cfg["id"]` | per-source id（如 `claude-plugins-official`） |

#### 1b. 链路一：About 页（`sources.json`）

```
catalog/index.json (每 entry 带 source 字段)
  → scripts/build_frontend_data.py:218  build_sources_payload(items)
      → scripts/source_registry.py:180  build_sources_payload()
          - counts = Counter(i["source"] ...)           # :190
          - 只遍历 SOURCE_REGISTRY 里的 slug              # :193
          - count==0 的 registered slug 跳过（不显示）    # :195-196
          - 实际出现但**未登记**的 source → WARNING + 不展示 # :227-231
  → frontend/public/api/sources.json
  → 前端 About 页"数据源 / 信任分级"两区块渲染
```

**新 source 在 About 页"显示出来"的条件（硬性）**：
- 必须把它的 `source` slug 登记进 `SOURCE_REGISTRY`（`source_registry.py:37-177`），带 `label`/`url`/`type`/`trust`；
- 且本周期 catalog 里该 source 的 `count > 0`。
- 未登记 → 命中 `source_registry.py:227-231` 的 WARNING "`source '<x>' (n=…) 不在 SOURCE_REGISTRY，未展示于 sources.json`"，**About 页看不到它**。
- 注意 `type` 必须是 `TYPE_ORDER`（`source_registry.py:26`）里的已知值，否则 `:208` 的 `TYPE_ORDER.index()` 抛 `ValueError`（这也是 github-trending 被硬归到 `Skills` 的原因，见 `source_registry.py:165-176` 注释）。

**当前已存在的 registry-vs-actual drift（重要旁证）**：实测 catalog 里有 16 个 source 值未登记、只 WARN 不展示，包括 per-repo 的 `ComposioHQ/awesome-claude-skills`(285)、还有 slug 拼写漂移的 `registry.modelcontextprotocol.io`(5546，registry 里登记的却是 `mcp-registry`)、`skills-sh`(123，登记的是 `skills.sh`)、`awesome-windsurfrules`(108，登记的是 `windsurfrules`)。即 **registry 的 key 必须逐字等于 entry 写入的 `source` 字面值**（`source_registry.py:15-16` 维护约定明说这一点），批量促升时务必对齐 slug 字面值，否则白登记。

#### 1c. 链路二：costrict-web（catalog bundle 的 `index.json`）

```
catalog/index.json
  → scripts/build_catalog_bundle.py（三道 filter：orphan / mcp_empty_stub / md_yaml_broken）
      - 只整条丢弃 entry，**不删/不改任何 entry 字段**（build_catalog_bundle.py 无 field strip）
  → dist/catalog-bundle.tar.gz 内的 index.json（entry 原样带 source 字段）
  → costrict-web 的 CatalogIngestService 一次 HTTPS GET 消费
     （scripts/build_catalog_bundle.md:5,111-112）
```

**costrict-web 的来源展示契约（我们这边能看到的部分）**：
- 下游 service：`costrict-web/server/internal/services/catalog_ingest_service.go`（外部仓，本仓只有引用，见 `build_catalog_bundle.md:111`）；链路总览 `costrict-web/docs/CATALOG_INGEST.md`（外部，本仓无副本）。
- 下游消费的是 **bundle 内 `index.json` 的逐条 entry**，bundle **不含 `sources.json`**（产物布局 `build_catalog_bundle.md:20-32` 里没有 sources.json）。
- 因此 costrict-web 看到的"来源"= 每条 entry 的 `source` 字段原始字面值。**它不经过 `SOURCE_REGISTRY` 过滤**——这正是"促升后 costrict-web 立刻多出一批来源"的原因：只要 entry 的 `source` 从 `github-trending` 变成 `composiohq/awesome-codex-skills` 等，下游分组就自动多出这些来源，无需我们登记 registry。
- bundle `schema_version=1`（`build_catalog_bundle.md:38`），promote 不改 schema，不需要下游同步升级。
- **未知点**：costrict-web 如何把 raw `source` 字面值映射成展示名 / 是否对 source 值做白名单，是外部仓逻辑，本仓不可见。若它直接展示 `source` 字面值，promote 后会显示 `owner/repo` 这样的原始 slug（与 Tier-2 现状一致）。

---

### 2. 逐仓 source 机制是否已有先例

**有，直接复用即可。**

- Tier-2 发现路径 `skill_registry.discover_skills` 给每条 entry 设 `"source": repo_slug`（`skill_registry.py:358`），即每个白名单仓拿到 `owner/repo` 形式的 per-repo source。这是逐仓一等源的现成模板。
- 对照：github-trending 统一设 `source=github-trending`（skill 在 `sync_github_trending.py:434`，plugin 在 `triage_github_trending.py:238` → `sync_plugins_official.py:851`）。
- 活样本：catalog 里 `ComposioHQ/awesome-claude-skills` 这条 source 值就是 per-repo（285 条 entry），说明 per-repo source **已经在生产数据里跑着**，只是没登记进 registry 所以 About 页没显示（但 costrict-web 仍能看到它）。
- 各 plugin marketplace（`claude-plugins-official` 等）也是 per-source id 的成熟先例（`sync_plugins_official.py:86-106` 的 per-source cfg）。

结论：促升不需要发明新机制，等于"把选定的 trending 仓从统一 source 切到 Tier-2 同款 per-repo source"。

---

### 3. 促升机制设计 + 难度 + 去重/迁移

#### 推荐做法（最干净）

**(a) per-repo-source 的 curated seed 清单 + 扫描时设专属 slug**

现状 seed 走 `scripts/trending_seed_repos.json`（`sync_github_trending.py:70` 引用，loader 在 `:221-252`），seed 仓**走 github-trending 同一 triage、最终也被打 `source=github-trending`**（triage 不区分 seed 来源）。

促升要做的是：让被选中的仓在构造 entry 时拿到**自己的 source slug**，而不是 `SOURCE_ID`。两个落点需要支持 per-repo source 覆盖：
- skill：`sync_github_trending.build_skill_entries`（`sync_github_trending.py:402-440`，硬编码 `"source": SOURCE_ID` at `:434`）；
- plugin：triage cfg `"id": sgt.SOURCE_ID`（`triage_github_trending.py:238`）。

最小侵入方案：新增一个 promote 清单（如 `scripts/trending_promoted_repos.json`，结构 `{repo, source_slug, label, type, trust}`），triage 处理候选时若 `full_name` 命中该清单，就用 `source_slug` 覆盖 `SOURCE_ID`（skill 把 `build_skill_entries` 改成接受 `source_id` 参数；plugin 把 cfg 的 `id` 换成该仓的 slug）。

**(b) `source_registry.py` 批量登记展示名**

仅为 About 页显示。在 `SOURCE_REGISTRY`（`source_registry.py:37`）批量加 entry，key **逐字等于** (a) 里设的 `source_slug`，带 `label`（出品方友好名）/`url`（仓库地址）/`type`/`trust`。trust 给 3（自动发现但知名出品方，高于 github-trending 的 2）。

#### 难度评估

- **低-中**。核心改动只有 3 处：promote 清单 loader + triage 里 per-repo source 覆盖 + 批量登记 registry。无 schema 变更，无 dedup 逻辑变更。
- 主要工作量在**迁移已入库旧 entry**（见下）和**写测试**（triage 现有测试覆盖 source 字面值）。

#### 去重 / 衔接 / 迁移注意点（关键）

1. **dedup 不看 `source` 字段，promote 不会引入重复**：`utils.deduplicate`（`utils.py:1348`）的 identity-collapse 按 `skill_identity_key`=（owner, repo, skill_name，全取自 `source_url`，`utils.py:948-976`）、Pass-2 按 `id` + 归一 `source_url`（`utils.py:1476-1490`）。**全程不读 `source`**。所以同一条 skill 不管 `source` 是 `github-trending` 还是 `composiohq/awesome-codex-skills`，identity key 不变 → 不会因 promote 产生双胞胎。
2. **不会触发重新收集**：Stage A 的 `known_repos` 预过滤（`sync_github_trending.py:131-162`）按 `source_url` 反解的 `owner/repo` 去重，也**不看 `source`**。已入库仓促升后仍被 `known_repos` 挡住，不会重抓。
3. **已入库旧 entry 不会自动改 source**：promote 只影响**新构造**的 entry。catalog 里现存 1508 条 `source=github-trending`（其中目标仓占大头，见 §5）**仍是 `github-trending`**，因为 triage 走 `merge_preserve`（`sync_github_trending.py:445-476`）"按 id 去重、已存在就跳过"，**不会覆盖已有 entry 的字段**。→ **必须写一次性迁移脚本**：扫 `catalog/{skills,plugins}/index.json`（及 `catalog/index.json`），把命中 promote 清单的仓的 entry 的 `source` 字段从 `github-trending` 改成对应 slug。由于这些 index.json 是 CI 生成并提交的（CLAUDE.md「注意事项」），迁移脚本改完直接提交即可。
4. **github-trending 与促升源的衔接**：promote 后 github-trending 仍存在（收剩余长尾仓），只是 entry 数下降；promote 的仓从它名下"搬走"。若不跑迁移脚本，会出现"同一仓的旧 entry 挂 github-trending、新 entry 挂专属 slug"的分裂，所以迁移脚本是衔接必需项。
5. **trust 分级一致性**：促升源 trust 给 3，会进 `TIER_META[3]`=Tier 3（`source_registry.py:31`），About 页"信任分级"区块自动归类，无额外工作。

---

### 4. source_registry one-type-per-source 约束

**约束真实存在**：`SOURCE_REGISTRY` 每个 slug 是单 `type` 字段（`source_registry.py:40,43,...`），`build_sources_payload` 用它做 `TYPE_ORDER.index()` 分组排序（`source_registry.py:208`）。github-trending 自己就因此被迫硬归到 `Skills`（注释 `source_registry.py:165-176` 明确说"schema 假设单一 type"）。

**对批量促升的影响**：
- 绝大多数候选是**纯 skill 仓**（单 type，无冲突）——见 §5 types 列。
- 个别仓走 **plugin 路由**会撞约束。实测命中 plugin 的目标仓：`dotnet/skills`（13 条，plugin）、`browserbase/skills`（5 条，plugin）。登记时只能给它一个 `type`（按主体归 `Plugins` 或 `Skills`），和 github-trending 现状同一处理方式——**不阻断**，但 About 页该仓会被归到单一 type 分组里。
- **没有"一个 slug 同时混 skill+plugin"的候选**（实测每个目标仓的 types 集合都是单一值），所以批量登记不会触发 `TYPE_ORDER.index()` 报错，只要给每个仓登记时填对它的主体 type 即可。
- costrict-web 侧无此约束（它读 per-entry `type`，不读 registry）。

---

### 5. 候选促升仓清单

基于本轮 `catalog/index.json` 中 `source=github-trending` 的 1508 条（1470 skill + 38 plugin），按仓聚合 + accept 率（decision 字段）+ 出品方知名度筛选。

| 仓 | entry 数 | accept | review | reject | accept 率 | stars | type | 促升理由 |
|---|---|---|---|---|---|---|---|---|
| `composiohq/awesome-codex-skills` | 565 | 358 | 206 | 1 | 63% | 13.8k | skill | 体量最大、几乎零 reject、ComposioHQ 知名出品方 |
| `thedaviddias/front-end-checklist` | 390 | 238 | 152 | 0 | 61% | 73k | skill | 超高 star、零 reject、知名前端清单 |
| `k-dense-ai/scientific-agent-skills` | 141 | 108 | 33 | 0 | 77% | 28.5k | skill | 高 accept 率、零 reject、MEMORY 里点名 K-Dense |
| `iofficeai/officecli` | 11 | 11 | 0 | 0 | 100% | 7.2k | skill | 全 accept |
| `dimillian/skills` | 16 | 16 | 0 | 0 | 100% | 3.7k | skill | 全 accept、知名作者（Dimillian） |
| `google/skills` | 10 | 8 | 2 | 0 | 80% | 13.8k | skill | 高 accept、Google 出品 |
| `opensensenova/sensenova-skills` | 72 | 46 | 26 | 0 | 64% | 4.6k | skill | 零 reject、商汤出品 |
| `wanshuiyin/auto-claude-code-research-in-sleep` | 78 | 50 | 28 | 0 | 64% | 12.2k | skill | 高 star、零 reject |
| `browserbase/skills` | 5 | 5 | 0 | 0 | 100% | 3.6k | **plugin** | 全 accept、Browserbase 出品（注意 plugin 路由，§4） |

**边缘 / 不建议促升**（accept 率低或 reject 多）：
- `danielmiessler/personal_ai_infrastructure`（68 条，accept 32 / review 33 / reject 3，47%）—— review 偏多。
- `samuraigpt/generative-media-skills`（55 条，accept 3 / review 52，5%）—— 几乎全 review，质量存疑。
- `dotnet/skills`（13 条 plugin，accept 1 / review 10 / reject 2，8%）—— accept 率低 + plugin 撞 type 约束，慎重。
- 大量 1-entry 仓（`safishamsi/graphify` 68k star 但仅 1 条且 review 等）star 高但产出极少，单独促升收益低。

**注意**：任务名里点名的 `mattpocock/skills` **当前不在 catalog**（`trending_seed_repos.json:4` 刚加为 seed，尚未跑过 triage 入库）。它会在下一轮 triage 以 `source=github-trending` 入库；若要促升，应在它入库前就把它加进 promote 清单，这样首次入库即带专属 slug，省去迁移。

---

## Related Specs / Files

| 文件 | 关键行 | 作用 |
|---|---|---|
| `scripts/source_registry.py` | 37-177（registry）/180-233（build_sources_payload）/227-231（未登记 WARNING） | About 页来源展示权威清单 |
| `scripts/build_frontend_data.py` | 218（调用）/83（slim_item 带 source）| sources.json + per-type json 产出 |
| `scripts/sync_github_trending.py` | 95（SOURCE_ID）/434（skill 写 source）/445-476（merge_preserve）/131-162（known_repos） | github-trending Stage A + skill 构造 |
| `scripts/triage_github_trending.py` | 238（plugin cfg id）/267（skill 构造调用） | Stage B/C，写 source 字面值 |
| `scripts/skill_registry.py` | 358（`"source": repo_slug` 先例） | Tier-2 per-repo source 模板 |
| `scripts/sync_plugins_official.py` | 851（`"source": source_cfg["id"]`）/673-681（_build_id） | plugin entry source 来源 |
| `scripts/utils.py` | 1348-1491（deduplicate，不看 source）/948-976（skill_identity_key） | 证明 promote 不影响 dedup |
| `scripts/build_catalog_bundle.py` / `.md` | md:5,20-32,38,111-112 | costrict-web 消费的 bundle 契约（含 index.json，不含 sources.json） |
| `scripts/trending_seed_repos.json` | 4（mattpocock/skills seed） | 手工 seed 清单（promote 清单可参照此结构） |

## Caveats / Not Found

- **costrict-web 是外部仓**：`catalog_ingest_service.go` / `docs/CATALOG_INGEST.md` 不在本仓，无法确认它如何把 raw `source` 字面值渲染成展示名、是否对 source 做白名单。本仓只能保证"promote 后 bundle index.json 里 source 字段变了"，下游怎么展示需查外部仓或其 docs。
- **promote 清单的具体落点未实现**：本研究只描述"哪里硬编码了 github-trending（需改）"，未写代码。`build_skill_entries`/triage cfg 需要小改以支持 per-repo source 覆盖。
- **迁移脚本未存在**：把已入库 1508 条 github-trending entry 里目标仓的 source 改写为专属 slug 的一次性脚本需新写（否则旧 entry 仍挂 github-trending，造成同仓 source 分裂）。
- decision 字段：少量 entry 可能无 decision（本轮数据 none=0，但跨周期可能出现），accept 率以本轮快照为准。
