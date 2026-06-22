# trending seed 仓清单 — 收 mattpocock/skills 等无 topic 高星 skill 仓

## Goal

给 github-trending 主动发现源加一个**手工 seed 仓清单**,把"高星但没打 topic / desc 通用、因而被搜索查询漏掉"的优质 skill/plugin 仓直接喂进候选池,复用现有 triage(LLM 判别 + 深拉)自动入库。首个收录目标:`mattpocock/skills`。

## What I already know（已实测）

* `mattpocock/skills`:132,733 stars,`Skills for Real Engineers. Straight from my .claude directory`,size 264KB,72 文件,**29 个 SKILL.md**,0 marketplace.json,**topics 全空**,当前 catalog 未收。
* 漏收根因:**无 topic + desc 通用** → github-trending 的搜索查询(`topic:claude-skill` / `"claude skills" in:...` / `"SKILL.md" in:readme` 等)都匹配不到。处理它本身零难度(标准 skill 仓,现有 skill 路线全套可吃)。
* github-trending 已是分阶段:Stage A(`scripts/sync_github_trending.py` 纯搜索,产 `.github_trending_cache/candidates.json`)→ triage(`scripts/triage_github_trending.py` LLM 判别 + 深拉)。seed 只需在 Stage A 把 seed 仓并进候选表。

## Requirements

1. 新增手工 seed 文件 `scripts/trending_seed_repos.json`(数组,元素 `owner/repo` 或 `{repo, branch?}`),首项 `mattpocock/skills`。带注释说明用途(收"高星但无 topic"被搜索漏掉的好仓)。
2. `sync_github_trending.py` Stage A:加载 seed → 对每个**不在 known_repos** 的 seed 仓,用 `utils.github_api` 拉 `repos/<owner>/<repo>` 元数据(stars/default_branch/topics/description/pushed_at)→ 作为候选并进候选表。
3. **seed 不受每轮限量(MAX_VERIFY)截断**:手工挑的必须每轮都处理(prepend 或 cap 豁免)。
4. seed 仓后续走完全相同的 triage(LLM is_primary_skill 判别 + 深拉构造 entry),无特殊路径。
5. 已在 catalog / known_repos 的 seed 仓自动跳过(不重复)。

## Acceptance Criteria

* [ ] `mattpocock/skills` 出现在 Stage A 候选表(即便无 topic/不匹配搜索)
* [ ] seed 仓不被 MAX_VERIFY 截断(本地用小 cap 验证 seed 仍在)
* [ ] seed 仓元数据拉取失败时不崩(WARN 跳过)
* [ ] 已收录的 seed 仓被 known_repos 跳过
* [ ] 单测覆盖:seed 加载 / 并入候选 / cap 豁免 / known 跳过 / 拉取失败兜底
* [ ] 不破坏现有 Stage A / triage;现有测试绿

## Definition of Done

* 单测 + 现有 sync_github_trending 测试绿
* CLAUDE.md「主动发现源」段补一句 seed 机制
* （收录效果需 CI 带 LLM 跑一轮验证,但代码层可单测）

## Out of Scope

* 不改 triage 的判别/深拉逻辑(seed 走同一路径)
* 不批量加 seed(先只 mattpocock/skills;清单后续按需扩)
* 不碰 plugin marketplace 发布链路

## Technical Notes

* Stage A 落点:`scripts/sync_github_trending.py` 的 `discover_candidates` / `collect_candidates`(候选表生成处)
* 复用 `utils.github_api`（拉 repo 元数据）、`build_known_repos`（去重预过滤）
* seed 候选的字段要对齐搜索 item（full_name/stars/default_branch/pushed_at/topics/description）以便 triage 一致消费
* 关联:github-trending 任务 `research/plugin-route-and-staging.md`（Stage A/B/C 结构）
