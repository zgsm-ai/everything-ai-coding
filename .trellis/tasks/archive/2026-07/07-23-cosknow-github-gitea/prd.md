# CosKnow 同步链路接入（GitHub + Gitea 镜像）

## Goal

仿照 cos-graph（`sync-cosgraph-plugins.yml` FULL-REPO mirror）与 cospower（`sync-csc-plugins.yml`）的既有模式，为 `zgsm-sangfor/CosKnow` 新增第一方同步链路：catalog entry 入库 + 全仓镜像到 `costrict-plugins-repo/cosknow`（GitHub + 自建 Gitea `gitea.costrict.ai`），让 CosKnow 在 web hub 可列出、可评分、可安装。

## What I already know

### 既有两条链路（模板）

- **cos-graph（FULL-REPO mirror 模式）**：`scripts/sync_plugins_cosgraph.py`（stdlib-only，merge-preserve 写 `catalog/plugins/index.json` + `--overlay-catalog-index` 外科手术式 overlay `catalog/index.json`，entry 带 `external_mirror=true` / `prune_content=false` / `final_score=100` / `marketplace_verified=true`）+ `.github/workflows/sync-cosgraph-plugins.yml`（catalog commit → 全仓 clone 上游 → force-push GitHub org repo（`gh repo create` 幂等预建 + 设默认分支）→ Gitea mirror（`GITEA_TOKEN` secret + `GITEA_USER` var，API 预建 201/409、force-push、PATCH 默认分支）→ 可选 trigger release-catalog-bundle）。PREVIEW guard：非 canonical ref 只推 GitHub、不写 canonical catalog、不碰 Gitea。
- **cospower（子目录提取模式）**：`sync_plugins_csc.py` + marketplace build.py 提取 6 个 plugin bare repo → publish.sh 强推 GitHub → 逐个 bare repo mirror 到 Gitea。

### CosKnow 仓库事实（2026-07-23 实测）

- `zgsm-sangfor/CosKnow`，**私有仓**，默认分支 `v2`，size 426KB
- 根 `.claude-plugin/plugin.json`（name=`cosknow`, version 2.0.0, MIT）+ `.claude-plugin/marketplace.json`（marketplace name=`cos-know`，plugins[0].source=`./cosknow-plugin`）
- `cosknow-plugin/` 子目录：plugin.json（name=cosknow-plugin）+ hooks/ + dist/kb-cli.js + skills/（kb-init/kb-eval/kb-graph/kb-optimize/kb-pre/kb-publish/kb-query/kb-status/kb-update，含大量 prompts/references）
- **实质内容超出 plugin 子目录**：根级 `src/`（TypeScript CLI 源码）、`build.ts`、根级 `skills/`、`hooks/`、`.csc/kb/dist/kb-cli.js`、`test/` → 与 cos-graph 同型，cospower 式子目录提取会丢实质 → 应走 FULL-REPO mirror
- `discover_plugin_subdirs` 逻辑套用后只会发现根 plugin（`""`，因 `cosknow-plugin/` 下无 `.claude-plugin/plugin.json`）→ 单 entry `cosknow`

### 环境事实

- repo secrets 已有：`GITEA_TOKEN`、`MARKETPLACE_GITHUB_TOKEN`、LLM_*；vars：`GITEA_USER=costrict-plugins-repo`
- catalog 目前无 cosknow entry；Gitea 无 cosknow repo；GitHub org `costrict-plugins-repo` 存在
- 本地 main 已 rebase 到 origin/main（c9337ed）

## Assumptions (temporary)

- CANONICAL ref = `v2`（CosKnow 默认分支）
- 镜像目标名 = `costrict-plugins-repo/cosknow`（id == plugin name，与 graphify 惯例一致）

## Decision (ADR-lite)

