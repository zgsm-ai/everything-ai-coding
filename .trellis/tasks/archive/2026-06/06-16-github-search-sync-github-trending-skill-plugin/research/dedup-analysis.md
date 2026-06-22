# Research: GitHub Search 主动发现源的去重 / 重复风险分析

- **Query**: 新的 "GitHub Search 主动发现" sync 源发现的仓与现有 catalog 去重时会不会产生重复
- **Scope**: internal（真实代码 + `catalog/index.json` 真实数据 + `/tmp/gap_rows.json` 301 候选仓实测）
- **Date**: 2026-06-16

## TL;DR（结论先行）

1. **同类型（skill↔skill / plugin↔plugin）去重是可靠的**：`skill_identity_key` 用 `(owner, repo, skill_name)` 三元组、`plugin_identity_key` 用 `('plugin', marketplace_repo, plugin_name)` 三元组收敛。即使新源用了不同 branch（`main` vs `HEAD`）、不同 URL 写法、owner 大小写不同，**只要 skill_name / plugin_name 一致就会正确 collapse**。
2. **跨类型（skill↔plugin）永远不会收敛** —— 这是最大重复风险。`_identity_key_for_entry`（utils.py:1261）按 `type` 路由，skill 与 plugin 落在**不同 key namespace**，物理上不可能撞键。
3. **实测重复表面积**：前序 GitHub Search 的 301 个候选仓里 **60 个已在 catalog**。其中：
   - **30 个仅以 `plugin`（claude-plugins-dev）存在** → 若新源把它当 **skill** 发现（因为有 SKILL.md），会**产生重复**（skill 条目 + 既有 plugin 条目并存）。
   - **15 个 skill+plugin 双类型都在** → 同类型各自 collapse，但跨类型那一半仍并存（现状本就并存，新源不会恶化也不会修复）。
   - **7 个仅以 `mcp` 存在** → 若新源当 skill/plugin 发现，会重复（mcp 与 skill/plugin 跨类型不收敛）。
   - **7 个仅以 `skill` 存在** → 新源当 skill 发现 → **正确 collapse**，零重复。
   - **1 个（obra/superpowers-marketplace）** → marketplace 本仓没有任何 `source_url` 指向它（其 plugin 指向别的 repo），新源若发现该仓会逃过 `source_url`-based 去重。
4. **必须在扫描/LLM 之前做"全类型 owner/repo 预过滤"**：现有 `deduplicate()` 是 merge 阶段、**type-aware**、且只在写库时跑；它**救不了跨类型重复**，也省不了你的 API/LLM 成本。新源必须自带一个独立的 "repo 已存在于任何 type/source ⇒ 跳过" 的预过滤层。

---

## Findings

### 1. 去重机制全貌（带 file:line）

#### 入口：`deduplicate()` — `scripts/utils.py:1278`

两趟策略：

**Pass 1 — type-aware identity collapse（utils.py:1302–1392）**
- 对每个 entry 调 `_identity_key_for_entry()`（utils.py:1261）拿到 key；key 为 `None` 的 entry 直接穿过不参与 collapse。
- 同 key 的 group 里选 winner（按 `source_priority` 降序 / 各类型有专属 rank 函数），loser 标记丢弃，并把 sibling 字段 merge 到 winner 上。

**Pass 2 — legacy id + url dedup（utils.py:1394–1421）**
- `seen_ids`：同 `id` 只留第一个（first-wins）。
- `seen_urls`：对 **非 rule/prompt/plugin** 类型，按 `normalize_source_url()`（utils.py:558）归一后的 URL 去重。
- `url_dedup_skip_types = {"rule", "prompt", "plugin"}`（utils.py:1404）—— 这三类多个 entry 合法共享一个 repo URL。

#### 路由：`_identity_key_for_entry()` — `scripts/utils.py:1261`

