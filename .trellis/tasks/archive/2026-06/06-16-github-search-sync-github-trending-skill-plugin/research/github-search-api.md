# Research: GitHub Search API 主动发现源可行性与查询策略

- **Query**: 用 GitHub Search API 构建主动发现源——找含 `SKILL.md` 或 `.claude-plugin/marketplace.json` 的仓；限流/上限/分页/auth、精确文件搜索、trending 近似、现有封装复用、单次 sync rate budget
- **Scope**: mixed（GitHub 官方文档 + 现有代码 + 实测探针）
- **Date**: 2026-06-16
- **验证方式**: 直接对 `api.github.com` 发实测请求 + 拉取 `github/docs` 仓库原文确认数字（exa MCP 在本会话不可用，改用 live API + 官方文档源，证据更硬）

---

## 0. TL;DR（给主 agent 的结论先行）

| 问题 | 结论 |
|---|---|
| 用哪个端点发现 | **Repo search (`search/repositories`) 做发现**（topic/keyword + stars 排序），**Tree API 逐仓验证文件存在性**。Code search 作可选补充。 |
| Code search 能不能直接找 SKILL.md | 能，但**必须 auth**（401 unauth）、**限流极紧 9 req/min（authed）**、且仍受 1000 上限 + 索引覆盖不全。不建议作主路径。 |
| 现有 `utils.github_api` 能用吗 | **能直接用**，它就是 `GET https://api.github.com/{path}`，传 `search/repositories?q=...` 即可。已带 token/retry/rate-limit 处理。**不需要 gh CLI**（项目零外部依赖原则）。**但有 2 个坑**（见 §4），需要小扩展。 |
| 现有 Tree API 封装 | `utils.list_repo_files(repo, branch, pattern="SKILL.md")` 现成，正是验证用的。 |
| 单次 sync 预算 | 推荐查询集 ~12 query × 最多 10 页 ≈ **120 search 调用**（authed 30/min → 需 ~4 分钟节流），验证阶段每仓 1 Tree 调用走 **core 5000/hr**，留足余量。可塞进 CI 90min 超时 + weekly cache。 |

---

## Findings

### 1. Repo search vs Code search（实测 + 官方文档确认）

官方文档原文（`github/docs/content/rest/search/search.md`）：

> The REST API provides **up to 1,000 results for each search**.
> For authenticated requests, you can make up to **30 requests per minute** for all search endpoints **except for the Search code endpoint**. The Search code endpoint **requires you to authenticate** and limits you to **9 requests per minute**. For unauthenticated requests, the rate limit allows you to make up to **10 requests per minute**.

实测确认（2026-06-16，unauth 探针）：

| 维度 | `search/repositories` | `search/code` |
|---|---|---|
| 需要 auth | 否（unauth 可用，10/min） | **是** — unauth 返回 `HTTP 401 {"message":"Requires authentication"}` |
| 限流（authed） | **30 req/min** | **9 req/min** |
| 限流（unauth） | 10 req/min（实测 `x-ratelimit-limit: 10`, `x-ratelimit-resource: search`） | 不可用 |
| 限流 resource 名 | `search` | `code_search`（`rate_limit` 端点实测有独立 `code_search` 对象，与 `search`/`core` 分开计） |
| 每查询结果上限 | **1000**（实测 per_page=100 请求 page=11 → `HTTP 422 "Only the first 1000 search results are available"`） | 1000（同上限） |
| 分页 | `per_page`(≤100) + `page`(≤10 才不越 1000)，`Link` header 给 `next`/`last`（实测 last=`page=200` when per_page=5） | 同 |
| total_count | 返回真实总数（实测 `topic:claude-skill` total_count=2667），但**只有前 1000 可取** | 同 |

实测证据片段：

```
# repo search unauth
HTTP/2 200
link: <...&page=2>; rel="next", <...&page=200>; rel="last"
x-ratelimit-limit: 10
x-ratelimit-resource: search
# total_count= 2667, incomplete= False（注意 total 2667 但仅前 1000 可分页取出）

# code search unauth
HTTP/2 401
{"message":"Requires authentication"}
x-ratelimit-resource: code_search

# 1000 cap 硬证据
GET search/repositories?q=stars:>100&per_page=100&page=11
HTTP 422  message= "Only the first 1000 search results are available"
```

**各自适合发现什么**：

