# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

Everything AI Coding — 聚合 4000+ 精选 MCP / Skills / Rules / Prompts / Plugins 的开发资源索引。数据从 11+ 个上游源自动同步，支持 Claude Code、Opencode、Costrict、VSCode Costrict 四个平台。

## 提交规范

原子化提交，格式：`[type] 中文描述`

类型：`[feat]` `[fix]` `[refactor]` `[docs]` `[ci]` `[chore]`

规则：
- 每个提交只做一件事
- 描述用中文，简洁直白
- 不写 Co-Authored-By（除非协作场景）

## 测试

```bash
# 运行所有测试
python -m pytest tests/ -v

# 运行特定测试文件
python -m pytest tests/test_merge_index.py -v
python -m pytest tests/test_eval_bridge.py -v
python -m pytest tests/test_scoring_governor.py -v
```

## 开发命令

### 同步数据

```bash
# 同步各类型资源（需要 GITHUB_TOKEN 避免 rate limit）
GITHUB_TOKEN=xxx python scripts/sync_mcp.py
GITHUB_TOKEN=xxx python scripts/sync_mcp_registry.py # 接入 registry.modelcontextprotocol.io（active+isLatest，无需 token）
GITHUB_TOKEN=xxx python scripts/sync_rules.py
GITHUB_TOKEN=xxx python scripts/sync_windsurfrules.py # 接入 awesome-windsurfrules ×2 仓库（cross-repo dedup）
GITHUB_TOKEN=xxx python scripts/sync_skills.py    # Tier 2 评估需要 LLM_* 环境变量
GITHUB_TOKEN=xxx python scripts/sync_skills_sh.py # 接入 skills.sh（mastra JSON 主路径，install_count ≥ 1000）
GITHUB_TOKEN=xxx python scripts/sync_prompts.py

# 增量抓取 mcp.so（避免全量重抓）
python scripts/crawl_mcp_so.py --mode incremental

# 合并索引（包含去重、富化、评分、生命周期管理）
python scripts/merge_index.py

# 更新 README 中的资源统计数字（中英文 README 会同时更新）
python scripts/update_readme.py
```

### 评估引擎

```bash
# 安装本地评估包（首次 / 更新后）
pip install -e ai-resource-eval

# 用 CLI 直接跑全量评估（独立于 merge 管线）
ai-resource-eval run \
  --task all \
  --input catalog/index.json \
  --output .eval_cache/results.json \
  --judge openai_compat \
  --cache-dir .eval_cache \
  --concurrency 5 \
  --incremental \
  --no-interactive \
  --on-fail queue

# 环境变量：LLM_API_KEY / LLM_BASE_URL / LLM_MODEL（或 JUDGE_ 前缀）
```

### 本地验证

```bash
# 验证 JSON schema
python -c "import json; json.load(open('catalog/index.json'))"

# 检查索引完整性
python scripts/merge_index.py  # 会输出去重统计和完整性警告
```

**依赖说明**：sync 脚本仅用标准库（urllib、json）。评估引擎需要 `pip install -e ai-resource-eval`（pydantic、httpx）。CI 中自动安装。

## 架构

### 数据流水线

```
上游源 (9个 GitHub 仓库 + mcp.so)
    ↓  scripts/sync_*.py（解析 README/API/CSV，写入各类型 index.json）
catalog/{mcp,skills,rules,prompts}/index.json  ← 各类型索引（CI 生成）
    + catalog/*/curated.json                    ← 手工精选（手动维护）
    ↓  scripts/merge_index.py（去重 → 富化 → 评分 → 生命周期）
catalog/index.json                              ← 最终索引（CI 提交）
    ↓  scripts/update_readme.py
README.md + README.zh-CN.md                    ← 自动更新统计与精选区块
```

