# Research: GitHub Search 发现源接入 sync 管线的最干净方式

- **Query**: 新的 GitHub Search 发现源接入现有 sync 管线的最干净方式
- **Scope**: internal
- **Date**: 2026-06-16

## Findings

### Files Found

| File Path | Description |
|---|---|
| `scripts/skill_registry.py` | Tier 2 skill 发现核心：`discover_skills()` 喂白名单仓库，产出 candidates |
| `scripts/sync_skills.py` | 消费 candidates → Tier 2 过滤 → 写 `catalog/skills/index.json` |
| `scripts/sync_plugins_official.py` | 官方 marketplace → **覆盖式写** `catalog/plugins/index.json` |
| `scripts/sync_plugins_dev.py` | claude-plugins.dev → **merge-preserve 写** `catalog/plugins/index.json` |
| `scripts/sync_plugins_csc.py` | 第一方 cospowers → merge-preserve 写同一文件 |
| `scripts/merge_index.py` | 合并所有类型 index + curated → `catalog/index.json`，调 `deduplicate()` |
| `scripts/utils.py` | `deduplicate()`、`*_identity_key()`、`source_priority()`、`github_api`、`list_repo_files` |
| `.github/workflows/sync.yml` | 三阶段 CI：sync-data → enrich(matrix) → aggregate |
| `scripts/spike_cursor_directory.py:303` / `spike_windsurf_directory.py:242` | 已有 `search/repositories?q=...&sort=stars` 用法可直接抄 |

---

### 1. 现有数据流追踪（带 file:line）

#### Skill 发现链路

1. **发现** — `skill_registry.py:203 discover_skills(tier1_entries)`：
   - 从远端 `skill_repos.json`（白名单）逐仓扫描（`skill_registry.py:213 fetch_skill_repos()` → `:232` 遍历）。
   - 每仓走增量 cache（`skill_registry.py:248 get_repo_info` 比对 `pushed_at`）→ `scan_repo_via_api()`（`:137`，Tree API + raw fetch SKILL.md）。
   - 对每个 skill 拼 candidate dict（`skill_registry.py:316-348`，含 `id`/`source_url`/`install`/`stars`），过 `hard_filter()`（`:166`，stars≤50 / spam / 与 Tier1 dup 剔除），打 `_keyword_match`（`:354`）。
   - 返回 candidates 列表（**只有 skill**，schema 已是完整 catalog entry）。

2. **消费** — `sync_skills.py:766 candidates = discover_skills(tier1_entries)`：
   - 与 `parse_openclaw_skills()`（`sync_skills.py:773`，同样产 candidate）合并到 `candidates`。
   - 过 `deterministic_tier2_filter()`（`sync_skills.py:727`，score = `log10(stars)*10 + 50*keyword`，取 TOP_N=300，`:724`）。
   - `all_entries = tier1_entries + tier2_entries`（`:792`），过 `is_plugin_source` 过滤（`:799`），**本地** `deduplicate(all_entries)`（`:807`）。
   - 写 `catalog/skills/index.json`（`:809/819 save_index`），带 0 条兜底保留旧索引（`:811-817`）。

3. **合并** — `merge_index.py:732-739`：遍历 `TYPES=["mcp","skills","rules","prompts","plugins"]`（`:58`），`load_index(catalog/skills/index.json)` extend 到 `all_entries`；skills 额外加载 `skills_sh_index.json`（`:745-753`）。最终 `deduplicate(all_entries)`（`:810`）。

#### Plugin 链路

- **有** `catalog/plugins/index.json`（确认存在：`catalog/plugins/{index.json,curated.json}`）。
- `sync_plugins_official.py:79 OUTPUT_PATH = catalog/plugins/index.json`，`main()`（`:921`）**覆盖式** `save_index(all_entries, ...)`（`:997`）。SOURCES 含 official(1000)/superpowers(950)/ECC(900)（`:89-108`）。
- `sync_plugins_dev.py:90 OUTPUT_PATH = 同一文件`，但 **merge-preserve**：`_merge_into_existing()`（`:656`）先 load 现有再追加，按 normalized source_url + id dedup（`:688-703`），`source_priority=700`、`source="claude-plugins-dev"`（`:499/110`）。
- `sync_plugins_csc.py:71 OUTPUT_PATH = 同一文件`，同样 merge-preserve（第一方 6 条）。
- **CI 顺序保证**：official（覆盖）先跑 → dev（merge）→ csc（merge）→ `backfill_plugin_subdirs.py`（`sync.yml:184-219`）。
- 进 merge：`merge_index.py:732` 同一 `TYPES` 循环 `load_index(catalog/plugins/index.json)`，无 sidecar 特判（plugin 无 `*_sub_index`）。