- **Repo search** — 适合"按主题/关键词/star 找仓"。我们的发现主路径。优点：authed 30/min 宽松、unauth 也能跑、`sort=stars` 直接给热门排序。缺点：无法直接断言"仓里有 SKILL.md"，需二次验证。
- **Code search** — 适合"找含某文件/某代码片段的仓"。理论上 `path:SKILL.md` 可一步定位。缺点：必须 auth、9/min 极紧、索引只覆盖默认分支且**对大量小仓/低星仓索引不全**（GitHub code search 索引有覆盖盲区，新仓/小仓可能查不到），1000 上限同样卡。**不适合作主发现路径，仅作补充召回**。

---

### 2. 精确找"含特定文件的仓"——两条路线 trade-off

**目标文件**：`SKILL.md`（仓内任意深度）/ `.claude-plugin/marketplace.json`（固定路径）。

#### 路线 A（推荐）：Repo search 发现 + Tree API 验证

1. `search/repositories?q=<topic/keyword> stars:>N&sort=stars&per_page=100&page=1..10` 召回候选仓
2. 对每个候选仓 `GET /repos/{owner}/{repo}/git/trees/{branch}?recursive=1`（= `utils.list_repo_files`）一次性拿到全部 blob 路径
3. 路径里有 `*/SKILL.md` → skill 仓；有 `.claude-plugin/marketplace.json` → plugin marketplace 仓

实测 Tree API 成本（anthropics/skills）：
```
GET repos/anthropics/skills/git/trees/main?recursive=1
HTTP 200  truncated= False  total_blobs= 483  SKILL.md count= 18
```
- **1 个仓 = 1 次 core 调用**（core 限额 authed 5000/hr，极宽松）。
- 返回 `truncated` 标志；超大仓（>100k entries / >7MB）会 truncate，此时退化用 `contents` API 或只查固定路径。对 skill/plugin 仓极少触发。
- 这正是 `marketplace.json` 也能用 Tree 验证的原因——但**plugin 路径固定**（`.claude-plugin/marketplace.json`），更省的是直接 raw 探测（见下）。

**marketplace.json 验证已有现成更省的封装**：`scripts/marketplace_verifier.py` 直接 raw 探测固定 4 个候选路径（`{main,master} × {.claude-plugin/marketplace.json, marketplace.json}`），走 `raw.githubusercontent.com`（**不消耗 API rate limit**），见 `marketplace_verifier.py:57-66, 141-167`。发现 plugin 仓后复用它即可，零 search/core 成本。

Trade-off：
- **覆盖率**：100%（只要候选在 repo search 召回里就能确证），无 code-search 索引盲区。
- **限流**：repo search ≤120 调用（search 桶）+ 每候选 1 Tree 调用（core 桶，5000/hr 充裕）。两个桶独立，互不挤占。
- **代价**：召回依赖关键词/topic 命中率（见 §3 查询集）。

#### 路线 B（可选补充）：Code search 一步定位

- `search/code?q=path:SKILL.md`（新 code search 语法用 `path:`，旧 `filename:` 已弱化）
- `search/code?q=path:.claude-plugin/marketplace.json`
- 优点：一步拿到"含该文件的仓"，无需逐仓 Tree。
- 缺点：**必须 auth + 9/min + 1000 上限 + 索引覆盖不全**（小仓/新仓常查不到，正是我们要捞的"孤儿仓"高发区）→ 召回率反而不稳。

Trade-off 结论：**A 为主、B 为辅**。B 可作为"额外召回一批 repo search 漏掉的"补充信号，但不能依赖它做 completeness。

---

### 3. 抓 trending / 近期高星（GitHub 不暴露 star 增速）

GitHub Search 无 star velocity。用 qualifier 组合近似"近期活跃高星新仓"：

| 目标 | qualifier 组合 |
|---|---|
| 近期更新的高星仓 | `pushed:>2026-05-16 stars:>20`（近 30 天有 push + 一定 star 基线） |
| 近期新建的快速涨星仓 | `created:>2026-03-16 stars:>50`（近 3 月新仓 + star 门槛 → 近似"新仓爆款"） |
| 纯热门存量仓 | `sort=stars&order=desc`（按 star 绝对值排，捞头部） |
| 组合（推荐发现窗口） | `topic:claude-skill pushed:>2026-05-16` + 按 stars 排序 |