**Context**：CosKnow 为私有仓且实质内容超出 plugin 子目录，需定 token、可见性、发布模式三项。
**Decision**（2026-07-23 用户确认）：
1. 私有仓读取 token = **MARKETPLACE_GITHUB_TOKEN**（用户确认已有 zgsm-sangfor 读权限），脚本 API/raw 读取与 workflow git clone 均用它
2. 镜像可见性 = **Public**（GitHub org repo + Gitea 均 public，与 graphify 完全同构）
3. 发布模式 = **FULL-REPO mirror**（同 cos-graph；entry 带 external_mirror=true）

**Consequences**：CosKnow 全部源码与历史将公开在 costrict-plugins-repo/cosknow；若上游 token 权限失效，sync step 会因 tree 拉取为空而非零退出（不产生半成品 catalog）。

## Requirements (evolving)

- 新脚本 `scripts/sync_plugins_cosknow.py`（cosgraph 模板：SOURCE_ID/SOURCE_REPO/branch 换成 CosKnow，私有仓所有 fetch 带 token）
- 新 workflow `.github/workflows/sync-cosknow-plugins.yml`（cosgraph 模板：UPSTREAM=zgsm-sangfor/CosKnow，TARGET=cosknow，CANONICAL_REF=v2，clone 带 token，Gitea mirror 步骤同款）
- Gitea 侧与另外两条链路一致：canonical only、GITEA_TOKEN/GITEA_USER、预建 + force-push + 默认分支 PATCH

## Acceptance Criteria (2026-07-23 全部验收通过)

- [x] `python scripts/sync_plugins_cosknow.py --overlay-catalog-index` 在带 token 环境产出 1 条 `cosknow` entry（external_mirror=true, verified, skills=10；本地实测 + CI run 30012310109）
- [x] workflow 手动触发后：GitHub `costrict-plugins-repo/cosknow@v2` 为全仓镜像（109 文件与上游一致、73 commits 全历史）且 v2 为默认分支
- [x] Gitea `costrict-plugins-repo/cosknow@v2` 同步且为默认分支（API 实测 default_branch=v2）
- [x] 幂等：run 30012425209 重跑输出 "No catalog changes"，无空提交
- [x] PREVIEW 模式（非 v2 ref）guard 与 cosgraph 同款表达式（结构复用，未单独实跑）
- [x] 无 token 本地跑 fail-fast（明确报私有仓需 PAT，exit 1）

## 实现补充（超出模板的三处适配）

1. **私有仓 token 贯穿**：脚本 main() 无 GITHUB_TOKEN fail-fast；workflow sync/clone 步骤均用 MARKETPLACE_GITHUB_TOKEN
2. **对外指针改指 public 镜像**：`source_url` 与 `bundle.source_repo` 指 `costrict-plugins-repo/cosknow`（非私有上游）——否则 web hub 链接 404、merge_index bundled-child 合成 raw fetch 失败；元数据读取仍走上游
3. **weekly sync.yml 加 CosKnow step**：official 是 per-type index 唯一 blanket 覆盖者，第一方 entry 靠每周重跑各自脚本存活（cos-graph/csc 同款），CosKnow step 带 MARKETPLACE_GITHUB_TOKEN + continue-on-error

## Definition of Done

- 测试补充（脚本级单测如适用）、CI green
- CLAUDE.md / 相关文档更新链路说明
- 回滚：重跑 canonical ref 即恢复

## Out of Scope

- 不改动 cos-graph / cospower 既有链路
- 不接入每周 sync.yml 主流程（与另外两条一致，独立 workflow_dispatch）

## Technical Notes

- 参考文件：`scripts/sync_plugins_cosgraph.py`、`scripts/sync_plugins_csc.py`、`.github/workflows/sync-cosgraph-plugins.yml`、`.github/workflows/sync-csc-plugins.yml`
- 私有仓注意点：`_http_get` 已支持 GITHUB_TOKEN header（raw + api 均可用于私有仓）；workflow clone 需 `https://x-access-token:${TOKEN}@github.com/zgsm-sangfor/CosKnow.git`
- cos-graph 上游是 public 匿名 clone —— CosKnow 这步是唯一结构性差异