**关键流程**：
- `sync_*.py` — 从上游抓取，写入 `catalog/{type}/index.json`
- `merge_index.py` — 调用 `enrichment_orchestrator.py`（评估+富化）→ `scoring_governor.py`（reject 过滤）→ `catalog_lifecycle.py`（生命周期字段 + 增量复抓候选）
- `eval_bridge.py` — 胶水层：按资源类型分组，调用 ai-resource-eval harness，将评分 + enrichment 字段映射回 catalog entry，转换 health 格式

### 评分引擎（ai-resource-eval）

嵌入在 `ai-resource-eval/` 的独立评估包（同时有独立 GitHub 仓库 `papysans/ai-resource-eval`，两边各自演化）。

**评分+富化流程**：抓取 README → 单次 LLM 调用产出 6 维评分 + enrichment 字段（summary, summary_zh, tags, tech_stack, search_terms, highlights）→ health 信号 → final_score 混合 → decision 判定

**6 个 LLM 维度**：coding_relevance, doc_completeness, desc_accuracy, writing_quality, specificity, install_clarity

**Enrichment 字段**：summary（英文）, summary_zh（中文）, tags, tech_stack, search_terms, highlights — 通过 `enrichment: true` task config 控制

**3 个 health 信号**：freshness, popularity, source_trust

**附加信号**：`install_popularity` —— 仅 skills.sh 派生条目可计算（含 `install_count > 0`），公式 `min(100, log10(max(install_count, 1)) / log10(100000) * 100)`。默认权重 `0.05`（让真实使用量高的 entry 在 health_score 中获得轻微加分救场，避免 LLM 误 reject），通过环境变量 `HEALTH_W_INSTALL_POPULARITY` 可覆盖。其他源 entry 走 `excluded_signals` 路径自动剔除该信号、原 freshness/popularity/source_trust 按比例分回，结果与权重 0 时等价。`rubric_version` 已从 `1` bump 到 `2`，强制旧 cache 失效。

**MCP entry 增量字段**（`add-tier1-rules-mcp-sources` change 引入）：
- `mcp_registry_status` — `active` / `inactive` / `deprecated`，来自 registry.modelcontextprotocol.io 的 `_meta.io.modelcontextprotocol.registry/official.status`
- `mcp_registry_published_at` — registry 端发布时间，用于 freshness 计算
- `mcp_remotes` — array of `{type, url}`，远端可托管 MCP 的访问端点

**增量评估短路**：mcp_registry 派生 entry 基于 registry name diff（added / status_changed / version_bumped / removed）短路；windsurfrules 派生 entry 当前保守不短路（无稳定 diff 来源），等内容稳定后再启用。复用 skills.sh 同款 stable + cache 命中逻辑，详见 `scripts/eval_bridge.py`。

**混合公式**：`final_score = llm_score × 0.85 + health_score × 0.15`

**4 种 task 配置**（内置于包内）：mcp_server, skill, rule, prompt — 各有不同的维度权重和 accept/review 阈值，均默认 `enrichment: true`

**缓存**：SQLite（`.eval_cache/`），基于 content_hash + rubric_version，增量评估只评新增/变更条目