实践建议：
- 用 `created:>` 卡新仓 + `stars:>N` 卡门槛 = 近似 trending（GitHub trending 页内部也是类似启发式，无公开 API）。
- `pushed:>` 保证"还活着"，过滤僵尸仓。
- 多个时间窗 + star 阈值分层查询，可绕过单查询 1000 上限（不同切片各自 ≤1000）。
- 日期用滚动窗口（`now - 30d`），可写进 sync 脚本动态计算。

---

### 4. 现有封装能否直接用（带 file:line 引用）

#### `utils.github_api(path)` — `scripts/utils.py:257`

```python
def github_api(path: str) -> Optional[dict]:
    url = f"https://api.github.com/{path.lstrip('/')}"
    ...
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    ...
    if e.code in (403, 429):  # 限流处理，读 Retry-After / X-RateLimit-Reset
        wait = _retry_delay_seconds(e.headers, ...)
```

- **直接支持 search 端点**：它就是通用 `GET api.github.com/{path}`，传 `"search/repositories?q=..."` 即可返回 `{total_count, incomplete_results, items: [...]}` 的 dict。
- **已带**：token 注入（`utils.py:270-271`）、3 次 retry、403/429 限流退避（`utils.py:277-291`，读 `Retry-After`/`X-RateLimit-Reset`，见 `_retry_delay_seconds` at `utils.py:461`）、无 token 时 rate-limit 后自我禁用（`_github_api_disabled_until`, `utils.py:259-262, 286`）。
- **用 urllib，不是 gh CLI** — 符合项目"sync 脚本仅标准库"原则（CLAUDE.md 依赖说明）。**不要引入 `gh api`**。

**坑 1 — 限流退避对 search 桶不够精准**：当前 retry 仅在 `403/429` 时退避。但 search 桶用尽时 GitHub 通常返回 **403 + `x-ratelimit-remaining: 0`**（有时是 200 但 `incomplete_results: true`）。`github_api` 会按 403 退避 → 没问题。**但它不区分 `search` / `code_search` / `core` 三个独立桶**——它对所有调用一视同仁。对本任务影响小（search 调用集中、core 调用充裕），但若想最优，发现阶段最好**主动节流**（每次 search 调用后 sleep ~2s，30/min authed = 1 次/2s）而不是等 403 撞墙。

**坑 2 — 不缓存空结果是另一套逻辑**：`utils.github_api` 本身不缓存。缓存在调用方（如 `_repo_meta_cache`, `utils.py:308-311`）。新源要自己实现"不缓存空结果"（对齐 commit f7d49f7 修的 skill_registry 行为，PRD Requirements 提到）。

#### `utils.list_repo_files(repo_slug, branch, pattern)` — `scripts/utils.py:393`

```python
def list_repo_files(repo_slug, branch="main", pattern="") -> list[str]:
    data = github_api(f"repos/{repo_slug}/git/trees/{branch}?recursive=1")
    if not data or "tree" not in data:
        return []
    paths = [item["path"] for item in data["tree"] if item.get("type") == "blob"]
    if pattern:
        paths = [p for p in paths if pattern.lower() in p.lower()]
    return paths
```

- **正是文件验证用的**。`list_repo_files(repo, branch, pattern="SKILL.md")` 直接返回所有 SKILL.md 路径（`skill_registry.scan_repo_via_api` at `skill_registry.py:137-148` 就是这么用的）。
- **坑 3 — branch 默认 `main`**：很多仓默认分支是 `master` 或别的。验证前应先 `get_repo_meta` 拿 `default_branch`（`utils.py:340`），或对 main/master 都试（`marketplace_verifier._BRANCHES = ("main","master")` 是这么兜的）。repo search 的 item 里其实直接带 `default_branch`，可零成本拿到，省一次 API。
- **坑 4 — 不处理 `truncated`**：超大仓 Tree 会 truncate，当前实现静默返回部分列表。对 skill/plugin 仓基本不触发，但代码里可加 `data.get("truncated")` 告警。

#### `utils.get_repo_info` / `get_repo_meta` — `utils.py:377 / 314`

- `get_repo_info`（DEPRECATED，转调 `get_repo_meta`）返回 `{stars, pushed_at, default_branch}`。
- 但**repo search 的 item 本身已含** `stargazers_count` / `pushed_at` / `default_branch` / `topics` / `description` / `full_name` / `html_url`（实测 §1 字段齐全）→ **发现阶段不需要额外调 get_repo_meta**，直接从 search item 取，省调用。