```
type == "skill"  -> skill_identity_key(entry)    # :878
type == "mcp"    -> mcp_identity_key(entry)       # :909
type == "rule"   -> rule_identity_key(entry)      # :963
type == "plugin" -> plugin_identity_key(entry)    # :1236
else             -> None                          # prompt 等无 identity key
```
**关键**：key 的第一维就是 type 派生的。skill key 是裸三元组 `(owner, repo, name)`；plugin/rule/mcp key 第一维是字面常量 `'plugin'`/`'windsurfrules'`/`'github'|'registry'`。**不同类型 key 不可能相等**。

#### 各类型 key 收敛规则

| 类型 | 函数:行 | 返回的 key | 收敛依据 |
|---|---|---|---|
| **skill** | `skill_identity_key` utils.py:878 | `(owner, repo, skill_name)` 全小写 | `_parse_owner_repo(source_url)`（:807，正则 `github\.com/([^/]+)/([^/#?]+)`，owner/repo 强制小写）+ `_extract_skill_name(entry)`（:858）。镜像 `sickn33/antigravity-awesome-skills` 被重写成 `anthropics/skills`（`_KNOWN_MIRRORS` :789）。非 skill / 无 GitHub URL / 无 name → `None` |
| **plugin** | `plugin_identity_key` utils.py:1236 | `('plugin', install.marketplace_repo, install.plugin_name)` | 直接读 `install.marketplace_repo`（如 `mukul975/Anthropic-Cybersecurity-Skills`，**保留原始大小写**）+ `install.plugin_name`。任一缺失 → `None`（穿过，后续由 merge validator drop） |
| **mcp** | `mcp_identity_key` utils.py:909 | registry `io.github.<o>/<r>` → `('github', o/r, '')`；其他 reverse-DNS → `('registry', name, '')`；普通 GitHub → `('github', o/r, sub_path)` | sub_path 取 `/tree|blob/<branch>/(.+)`（:957），monorepo 子路径各自独立 key，**不做 owner-only fuzzy** |
| **rule** | `rule_identity_key` utils.py:963 | `('windsurfrules', slug)` | **仅** `_WINDSURFRULES_REPOS`（:796，SchneiderSam + balqaasem 两仓）生效；其他来源 rule 返回 `None`（按 id 去重） |

#### `_extract_skill_name()` 的关键正则 — `scripts/utils.py:858`

优先级：
1. `#skill=([^&]+)`（skills.sh 锚点）→ 用锚点值
2. `/tree/[^/]+/skills/([^?#]+)` → 取 `/skills/` **直接** 之后的路径（保留嵌套子路径，rstrip `/`）
3. **fallback → `entry["name"]`**

**盲区根源**：正则要求 `skills/` **紧跟在 `/tree/<branch>/` 之后**。对 `/blob/...`、`/tree/HEAD/openclaw/skills/do`（嵌套前缀）、`/tree/HEAD/plugins/caveman/skills/caveman`、或 repo-root URL，正则**不命中**，全部退回 `name`。实测 `plugin-bundled-skill` 共 2025 条，其中 **105 条** 的 `source_url` 没有 `/tree/<b>/skills/` 直接命中（走 name fallback）。

#### `source_priority()` 选 winner — `scripts/utils.py:820`

`1000`(anthropics) > `900`(其他官方 org / registry.mcp.io) > `800`(skills.sh `#skill=`) > `500`(普通 GitHub) > `200`(已知镜像) > `100`(非 GitHub)。**新 GitHub Search 源发现的普通仓默认落 500 tier**，会输给已有的 800/900/1000 winner（即新源条目被丢弃、保留旧 winner）—— 这正是去重想要的结果。

---

### 2. 重复风险判定（三种"已以别的形式在 catalog"场景）

设新源把一个仓发现为 **skill**（有 SKILL.md）或 **plugin**（有 marketplace.json）。

#### (a) 仓已通过 `claude-plugins-dev` 作为 **plugin** 收录

- 新源若也当 **plugin** 发现 → `plugin_identity_key` 命中 `('plugin', marketplace_repo, plugin_name)` → **正确 collapse**（前提：新源算出的 `marketplace_repo` / `plugin_name` 与既有一致；既有大小写保留，新源也必须保留同样的 `owner/Repo` 大小写）。
- 新源若当 **skill** 发现（仓里有 SKILL.md，而它在 dev registry 只是个 plugin 壳）→ skill key 与 plugin key **不同 namespace** → **产生重复**：catalog 里同时有 `plugin:claude-plugins-dev` 条目 + 新的 `skill` 条目。**这是 30/60 实测仓的处境。**