**Security 评估 task**（`add-security-risk-eval` change 引入）：与 6 维质量评分**完全解耦**的独立 LLM 通道，由 `security_scan` task 配置驱动（`ai-resource-eval/ai_resource_eval/tasks/security_scan.yaml`）。
- **输出 6 字段**：`risk_level`（clean / low / medium / high / extreme）、`verdict`（safe / caution / reject）、`red_flags`、`permissions`（files / network / commands）、`summary`、`recommendations`；语义对齐 costrict-web `SecurityScan` 模型，去掉 `category` 与 `builtin_tags`。`verdict` 与 `risk_level` 有强约束映射（clean/low→safe、medium→caution、high/extreme→reject），不匹配视为评估失败。
- **独立 `rubric_major_version`**：security prompt 演进与质量评分 rubric 互相不失效 cache。当前 `rubric_major_version: 1`。
- **独立 cache namespace**：`EvalCache.make_key(namespace="security")` 把 security cache row 与质量评分 row 隔离开（同一 SQLite 文件，无新增 cache key 需要）。
- **MCP 类型特殊处理**：`eval_bridge.security_scan_and_map` 为 type=mcp 的 entry 序列化 `install.config` 作合成 content，不走远端 fetcher；其他类型复用 GitHubFetcher / PluginContentFetcher 已拉取的内容。
- **失败兜底**：LLM 调用失败、JSON 解析失败、verdict↔risk_level 校验失败 → entry 不写 `security` 字段，下个周期重试（不引入 status/error 占位）。
- **管线插入位置**：`enrichment_orchestrator.enrich_entries` 在质量评分之后调用 `eval_bridge.security_scan_and_map`，CI 中由 aggregate job 的 "Run security scan" step 触发（独立 `security-eval-cache-...` cache）。
- **开关**：环境变量 `SECURITY_SCAN_ENABLED`（默认 true）控制执行；workflow_dispatch 提供 `security_scan_enabled` 手动开关。

### MCP 上游源