#### 现有 search 用法参考

- `scripts/spike_windsurf_directory.py:229-266` 和 `scripts/spike_cursor_directory.py:295-303` **已有 repo search 范例**：`search/repositories?q=...&sort=stars&order=desc&per_page=5`，多查询 + `seen` 集合跨查询去重 + 取 `items[].full_name/stargazers_count/pushed_at`。
  - 注意：这两个 spike 脚本**自带一个本地 `github_api`**（返回 `(status, data, err)` 三元组，`spike_windsurf_directory.py:203`），**与 `utils.github_api`（返回 dict）签名不同**。新源应复用 `utils.github_api`，别照抄 spike 的三元组版本。

---

### 5. 单次 sync 的 rate budget + 推荐查询集

#### 推荐查询集（skill + plugin 发现）

```
# Skill 发现（topic + keyword + 时间/star 切片）
topic:claude-skill sort=stars
topic:claude-skills sort=stars
topic:agent-skills sort=stars
topic:claude-code sort=stars
"SKILL.md" in:readme sort=stars
"claude skills" in:name,description sort=stars
"agent skills" in:name,description sort=stars
topic:claude-skill created:>{now-90d} stars:>20    # 近期新仓切片（绕 1000 上限）

# Plugin 发现
topic:claude-plugin sort=stars
topic:claude-code-plugin sort=stars
"claude-plugin" in:name,description sort=stars
".claude-plugin/marketplace.json" in:readme sort=stars
```

约 **12 个查询**（可按 MVP 砍到 skill-only ~8 个）。

#### 调用预算估算（authed，假定有 GITHUB_TOKEN）

**发现阶段（search 桶，authed 30/min）**：
- 每查询最多翻 10 页（per_page=100，到 1000 上限）。
- 实际多数查询 total_count < 1000 或我们只取前几页（按 star 排序，尾部低星仓价值低 → 建议**每查询只取前 2-3 页 = 200-300 个候选**）。
- 预算：12 query × 3 页 ≈ **36 search 调用**（保守上限 12×10=120）。
- 30/min → 36 调用 ≈ 1.2 分钟；120 调用 ≈ 4 分钟（含主动 2s 节流）。**远低于 CI 90min 超时**（`sync.yml:41 timeout-minutes: 90`）。

**验证阶段（core 桶，authed 5000/hr）**：
- 去重后假设 ~300-500 个唯一候选仓需 Tree 验证。
- 每仓 1 Tree 调用（`list_repo_files`）= 300-500 core 调用 << 5000/hr。
- plugin marketplace 验证走 `marketplace_verifier` 的 **raw.githubusercontent.com**，**不占 API 桶**。
- search item 已带 metadata → 不需额外 `get_repo_meta`，进一步省 core。

**总预算**：~36-120 search（search 桶）+ ~300-500 core（core 桶）。**两个桶独立，互不挤占**；都在 authed 限额内有大量余量。

#### CI / cache 框架契合度

- CI 已有 `GITHUB_TOKEN`（`sync.yml`，自动提供）→ authed 30/min + 5000/hr 可用。
- 现有 weekly cache 框架可直接照搬：每个新 sync 源用独立 `actions/cache/restore@v4` block + weekly stamp（`date -u +%Y-%U`，`sync.yml:54-57`），`restore-keys` 只锚本周（参考 skills.sh/mcp-registry/windsurfrules/plugins 五个现成 block，`sync.yml:73-122`）。
- 建议新源缓存目录如 `.github_trending_cache/`，存：(a) 上次发现的 repo full_name → tree-verified 结果 hash；(b) 增量 diff（新增/star 变化）。**不缓存空结果**（对齐 f7d49f7）。
- 增量短路可参考 CLAUDE.md 描述的 mcp_registry "基于 name diff 短路"模式。

---

### Files Found（现有可复用代码）