> 实测一例（utils.py 实跑验证）：`mukul975/Anthropic-Cybersecurity-Skills`
> - 既有 `plugin` 条目 key = `('plugin', 'mukul975/Anthropic-Cybersecurity-Skills', 'cybersecurity-skills')`
> - 新发现 `skill` 条目 key = `('mukul975', 'anthropic-cybersecurity-skills', '<skill-name>')`
> - 两者类型不同 → `skill_identity_key(plugin_entry)` 直接返回 `None`（utils.py:894 type 守卫）→ **绝不收敛**。

#### (b) 仓已通过 Tier 2 作为 **skill** 收录

- 新源当 **skill** 发现 → 同为 skill → `skill_identity_key` 用 `(owner, repo, name)` collapse。
- **会正确收敛的条件**：`_extract_skill_name` 对新旧两边算出**相同 name**。已实测：branch 差异（`HEAD`↔`main`）、root↔subpath、owner 大小写**都不影响**收敛（见下方实测）。
- **不收敛的盲区**：若一边走 `/skills/` 路径正则、另一边走 `name` fallback，且两边 `name` 取法不同（如旧条目 `name='do'` vs 新源 `name='claude-mem-do'`）→ key 不一致 → 重复。

#### (c) 仓的 skill 已作为某 plugin 的 `bundled_in` 子条目存在

`merge_index.py:_apply_bundled_in_annotations`（:224）会把 plugin bundle 里的每个 skill **合成成独立 `type=skill` 条目**（`source: "plugin-bundled-skill"`，`_synthesize_orphan_skill_entry` :110）。这些合成条目的：
- `source_url = https://github.com/{repo}/tree/{branch}/{skill_dir}`（:151，`skill_dir` 含完整嵌套路径，`branch` 默认 `HEAD`）
- `name = <leaf skill_name>`
- `id = _synthetic_skill_id(plugin_id, skill_name, ...)`（:62，形如 `<plugin-id>-<skill-name>`）

→ 它们是 **真正的 type=skill 条目**，所以新源当 skill 发现**同一个 SKILL.md 时会与之同类型 collapse**（key 都是 `(owner, repo, skill_name)`）。**实测：`mukul975/...` 的 754 条 bundled-skill 与新发现的 skill key 完全一致，会 collapse。**
- ⚠️ 但 `source_url` 的 `tree/HEAD` 与新源可能用的 `tree/main` 不同 → **Pass-2 legacy URL dedup 救不了**（实测 `normalize_source_url` 因 branch token 不同而判不等）。**只有 Pass-1 的 skill_identity_key 救得了**，而它对 name fallback 路径敏感。

#### 跨类型碰撞汇总（同一 repo 既是 skill 又被某 plugin bundle）

实测 60 个 in-catalog 仓里 **15 个 skill+plugin 双类型并存**（如 `anthropics/skills` skill×18+plugin×3、`davila7/claude-code-templates` skill×259+plugin×10、`mukul975/...` skill×754+plugin×1）。这种并存是 catalog **现状**（plugin 条目 + 其 bundled-skill 子条目本就是设计上并存的两类资源）。新源**不会修复也不会加剧**这种跨类型并存——它只在自己发现的那一类内部 collapse。

---

### 3. 实测重复表面积（`/tmp/gap_rows.json` 301 候选 × `catalog/index.json`）

301 候选仓：**60 in_catalog / 241 not**。60 个已收录仓按"既有类型覆盖"分类（决定新源会 collapse 还是 dup）：