- [wong2/awesome-mcp-servers](https://github.com/wong2/awesome-mcp-servers) — 社区 awesome list（README 解析）
- [yzfly/Awesome-MCP-ZH](https://github.com/yzfly/Awesome-MCP-ZH) — 中文 awesome list
- [mcp.so](https://mcp.so) — 第三方 MCP 目录（增量爬取，`scripts/crawl_mcp_so.py`）
- **[registry.modelcontextprotocol.io](https://registry.modelcontextprotocol.io)** — MCP 官方 registry，`scripts/sync_mcp_registry.py` 拉取 v0/servers，仅保留 `active` + `isLatest`，约 7,500 条；source_priority 为 `900`，与 wong2 等 GitHub URL 源走严格匹配 dedup（`io.github.<owner>/<repo>` 反向 DNS → `('github', owner/repo)`，其他 reverse-DNS 独立 key，**不做 owner-only fuzzy match**，详见 `utils.py:mcp_identity_key()`）

### Rules 上游源

- [PatrickJS/awesome-cursorrules](https://github.com/PatrickJS/awesome-cursorrules) — Cursor rules awesome list
- [Mr-chen-05/rules-2.1-optimized](https://github.com/Mr-chen-05/rules-2.1-optimized) — 中文优化 rules
- **[SchneiderSam/awesome-windsurfrules](https://github.com/SchneiderSam/awesome-windsurfrules) + [balqaasem/awesome-windsurfrules](https://github.com/balqaasem/awesome-windsurfrules)** — Windsurf rules 双仓库镜像，`scripts/sync_windsurfrules.py` 递归遍历 `rules/` 目录拉取 `.md`；约 108 唯一 slug（cross-repo dedup 后 SchneiderSam 优先）；`global_rules/<slug>/global_rules.md` 加 tag `windsurf-global` + category `global`；source_priority 为 `500`

### Skills 三层来源与去重

- **Tier 1**（最高优先级）: anthropics/skills + Ai-Agent-Skills + antigravity-awesome-skills + vasilyu1983/ai-agents-public + skills.sh（全量收录，非技术类过滤）
  - skills.sh 通过 mastra-ai/skills-api 维护的 `scraped-skills.json` 静态文件间接拉取（主路径，零 rate limit，每日刷新），脚本为 `scripts/sync_skills_sh.py`，输出到 `catalog/skills/skills_sh_index.json`
  - 阈值 `install_count ≥ 1000`（环境变量 `SKILLS_SH_MIN_INSTALLS` 可调），随条目附带 `install_count` / `skills_sh_url` / `skills_sh_scraped_at` 字段
  - 备用降级到 skills.sh 隐藏 API（探针发现端点 404，当前为 stub）
  - 注：sickn33/antigravity-awesome-skills 镜像已 collapse 到 anthropics/skills 直接源（canonical 收敛）
- **Tier 2**: GitHub 搜索 + awesome-openclaw-skills → LLM 评估（TOP 300）
- **Tier 3**（最低优先级）: `catalog/skills/curated.json` 手工精选

**去重逻辑**（`utils.py:deduplicate()`）：
1. 按 `source_url` 去重（先入为主，Tier 1 优先保留）
2. 按 `id` 去重（同一 ID 只保留第一个）
3. 结果：Tier 1 > Tier 2 > Tier 3

### Plugins 上游源

Plugins 是 Claude Code 的 marketplace 打包格式（一个 plugin 通常捆绑 skills + commands + agents + MCP servers），由 `add-plugins-category` change 引入。

- **[anthropics/claude-plugins-official](https://github.com/anthropics/claude-plugins-official)** — 官方 marketplace，解析仓库根 `marketplace.json`；`source_priority` 为 `1000`（最高），`scripts/sync_plugins_official.py`；`superpowers` 等同名 plugin 以此源为 canonical（obra 镜像通过黑名单移除，避免双胞胎）
- **[obra/superpowers-marketplace](https://github.com/obra/superpowers-marketplace)** — Jesse Vincent 的社区 marketplace，同样解析 `marketplace.json`；`source_priority` 为 `950`，`scripts/sync_plugins_superpowers.py`；与官方源同名 plugin（如 `superpowers`）走精确黑名单收敛
- **[claude-plugins.dev](https://claude-plugins.dev)** — 公共 registry API（约 32k plugins），脚本 `scripts/sync_plugins_registry.py` 拉取后按 `stars ≥ 5` 过滤；`source_priority` 为 `700`

**任务配置**（`ai-resource-eval` 包内 `plugin` task，配置见 `ai-resource-eval/ai_resource_eval/tasks/plugin.yaml`）：**v2 起已激活 5 维 LLM 评分**（`coding_relevance` / `doc_completeness` / `desc_accuracy` / `writing_quality` / `specificity`，剔除了 skill 的 `install_clarity`，其 0.10 权重并入 `doc_completeness`），由 `PluginContentFetcher` 抓全 plugin 内容（plugin.json + 全部 SKILL.md / agents / commands）作为 LLM 输入。`health_blend_alpha: 0.85`（与 skill 对齐），accept/review 阈值 65/50，`rubric_major_version: 2`。健康度信号 4 个 — `freshness` / `popularity` / `source_trust` / `manifest_completeness`，`enrichment: true` 仍生效（summary / tags / tech_stack）。（旧文档曾写"plugin task 关闭 LLM 评分（health-only）"，v2 已不再如此。）

**Marketplace 字段**（`fix-plugin-marketplace-fields` change 引入）：plugin entry 的 `install` 对象在 `plugin_name` / `marketplace`（display-only）之外新增 3 个必填字段：
- `install.marketplace_repo` — 规范的 GitHub `owner/repo` 字符串。official 源直接取自 `repo_slug`；dev 源从 `gitUrl` / `source_url` 反推
- `install.marketplace_name` — 上游 `marketplace.json::name` 的值，必须匹配 `^[A-Za-z0-9._-]+$`；用作 `enabledPlugins["<plugin_name>@<marketplace_name>"]` 的后缀。manifest 缺 `name` 字段时为 `null`
- `install.marketplace_verified` — bool。`true` 当且仅当 marketplace.json 可达、含合法 `name`、且 `plugin_name` 真在 `plugins[]` 数组里。`false` 时 install 命令拒绝，前端 Detail 显示 unverified banner、ResourceCard 显示 "unverified" 角标

sync 时通过 `scripts/marketplace_verifier.py` 统一 fetch + cache，每次 sync 约 96 个 unique repo 的 marketplace.json，缓存写入 `.plugins_*_cache/marketplace_manifests.json`（随现有 weekly cache block 持久化）。

**去重**：
- **硬剔除**（sync 阶段）：`scripts/plugin_sources.json` 黑名单跳过已知冗余源。除 `repos: []` 数组（按整仓库屏蔽）外，还支持 `plugins: [{source, plugin_name}]` 数组，按 (source, plugin_name) 做精确二元黑名单（如 `obra-superpowers + superpowers` 被收敛到官方源）
- **identity-collapse**（merge 阶段，`fix-plugin-marketplace-fields` 引入）：`utils.plugin_identity_key` 返回 `("plugin", marketplace_repo, plugin_name)` 三元组，dev 源中 ~171 条与 official 撞键的 entry 被合并到 official 一侧；丢弃时通过 `_merge_plugin_enrichment_fields` 把 dev 的 `tags` / `tech_stack` / `highlights` / `description_zh` / `summary` / `summary_zh` overlay 进保留的 entry
- **schema 校验**（`merge_index.py`）：plugin entry 缺 `install.marketplace_repo` 或 `install.marketplace_verified` → 直接 drop 并 WARN
- **软标注**（merge 阶段）：`merge_index._apply_bundled_in_annotations` 在 plugin entry 上标注它捆绑了哪些 skill/command/agent/mcp（`bundled_in` 字段写到 skill/command/agent/mcp 侧），同时**反向写回** plugin entry 的 `bundle.bundled_skill_ids` 等数组，前端 Detail 页用该反向映射渲染可点跳转的 chip
- **search-index 透传**：`bundled_in` 字段被加进 `search-index.json`，避免列表页 fallback 渲染时丢失 plugin 归属角标；plugin entry 额外带一个最小 `install: {marketplace_verified}` 子对象，让 ResourceCard 在 list view 不依赖 per-entry JSON 即可渲染 unverified 角标
- **前端兜底**：`Detail.tsx` 增加 search-index fallback，即便 entry 在 split 后的单条 JSON 缺失也能从 search-index 还原最小卡片，修了 bundled skill 直链 404 的 bug

**平台兼容性**：主要面向 **Claude Code**；**opencode** 部分兼容（npm 包形式）；**cursor / windsurf / costrict 暂无等价 plugin 机制**，安装命令侧仅 Claude Code 路径生效。

### 主动发现源（GitHub Search）

`scripts/sync_github_trending.py` —— 唯一**主动发现**源（其余源都是被动等上游 curated 白名单/registry 收录）。补"发现盲区"：~190 个高星热门 skill 仓不在任何现有源里。

- **发现**：`utils.github_api` 跑一组 repo search 查询（topic/keyword + `created:>` trending 切片），`sort=stars`，主动 2s 节流避开 search 桶（authed 30/min、1000 条/查询上限）。**不引入 gh CLI**（标准库原则）。
- **结构验证定 type**：对候选仓**一次 Tree API** 调用，含 `.claude-plugin/marketplace.json` → plugin（优先，bundled skill 交下游合成）；含 `SKILL.md` → skill；都没有 → 丢弃（天然剔除 cherry-studio/cliproxyapi 这类越界工具，比描述正则准）。
- **去重主防线 = repo 级 `known_repos` 预过滤**（`build_known_repos`）：扫描/LLM **之前**就挡掉"已存在于任意 type/source 的仓"。关键——`deduplicate()` 按 `type` 分命名空间，**跨类型抓不住**（一个仓已作 plugin 在库，再被当 skill 发现会重复）；实测 301 候选中 60 已在库、含 37 个跨类型地雷。known_repos **双路提取** owner/repo：`source_url` 反解 + `install.marketplace_repo`（覆盖 marketplace 容器仓无自指 source_url 的盲区）+ 镜像归一。merge 阶段 `deduplicate()` 仅兜底。
- **复用**：skill 走 `skill_registry.scan_repo_via_api` + `hard_filter`；plugin 走 `sync_plugins_official.sync_one_source`（`_entry_from_plugin`），避免重写 plugin schema。**merge-preserve** 写 `catalog/{skills,plugins}/index.json`（plugin 侧 id-only dedup，同 monorepo 多 plugin 合法共享 URL）。
- **增量友好 + 失败可见**：`.github_trending_cache/verify_cache.json` 按 `pushed_at` 缓存结构验证结果、**不缓存空结果**；末尾 WARN 汇总发现健康度（skill/plugin 仓数、丢弃、预过滤命中）。`source_priority=600`（低于 official/dev，碰撞时既有源胜出）。
- **覆盖**：skill + plugin（MVP）。star velocity / trending 时间序列信号留待后续。

### 多平台适配

`platforms/` 下四套内容，差异仅在文件命名、frontmatter、命令引用格式：

| 平台 | 命令分隔符 | 命令路径 |
|------|-----------|---------|
| claude-code | `:` | `commands/eac/{cmd}.md` |
| opencode | `-` | `command/eac-{cmd}.md` |
| costrict | `-` | `commands/eac/eac-{cmd}.md` |
| vscode-costrict | `-` | `commands/eac/eac-{cmd}.md` |

修改 skill 内容时需同步四个平台文件。

### 脚本模块依赖关系

```
merge_index.py
  ├── utils.py                    (公共工具：load_index, save_index, deduplicate, categorize, extract_tags)
  ├── enrichment_orchestrator.py  (调度：仅调用 eval_bridge)
  │   └── eval_bridge.py          (评估+富化 → ai-resource-eval 本地包)
  ├── scoring_governor.py         (reject 过滤 + dry-run 控制)
  └── catalog_lifecycle.py        (生命周期: added_at, 增量复抓候选)
```

## CI

`.github/workflows/sync.yml` — 每周一 UTC 3:23 自动触发，也支持 `workflow_dispatch` 手动触发。

**流程**：crawl_mcp_so → sync_mcp → sync_mcp_registry → sync_rules → sync_windsurfrules → sync_skills → sync_skills_sh → sync_prompts → sync_plugins(official→dev→csc) → **sync_github_trending** → backfill_plugin_subdirs → verify_sync → merge_index → update_readme → audit_popular_coverage → auto commit+push

**缓存**：CI 通过 `actions/cache` 持久化 `.llm_cache.json`、`.eval_cache/`（SQLite）、`incremental_recrawl_state.json`、`fallback_skill_repos.json` 等文件避免重复计算；`.skills_sh_cache/` / `.mcp_registry_cache/` / `.windsurfrules_cache/` 各自使用独立 weekly cache block，`restore-keys` 仅锚定本周 stamp，不跨周回退。

**环境变量**：
- `GITHUB_TOKEN`（自动提供）
- `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`（评估引擎用，可选 — 无 key 则跳过评估）
- `EVAL_DRY_RUN`（默认 `true`，reject 条目仅标记不删除）
- `EVAL_INCREMENTAL`（CI 中硬编码 `true`，防止意外全量评估）
- `SKILLS_SH_MIN_INSTALLS`（默认 `1000`，调节 skills.sh 阈值）
- `HEALTH_W_INSTALL_POPULARITY`（默认 `0.05`，调整 install_popularity 在 health_score 中的权重；0 等价于禁用）

## Evo 命令（客户端质量演化）

`/eac:evo <id>` 对用户**本机已安装**的 skill / prompt / rule 做靶向质量改进。与 catalog 入库评分管线（`ai-resource-eval` 的 6 维）**架构分离、互不干扰**。

**双 rubric 架构**：

| 管线 | 位置 | Rubric | 触发 | 落点 |
|------|------|--------|------|------|
| Catalog 入库 | 服务端，CI | 6 维：coding_relevance / doc_completeness / desc_accuracy / writing_quality / specificity / install_clarity | 每周 cron + workflow_dispatch | per-entry API 的 `decision` / `weak_dims` |
| Evo 质量演化 | 客户端，按需 | Skill 7 维 / Prompt+Rule 4 维（详见 `docs/wiki/evo-rubric.md`） | 用户 `/evo <id>` 或 install 后 weak_dims 非空时提示 | 用户本机副本 + `~/.claude/.evo/<id>/history.json` |

**Evo Rubric 维度**（改编自 [darwin-skill](https://github.com/alchaincyf/darwin-skill)，MIT License © 花叔）：

- **Skill（7 维 + 静态 lint）**：D1 Frontmatter.description 质量（10）/ D2 工作流清晰度（20）/ D3 指令具体性（20）/ D4 边界条件覆盖（15）/ D5 检查点设计（10）/ D6 资源整合度（5）/ D7 整体架构（20）
- **Prompt / Rule（4 维）**：D2（31）/ D3（31）/ D6（8）/ D7（30），权重归一到 100
- **静态 lint（0 token 预检）**：frontmatter 字段完整性 + markdown 合法性，lint 不过先修再评

**本机数据落盘**：

```
~/.claude/.evo/<id>/history.json    # claude-code
~/.opencode/.evo/<id>/history.json  # opencode
~/.costrict/.evo/<id>/history.json  # costrict + vscode-costrict
```

history.json 使用 **开放字段 schema**（`dimensions` 是 map 而非固定 record），后期加新维度 / 新字段不破坏历史数据。rubric_version 当前为 `"1.0"`。

**关键边界**：evo **不写 catalog、不发上游 PR、不跑在 CI**。完全客户端按需触发，LLM 成本发生在用户本机（沿用本机 Claude Code 环境的 LLM 会话）。

### 后期增强项（未实施，保留扩展位）

1. **动态实测表现维（25% 权重）**：真跑 skill + 测试用例对比 baseline 评价输出质量。依赖：测试用例管理（第一次 LLM 生成 + 本机缓存 + 增量扩充）。增量策略：`content_hash_before` 未变复用，变了用历史 baseline 用例重跑。
2. **棘轮机制**：改后全维度重评，`final_score > baseline + ε` 才落盘，否则回滚到上次 SHA-256 快照。依赖：先验证当前 LLM 评估方差（DeepSeek 基准显示偏高但可信，方差未测）。
3. **独立评分子 agent**：改动 agent 与评分 agent 分离，避免左右互搏。依赖：Agent SDK 的子 agent spawn 能力。
4. **使用反馈 hook**（最后期，可能不做）：opt-in 记录 skill 调用 / 卸载事件，生成 `feedback-signal.json`，驱动"被动追踪 + 主动建议"的 Inbox。

**增量更新保证**：上述所有增强项都满足"不破坏已有数据"——history.json 的开放 schema + content_hash 复用 + rubric_version 版本号使得新维度 / 新步骤只能追加字段、不能改语义。参考 darwin-skill 的棘轮 + SHA-256 快照思路。

**源文件**：
- 命令行为契约：`platforms/{platform}/commands/eac/.../evo.md`（claude-code）或 `eac-evo.md`（其他 3 平台）
- Rubric 规范：`docs/wiki/evo-rubric.md`
- Change proposal：`openspec/changes/add-evo-command/` 归档后迁到 `openspec/specs/evo-command/spec.md`

## 注意事项

- `catalog/index.json`、各类型 `index.json`、`catalog/featured*.md` 由 CI 生成并提交，供 skill 命令与 README 渲染使用
- `curated.json` 是手工维护的精选数据，也提交到仓库
- 本地跑 sync 脚本不带 `GITHUB_TOKEN` 会大量 429 限流，数据不完整但不影响验证逻辑
- `fetch_raw_content()` 对 404 只输出 DEBUG 日志，这是正常探测行为（如 skills.json 列出但无 SKILL.md 的条目）
- `merge_index.py` 会在去重后检查各类型的 drop 比例，超过 50% 会输出 WARNING
- `ai-resource-eval` 依赖 pydantic + httpx，首次使用需 `pip install -e ai-resource-eval`
