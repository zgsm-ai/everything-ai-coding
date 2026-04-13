# Architecture

Everything AI Coding 由五个长期存在的部分组成：上游采集、类型索引、合并与治理、站点发布、平台适配。主干产物是 `catalog/index.json`；站点、安装脚本和平台命令都围绕这份目录工作。

## 范围

本页覆盖：

- 仓库的稳定组成部分
- 目录从上游到最终发布的主链路
- 每一层的职责边界

本页不覆盖：

- 字段逐项定义
- 单个脚本的参数细节
- 前端页面实现
- 具体 change 的设计决策

这些内容分别放在 `Catalog Governance`、源码、`frontend/` 和单独维护的设计文档里。

## 系统结构

| 组成部分 | 主要位置 | 直接产物 | 不负责的事情 |
| --- | --- | --- | --- |
| 上游采集 | `scripts/sync_*.py`、`scripts/crawl_mcp_so.py` | 各类型 `index.json` | 全局去重、最终排序、页面展示 |
| 类型索引 | `catalog/mcp/`、`catalog/skills/`、`catalog/rules/`、`catalog/prompts/` | 自动同步数据、`curated.json` | 跨类型治理、最终对外视图 |
| 合并与治理 | `scripts/merge_index.py`、`scripts/enrichment_orchestrator.py`、`scripts/scoring_governor.py`、`scripts/catalog_lifecycle.py` | `catalog/index.json`、治理信号、生命周期字段 | 取代上游事实源、替代人工判断 |
| 站点发布 | `scripts/build_frontend_data.py`、`scripts/generate_pages.py`、`scripts/generate_featured.py`、`frontend/` | GitHub Pages 站点、静态 API | 决定是否收录资源、定义 schema |
| 平台适配 | `platforms/`、`install.sh`、`install.ps1` | 各平台 skill / command 安装入口 | 控制平台本身行为、保证平台兼容性永久稳定 |

## 主链路

```text
上游源
  ↓
scripts/sync_*.py / crawl_mcp_so.py
  ↓
catalog/<type>/index.json
  + catalog/<type>/curated.json
  ↓
scripts/merge_index.py
  ↓
catalog/index.json
  ├─ scripts/build_frontend_data.py
  ├─ scripts/generate_featured.py
  ├─ scripts/generate_pages.py
  └─ platforms/* / install.sh / install.ps1
```

这条链路里，真正的统一出口只有一个：`catalog/index.json`。只要某个改动会影响这份文件，它就不再是局部改动，而是目录层改动。

## 1. 上游采集

采集层按资源类型拆分。当前主干的入口包括：

- `scripts/sync_mcp.py`
- `scripts/sync_skills.py`
- `scripts/sync_rules.py`
- `scripts/sync_prompts.py`
- `scripts/crawl_mcp_so.py`

采集层负责把不同来源转成统一的基础记录，并写入各自类型目录。

采集层的边界很明确：

- 可以做格式归一化。
- 可以做少量字段补齐。
- 不能在这里定义全局优先级。
- 不能把单一来源的视角当成最终目录结论。

采集失败的影响通常是覆盖率下降或新鲜度下降，不会自动等价于“整个仓库不可用”。

## 2. 类型索引

`catalog/<type>/index.json` 是自动同步产物，`catalog/<type>/curated.json` 是人工补充入口。两者共同组成某一类型的输入面。

这里最容易被误解的点有两个：

第一，`index.json` 不是最终目录，只是某一类型的阶段性结果。

第二，`curated.json` 不是万能覆盖层。根据当前 `scripts/merge_index.py` 的实现，curated 主要用于补充 `tags` 和 `tech_stack`，以及在没有匹配项时追加新条目；它不会无条件重写所有核心字段。

这意味着：

- 适合用 curated 精修高价值条目。
- 不适合把 curated 当成绕过主流程的总开关。

## 3. 合并与治理

`scripts/merge_index.py` 是目录主干的装配点。当前实现至少会做四件事：

- 读取各类型 `index.json` 与 `curated.json`
- 按 `id` 和标准化后的 `source_url` 去重
- 修正非法分类
- 调用富化、评分、治理和生命周期逻辑，生成统一目录