| # | 类别 | 新源当 skill 发现 | 新源当 plugin 发现 |
|---|---|---|---|
| **30** | **仅 plugin 存在**（全来自 `claude-plugins-dev`） | **DUP**（skill 与 plugin 不收敛） | collapse ✓ |
| **15** | **skill + plugin 双存在** | skill 部分 collapse ✓（跨类型部分本就并存） | plugin 部分 collapse ✓ |
| **7** | **仅 skill 存在** | **collapse ✓ 零重复** | DUP（plugin 与 skill 不收敛，但这些仓多半没 marketplace.json，不会被当 plugin 发现） |
| **7** | **仅 mcp 存在** | DUP（mcp↔skill 不收敛） | DUP（mcp↔plugin 不收敛） |
| **1** | **obra/superpowers-marketplace** | — | 见盲区 §4 |

**最关键数字**：**30 个"仅 plugin（claude-plugins-dev）"高星仓**，若新 skill 源去发现它们的 SKILL.md，会**全部产生重复条目**。示例（stars 降序）：`obra/superpowers`(228916)、`nexu-io/open-design`(65542)、`composiohq/awesome-claude-skills`(107 plugin 条)、`addyosmani/agent-skills`、`ruvnet/ruflo`(34 plugin 条)、`anthropics/knowledge-work-plugins`(61)、`alirezarezvani/claude-skills`(74)、`trailofbits/skills`(39)、`deanpeters/product-manager-skills`(47)…

**既有 source 分布（60 仓 → 实际命中的 type:source）**：
- `plugin:claude-plugins-dev` 是绝对主力（dev registry 把大量高星 skill 仓当 plugin 收了）。
- `skill:plugin-bundled-skill`（合成子条目，如 mukul975 ×754、coreyhaines31 ×35、yeachan-heo ×40）。
- `skill:skills-sh`（vercel-labs、antfu、jimliu/baoyu、wshobson…）。
- `skill:antigravity-skills`（sickn33 镜像 ×1368，会被重写到 anthropics/skills）。
- `mcp:awesome-mcp-zh / registry.modelcontextprotocol.io / mcp.so`（serena、agent-reach、pg-aiguide…）。
- `plugin:claude-plugins-official`（obra/superpowers、anthropics/claude-plugins-official）。

> 完整 60 行明细已通过实跑打印（见会话 tool 输出），核心 30 个 dup-risk 仓如上。

---

### 4. 去重盲区（同一底层 repo 不会收敛的情形）

1. **跨类型恒不收敛**（最大盲区）：`_identity_key_for_entry`（:1261）按 type 路由，skill/plugin/mcp 落不同 namespace。同一 repo 以 plugin 收录后，再被当 skill 发现 → 必重复。**30/60 实测仓正中此坑。**

2. **`_extract_skill_name` 的 `name` fallback 漂移**（utils.py:872 正则只吃 `/tree/<b>/skills/`）：
   - 新源用 `/blob/...` URL、或 skill 不在 `/skills/` 直下（嵌套如 `openclaw/skills/`、`plugins/x/skills/`）、或 repo-root URL → 退回 `entry["name"]`。
   - 实测 105 条 bundled-skill 走此 fallback；只要新源对同一 skill 取了不同 `name`，key 就不一致 → 重复。

3. **branch token 差异击穿 Pass-2 URL dedup**：合成 bundled-skill 用 `tree/HEAD`（merge_index.py:141），新源大概率用 `tree/main`。`normalize_source_url`（utils.py:558）只小写 + 去 `.git`/trailing slash，**不归一 branch** → `head` ≠ `main` → Pass-2 url 去重判不等。此时**唯一防线是 Pass-1 skill_identity_key**（依赖 §4.2 的 name 一致）。

4. **marketplace 容器仓无 `source_url` 指向自己**：`obra/superpowers-marketplace` 的 plugin 把 `source_url` 指向被打包的真仓（如 `obra/episodic-memory.git`），`install.marketplace_repo` 才记录容器仓。新源若按 `source_url`-based owner/repo 预过滤去查"容器仓在不在 catalog"，会**查不到**（catalog 无任何 entry 的 `source_url` 含 `superpowers-marketplace`）→ 误判为新仓。预过滤必须**同时索引 `install.marketplace_repo`**。