#### Merge 阶段去重位置

- **唯一去重入口**：`merge_index.py:810 deduped = deduplicate(all_entries)`。
- `deduplicate()`（`utils.py:1278`）两遍：
  - **Pass 1 身份折叠**（`:1302-1392`）：按 `_identity_key_for_entry()`（`:1261`）分组，type 路由到 `skill_identity_key`(`:878`)/`mcp_identity_key`(`:909`)/`rule_identity_key`(`:963`)/`plugin_identity_key`(`:1236`)。组内按 `source_priority` 选 winner，merge sibling 字段（`:1379-1390`）。
  - **Pass 2 legacy**（`:1394-1421`）：first-wins by id + normalized source_url（rule/prompt/plugin 跳过 URL dedup，`:1404`）。

---

### 2. 三种候选设计对比（结合真实代码）

#### (a) 动态扩充白名单 — 把发现仓喂进 Tier 2 scan+filter+eval

**做法**：GitHub Search 产出仓库列表，注入到 `skill_registry.fetch_skill_repos()` 返回的 dict（或新增一个 `discover_skills` 之前的合并步骤），让现有 `scan_repo_via_api` + `hard_filter` + `deterministic_tier2_filter` 全程复用。

- **Pros**：
  - 改动最小——只需在 `skill_registry.py:213 fetch_skill_repos()` 返回的 dict 里追加 Search 命中的仓（或新写一个 `discover_search_repos()` 与白名单 merge）。
  - 完全复用增量 cache（`.repo_cache.json`）、`hard_filter`(`skill_registry.py:166`)、TOP_N=300 过滤(`sync_skills.py:739`)、Tier1 dedup、`is_plugin_source` 过滤。
  - candidate schema 自动正确（`scan_repo_via_api` 已产标准 entry，`:316-348`）。
- **Cons**：
  - **只覆盖 skill**——plugin 完全不在 `skill_registry`/`sync_skills` 路径内（plugin 由 `sync_plugins_*.py` 独立产出）。任务要求覆盖 skill+plugin，本方案对 plugin 无解。
  - Search 命中的仓多为"含 SKILL.md 的仓"，对"含 `.claude-plugin/marketplace.json` 的 plugin 仓"无识别逻辑。
  - TOP_N=300 硬截断（`sync_skills.py:724`）会把 Search 新发现挤出，除非调大或单独配额。

#### (b) 独立 `scripts/sync_github_trending.py` — 自发现 + 结构验证 + 写两个 index

**做法**：新脚本用 `search/repositories?q=...&sort=stars`（抄 `spike_cursor_directory.py:303`），对命中仓用 `list_repo_files`(`utils.py:393`) 探 `SKILL.md` / `.claude-plugin/marketplace.json`，分别拼 skill / plugin entry，**merge-preserve** 写 `catalog/skills/index.json` + `catalog/plugins/index.json`，再走现有 merge。

- **Pros**：
  - **skill + plugin 都能覆盖**——单脚本两种结构验证，满足任务全部目标。
  - 与 sync_plugins_dev 同形态（merge-preserve `_merge_into_existing` 模式，`sync_plugins_dev.py:656`），不破坏 official 覆盖式写（只要排在 official 之后）。
  - 隔离失败：和现有 sync step 一样 `continue-on-error`。
  - 可复用 `utils.py` 全部工具：`github_api`(`:257`)、`list_repo_files`(`:393`)、`fetch_raw_content`(`:418`)、`categorize`、`extract_tags`、`to_kebab_case`、`save_index`、`load_index`。
- **Cons**：
  - **要自己拼 entry schema**——skill 侧可抄 `sync_skills.py` 的 candidate dict（`:322-348`），plugin 侧 entry 远比 skill 复杂（`sync_plugins_official.py:775-806`：`install.marketplace_repo`/`marketplace_name`/`marketplace_verified`/`bundle`/`manifest_completeness`）。plugin entry 缺 `marketplace_repo`/`marketplace_verified` 会被 `merge_index.py:818-839` 直接 drop。
  - plugin 验证需复用 `marketplace_verifier.verify_marketplace`（`sync_plugins_official.py:769`）和 `PluginContentFetcher.detect_plugin_layout`（`:438`），否则 bundle/verified 全空。
  - skill 侧不会自动走 Tier 2 的 `hard_filter`/TOP_N（除非手动调用），需自己定质量门槛。