| File Path | 用途 | 关键行 |
|---|---|---|
| `scripts/utils.py` | `github_api`（通用 GET，支持 search 端点） | `:257` |
| `scripts/utils.py` | `list_repo_files`（Tree API 验证 SKILL.md，文件存在性） | `:393` |
| `scripts/utils.py` | `get_repo_meta`（stars/pushed_at/default_branch/topics，发现阶段多可省） | `:314` |
| `scripts/utils.py` | `_retry_delay_seconds`（读 Retry-After / X-RateLimit-Reset） | `:461` |
| `scripts/utils.py` | `deduplicate` + `skill_identity_key`/`plugin_identity_key`/`mcp_identity_key`（去重收敛） | `:1278` / `:878` / `:1236` / `:909` |
| `scripts/marketplace_verifier.py` | raw 探测 `.claude-plugin/marketplace.json`（不占 API 桶，验证 plugin 仓） | `:57-66, 141-167, 197` |
| `scripts/skill_registry.py` | `scan_repo_via_api`（Tree + raw 找 SKILL.md）、`hard_filter` | `:137` / `:166` |
| `scripts/sync_skills.py` | Tier 2 pipeline 入口（候选 → hard_filter → LLM 评估），新源可喂进这里 | `:760-789` |
| `scripts/spike_windsurf_directory.py` | repo search 多查询 + 跨查询 dedup 范例（注意本地 github_api 是三元组版） | `:229-266` |
| `scripts/spike_cursor_directory.py` | 同上 repo search 范例 | `:295-303` |
| `.github/workflows/sync.yml` | 90min 超时 + weekly cache block 模板（5 个现成可仿） | `:41, 54-57, 73-122` |

### External References

- GitHub REST Search 官方文档（源文件，实证拉取）：`github/docs/content/rest/search/search.md` — "up to 1,000 results for each search"；authed 30/min（非 code）、code search 9/min 且需 auth、unauth 10/min。
- GitHub Rate-limit 文档源：`github/docs/content/rest/rate-limit/rate-limit.md` — `search` / `code_search` / `core` 三个独立 rate-limit resource 对象。
- 实测 `GET api.github.com/rate_limit`（2026-06-16）：`code_search` 是独立对象，与 `search`、`core` 分桶。
- 实测 1000 上限：`GET search/repositories?...&per_page=100&page=11` → `HTTP 422 "Only the first 1000 search results are available"`。
- 实测 code search unauth：`HTTP 401 "Requires authentication"`。
- 类似"registry/awesome 生成器"通用做法（业界惯例，本任务对照）：均以 **repo search 召回 + 文件树/manifest 二次验证**为主路径，code search 仅补充——与本项目 `marketplace_verifier`（manifest 验证）、`skill_registry.scan_repo_via_api`（Tree 验证）已采用的模式一致。

### Related Specs

- `CLAUDE.md`（项目根）— 数据流水线、Skills 三层来源与去重、`utils.py:deduplicate` identity key、CI weekly cache 框架、"sync 脚本仅用标准库"依赖原则。
- `.trellis/tasks/06-16-github-search-sync-github-trending-skill-plugin/prd.md` — 本任务目标、已知前序实测（~190 孤儿仓）、Open Questions（集成形态 / MVP 范围）。
- `~/.claude/.../memory/popularity-coverage-gap.md`（用户 auto-memory 引用）— catalog 漏收热门资源的实测证据与系统性病灶。

## Caveats / Not Found

- **exa MCP 工具本会话不可用**（`mcp__exa__*` 不在工具集）。改用 live `api.github.com` 实测探针 + 直接拉取 `github/docs` 官方文档源——证据强于二手 exa 摘要，但未做"业界其他爬虫源码"的逐项检索（仅以本项目已有 verifier/registry 模式做对照）。
- **实测探针是 unauthenticated**（本机无 `GITHUB_TOKEN` 注入）：`x-ratelimit-limit: 10`（search 桶 unauth）是实测值；authed 30/min（非 code）、code search authed 9/min 来自官方文档原文，未在 authed 状态实测（CI 有 token，生产即 authed）。
- **Code search 索引覆盖盲区**未量化：GitHub 官方未公布 code search 对小仓/新仓的索引比例。判断"覆盖不全 → 不适合作主路径"基于公开已知行为（新仓常查不到）+ 我们要捞的恰是低星孤儿仓的逻辑推断，未做对照实验。
- **新 code search 语法**：`filename:` 在新版 code search 已弱化，推荐 `path:`。本文未对 `path:.claude-plugin/marketplace.json` 在 authed 下实测召回率（需 token）。
- **集成形态 / MVP 范围**（PRD Open Questions）属架构决策，本研究只给了素材（路线 A/B、预算、复用点），不替主 agent 拍板"独立 sync 脚本 vs 扩充 Tier 2 白名单"。