5. **owner 改名 / repo 改名**：`_parse_owner_repo` 只认当前 URL 字面 owner/repo。GitHub 改名后旧 catalog 用旧名、新发现用新名 → 不收敛（GitHub redirect 不在去重考虑内）。

6. **prompt 类无 identity key**：`_identity_key_for_entry` 对 prompt 返回 `None`，只靠 id/url 去重。新源若涉及 prompt（不在本 MVP 范围）需自带去重。

---

### 5. 建议：扫描/LLM 之前的预过滤策略

目标：在**昂贵的 Tree API 扫描 + LLM 6 维评估 + security scan 之前**，把"已存在于任意 type/source 的仓"挡掉（省 API + LLM 成本，且物理上杜绝跨类型重复）。

**核心：建一个 repo-level "已收录集合" 预过滤层（独立于 merge 阶段的 type-aware `deduplicate()`）。**

1. **构建 `known_repos: set[str]`，键 = `owner/repo` 全小写，覆盖全 catalog 全类型**。来源字段要**同时**吃两个：
   - `_parse_owner_repo(entry["source_url"])`（覆盖 skill/mcp/普通 plugin/bundled-skill）。
   - `entry["install"]["marketplace_repo"]`（小写化，覆盖 §4.4 的 marketplace 容器仓盲区）。
   - 镜像归一：命中 `_KNOWN_MIRRORS`（utils.py:789）的重写到 `anthropics/skills`，避免把镜像当新仓。

2. **GitHub Search 一拿到候选 repo `owner/repo`，先 `lower()` 查 `known_repos`，命中即跳过**——不发 Tree API 查 SKILL.md、不进 hard_filter、不评 LLM。这一步直接吃掉实测 60/301（≈20%）的候选，**包括那 30 个否则会变跨类型重复的"仅 plugin"仓**。

3. **不命中（疑似全新仓）才继续**：结构验证（`skill_registry.scan_repo_via_api` 找 SKILL.md / `marketplace_verifier` 验 marketplace.json）→ hard_filter → LLM。

4. **写入 index.json 时仍保留正常 type 字段**，让 merge 阶段的 `deduplicate()` 作为第二道安全网（防同一次 sync 内 / 与同周其他源的同类型撞键）。预过滤层不替代 `deduplicate()`，是它的前置成本闸门。

5. **若坚持"按结构定 type 后再去重"**，至少要做到：新源给 skill 条目算 `name` 时**严格复用 `_extract_skill_name` 同款逻辑**（取 `/skills/` 后 leaf，或 SKILL.md 所在目录名），并把 `source_url` 写成 `tree/HEAD/skills/<name>` 形态（对齐合成 bundled-skill 的 `tree/HEAD`），让 Pass-1 skill key 能与既有 bundled-skill / Tier2 skill collapse，规避 §4.2/§4.3 盲区。

6. **增量友好 + 失败可见**（对齐 PRD / 同会话刚修的 skill_registry 行为）：`known_repos` 每次 sync 从最新 `catalog/index.json` 现算（不缓存空集），构建失败要 raise/WARN 可见，不能静默退化成空 set（否则预过滤失效、全量重评）。

---

## Caveats / Not Found

- 本分析基于 `/tmp/gap_rows.json`（301 候选，前序同会话 GitHub Search 产物，含 `in_catalog`/`types`/`stars`）与本地 `catalog/index.json`（12,632 条，2026-06-11 快照）。241 个 not-in-catalog 候选**未**逐仓验证其是否真有 SKILL.md/marketplace.json（结构验证是新源 runtime 职责，不在本调研）。
- 实测的 type 计数来自 `source_url` 反解的 owner/repo 聚合，monorepo 子路径可能让同一仓在某类型下计多条（如 mukul975 skill×754），不影响"该 repo 在/不在某 type"的结论。
- `/tmp/catalog_lookup.json`（预建映射）**缺 `source` 字段**，故本调研改用 `catalog/index.json` 实时重建带 `source`/`source_url` 的映射；如需复用 lookup，建议补 `source` 与 `install.marketplace_repo` 两字段。
- GitHub owner/repo 改名导致的去重盲区（§4.5）未量化（需历史 redirect 数据，不可得）。