#### (c) Tier 2 候选注入 — 在 `deterministic_tier2_filter` 之前注入候选池

**做法**：在 `sync_skills.py:781` 之前（`candidates` 已 = registry + openclaw），把 Search 发现的 skill candidate append 进去，再统一过 `deterministic_tier2_filter`（`:783`）。

- **Pros**：
  - 比 (a) 更精准的注入点——直接进 candidate 池，复用 score+TOP_N 排序（与 openclaw 注入完全同构，`sync_skills.py:773-775`）。
  - Search candidate 与 registry/openclaw 一视同仁竞争 TOP 300。
- **Cons**：
  - 仍**只覆盖 skill**（同 (a) 的根本限制）。
  - candidate 必须已是完整 entry + `_keyword_match` 标记（`sync_skills.py:735`），即注入前要自己跑等价 `scan_repo_via_api`+`hard_filter`，相当于在 (a) 之上再加一层。
  - TOP_N=300 截断对 Search 新仓不友好。

---

### 3. 预过滤位置（identity key 对照现有 catalog）

**两层防线已存在，但语义不同**：

- **merge 阶段 `deduplicate()` 是最终兜底**（`utils.py:1278`）——任何重复（同仓 skill / 同 `(marketplace_repo, plugin_name)` plugin）都会被 Pass1 身份折叠 / Pass2 id+url dedup 收掉。**正确性上靠它就够**，新源即便完全不预过滤也不会产生重复入库。
- **但发现阶段应该预过滤以省 API/LLM**：
  - skill 路径已有 `discover_skills` 内的 Tier1 dedup（`skill_registry.py:189` `source_url in tier1_urls or skill_id in tier1_ids`）——但**只对照 Tier1，不对照整个 `catalog/index.json`**。
  - plugin 路径 `sync_plugins_dev.py:656 _merge_into_existing()` 读现有 `catalog/plugins/index.json` 做 url+id 预过滤（`:688-703`），并 `_prune_existing_plugin_source_entries`（`:716`）清理过期行——**这是发现阶段读现有条目预过滤的现成范本**。

**推荐**：新发现源应在**发现阶段读现有 `catalog/skills/index.json` + `catalog/plugins/index.json`**，用与 merge 同款 identity key 预过滤：
  - skill 用 `utils.skill_identity_key`（`:878`，`(owner, repo, skill_name)`）。
  - plugin 用 `utils.plugin_identity_key`（`:1236`，`(marketplace_repo, plugin_name)`，依赖 `install.marketplace_repo`/`plugin_name`）。
  
  命中现有条目则**跳过 SKILL.md/marketplace.json 的 raw fetch 与后续 enrich**（省最贵的 API + LLM）。merge 阶段 `deduplicate()` 仍作正确性兜底。注意 identity key 复用现有函数 = 预过滤与 merge 折叠语义一致，不会出现"预过滤放行但 merge 折叠丢弃"的浪费，也不会"预过滤误杀本应保留的高优先级源"。

---

### 4. CI 集成（`.github/workflows/sync.yml`）

- **插入位置**：`sync-data` job 内，**所有 plugin sync 之后、`backfill_plugin_subdirs` 之前**。即在 `:206 Sync Plugins (csc-plugins)` 之后、`:213 Backfill monorepo plugin subdirs` 之前。
  - 理由：若新源写 `catalog/plugins/index.json`，必须排在 official 覆盖式写（`:184`）之后，否则被覆盖；与 dev/csc 同为 merge-preserve，串在最后最安全。skill 侧写 `catalog/skills/index.json` 同理排在 `:161 Sync Skills` 之后即可（实际放最后统一）。
- **step 形态**（抄 `sync.yml:184-190` official 块）：
  ```yaml
  - name: Sync GitHub trending (skills + plugins)
    env:
      GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
      PYTHONUNBUFFERED: "1"
    run: python -u scripts/sync_github_trending.py
    timeout-minutes: 15
    continue-on-error: true
  ```