其中有一个重要边界来自现有实现本身：curated 进入合并后是“补充优先”，不是“事实优先”。当前代码明确把 `name`、`description`、`stars`、`source_url`、`install`、`evaluation` 视为非补充字段，不在 `overlay_curated_fields()` 中直接覆盖。

这一层负责目录质量，不负责目录真实性。更具体地说：

- `evaluation.final_score` 是排序信号，不是资源价值定论。
- `health.freshness_label` 是维护信号，不是项目生死判决。
- `added_at` 表示目录生命周期，不表示资源第一次出现在互联网的时间。

## 4. 发布链路

发布链路把统一目录变成两个方向的消费产物：

- 站点和静态 API
- 平台安装与命令入口

站点发布主要由 `publish-site.yml` 驱动。当前流程会：

1. 生成 featured 数据。
2. 构建前端消费数据。
3. 构建 `frontend/`。
4. 生成静态 API 页面。
5. 部署到 GitHub Pages。

这层的职责是分发，不是治理。它可以放大上游质量，也会原样暴露上游问题；它不会自动纠正目录层的错误。

## 5. 平台适配

`platforms/`、`install.sh`、`install.ps1` 负责把统一目录接到不同 AI Coding 平台的目录结构和命令约定上。

平台适配层负责：

- 安装路径差异
- 命令命名差异
- 平台对应的 skill / command 文件组织

平台适配层不负责：

- 定义目录 schema
- 决定资源收录
- 保证平台未来版本不改变其目录结构或行为

这个边界必须单独强调：仓库可以适配平台，不能控制平台。

## 6. 自动化工作流

`.github/workflows/` 中至少有三条主线：

- `sync.yml`
- `publish-site.yml`
- `validate-pr.yml`

### `sync.yml`

当前配置每周一 `03:23 UTC` 定时触发，也支持手动触发。它会恢复缓存、执行各类同步脚本、检查是否至少保留了部分类型数据、运行 `merge_index.py`、更新双语 README，并在有变更时自动提交。

这条流程的策略是“尽量产出”，不是“任何一步失败都整体失败”。从现有配置可以直接看到多个同步步骤和合并步骤都带 `continue-on-error: true`。这带来两个后果：

- 单一上游失败时，目录仍可能继续更新。
- 流程整体成功时，产物也可能只是“部分完整”。

### `publish-site.yml`

这条流程负责构建和部署站点。它不重新同步目录，只消费仓库当前状态。

### `validate-pr.yml`

这条流程只校验 `catalog/**/curated.json` 的 PR 变化，调用 `scripts/validate_curated.py` 做结构与基础约束检查。它不是全仓库通用 CI，也不替代脚本级验证。

## 7. 文档分工

仓库内现在有三类长期可见的说明性内容：

- README：面向外部使用者
- `docs/wiki/`：面向维护者和贡献者的稳定说明
- 研究文档：面向专题研究和长文记录

这三者的边界如下：

| 位置 | 主要回答的问题 | 不回答的问题 |
| --- | --- | --- |
| README | 项目是什么，怎么安装，怎么用 | 内部维护动作、长期设计背景 |
| `docs/wiki/` | 仓库如何运作，哪些边界不能越 | 具体实现方案的推演过程 |
| 研究文档 | 研究、专题设计、背景分析 | 当前主干的最终执行逻辑 |

## 8. 维护时的判断顺序

出现问题时，建议先判断问题落在哪一层，再决定改哪里：

1. 上游没拉到，先查采集层。
2. 某类型条目异常，先查对应 `catalog/<type>/`.
3. 全局字段或排序异常，查 `merge_index.py` 和治理逻辑。
4. 页面显示异常，查发布层和前端。
5. 平台安装异常，查 `platforms/` 与安装脚本。

先定位层级，再修改文件，比先选文件再解释问题可靠得多。

## 9. 当前架构不承诺的事情

以下几件事不在当前架构的承诺范围内：

- 第三方资源一定安全可用
- 每次同步都百分之百完整
- curated 改动一定覆盖自动同步字段
- 任意平台未来都能零成本继续兼容

这不是文档保守，而是目录型仓库的真实边界。把边界写清楚，比把系统描述得无所不能更有用。