- **cache block**：新增独立 weekly cache（抄 `sync.yml:104-122` plugins-official/dev 两套 restore + `:289-303` save 两套）：
  - restore：`key: github-trending-cache-${{ steps.week.outputs.stamp }}-${{ github.run_number }}`，`restore-keys: github-trending-cache-${{ steps.week.outputs.stamp }}-`（**仅本周 stamp 前缀、不跨周回退**，与 skills.sh/mcp-registry 一致，见 `sync.yml:73/81-82` 注释）。
  - path：`.github_trending_cache/`（存 Search 结果分页 + repo `pushed_at` 增量 cache，模式同 `skill_registry.py:51 load_repo_cache` 的 `.repo_cache.json`）。
  - save：`if: always() && steps.cache-restore-github-trending.outputs.cache-hit != 'true'`（抄 `:290-291`）。
- **verify**：`sync.yml:221-234 Verify sync` 只校验 mcp/skills/rules/prompts 非空，新源失败不影响该门槛（且 `continue-on-error`）。

---

### 5. 推荐设计 + 理由

**推荐 (b) 独立 `scripts/sync_github_trending.py`，并采用混合实现**：

1. **plugin 侧**：直接复用 `sync_plugins_official.py` 的 entry 构造器——`_entry_from_plugin()`（`:629`）已封装 `marketplace_verifier.verify_marketplace`(`:769`) + `_build_bundle_from_layout`(`:699`) + 全部必填 install 字段。新脚本对 Search 命中的"含 `.claude-plugin/marketplace.json` 的仓"，把它当一个临时 SOURCES 项喂给 `sync_one_source()`（`:813`），再 `_merge_into_existing`（抄 `sync_plugins_dev.py:656`）写回 `catalog/plugins/index.json`。**避免重写复杂 plugin schema 这个最大 Con**。

2. **skill 侧**：复用 `skill_registry.scan_repo_via_api()`（`:137`，已产标准 candidate）+ `hard_filter`（`:166`），对 Search 命中的"含 SKILL.md 的仓"扫描，merge-preserve 写 `catalog/skills/index.json`。

3. **预过滤**：发现阶段读现有 `catalog/{skills,plugins}/index.json`，用 `utils.skill_identity_key`(`:878`) / `utils.plugin_identity_key`(`:1236`) 命中即跳过，省 API/LLM；merge 阶段 `deduplicate()`(`:810`) 兜底正确性。

**理由**：
- **唯一能同时覆盖 skill + plugin 的方案**（(a)/(c) 结构上只触达 skill，因 plugin 不经 `sync_skills`/`skill_registry`）。
- 通过**复用 official 的 `_entry_from_plugin` 和 registry 的 `scan_repo_via_api`**，把 (b) 的"自己拼 schema" Con 几乎消除——不重写 entry 构造，只新增"Search 发现 + 路由到已有构造器"这一薄层。
- merge-preserve 写法与 dev/csc 完全同构（`sync_plugins_dev.py:656`），不破坏 official 覆盖式写，CI 串接位置清晰（official→dev→csc→trending→backfill）。
- merge 的 `deduplicate()` 身份折叠（`utils.py:1302`）天然处理与现有源的重复，新源无需自己实现跨源 dedup，只需在发现阶段用同款 identity key 做省钱预过滤。

---

## Caveats / Not Found

- **当前代码库无生产级 GitHub Search API 调用**：仅 `spike_cursor_directory.py:303` / `spike_windsurf_directory.py:242` 两个 spike 脚本用了 `search/repositories?q=...&sort=stars&order=desc`，可作 query 写法参考，但它们用各自局部的 `github_api`（返回 `(status, data, err)` 三元组），与 `utils.py:257 github_api`（返回 `Optional[dict]`）签名不同——新脚本应统一用 `utils.github_api`。
- **GitHub Search API 限制未在代码中处理**：Search 端点 rate limit 比常规 API 严（authenticated 30 req/min），且单 query 最多返回 1000 条结果（10 页×100）。新脚本需自己做分页 + 限流退避，现有 `utils.github_api` 未内建 Search 专用退避。
- **plugin entry 的 `_build_bundle_from_layout` 依赖 `PluginContentFetcher`**（`sync_plugins_official.py:68`，来自 pip install -e 的 ai-resource-eval 包），CI 已安装（`sync.yml:52`），本地需 `pip install -e ai-resource-eval`。
- **TOP_N=300 截断**（`sync_skills.py:724`）只作用于经 `deterministic_tier2_filter` 的 candidate 池；若推荐方案 (b) skill 侧绕过该函数直接 merge-preserve 写 index，则不受 300 限制，但也失去该质量排序——需自行决定是否复用 `deterministic_tier2_filter` 作质量门槛。
