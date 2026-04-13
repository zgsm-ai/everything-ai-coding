# Home

Everything AI Coding 是一个持续更新的开发资源目录仓库。主干工作不是写业务功能，而是把 MCP Server、Skill、Rule、Prompt 从多个上游汇总进统一目录，再分发给站点、安装脚本和多平台命令使用。

## 读者

这套 wiki 面向三类人：

- 维护目录和脚本的人
- 提交资源、规则或文档的人
- 需要快速判断“问题该在哪一层处理”的人

如果你的目标只是安装和使用项目，先看根目录 [README](../../README.zh-CN.md)。

## 从哪里开始

| 目标 | 页面 |
| --- | --- |
| 看懂仓库如何运作 | [Architecture](./Architecture.md) |
| 了解目录字段、治理和边界 | [Catalog Governance](./Catalog-Governance.md) |
| 提资源、改脚本、提文档 | [Contribution Guide](./Contribution-Guide.md) |
| 处理同步、发布和排障 | [Operations Runbook](./Operations-Runbook.md) |
| 查历史研究和设计背景 | [Design Records](./Design-Records.md) |

## 仓库的实际组成

这个仓库长期稳定的部分只有几类：

- `catalog/`：目录数据和人工 curated 入口
- `scripts/`：同步、合并、治理、发布脚本
- `platforms/`：各平台适配文件
- `frontend/`：站点前端
- `.github/workflows/`：自动化工作流
- `docs/wiki/`：稳定维护文档

这里最常见的误判，是把仓库只看成其中一类。

它不是：

- 纯前端项目
- 纯 awesome list
- 纯脚本仓库
- 纯规格仓库

它同时包含目录生产、目录治理、平台分发和变更管理。

## 文档分层

| 位置 | 主要用途 | 不该承接的内容 |
| --- | --- | --- |
| README | 对外介绍、安装、使用 | 内部维护手册、长期设计背景 |
| `docs/wiki/` | 稳定的维护说明和边界 | 临时讨论稿、一次性研究过程 |
| 研究文档 | 保存背景、策略和专题长文 | 仓库稳定入口 |
| `catalog/` | 数据文件与 schema | 文字性教程和设计解释 |

这层分工比文件名本身更重要。位置放错，后面的人就会在错误入口里找答案。

## 一张图

```text
上游源
  ↓
scripts/sync_*.py / crawl_mcp_so.py
  ↓
catalog/<type>/index.json + curated.json
  ↓
scripts/merge_index.py
  ↓
catalog/index.json
  ├─ catalog/search-index.json
  ├─ scripts/generate_featured.py -> catalog/featured*.md
  ├─ scripts/build_frontend_data.py -> frontend/public/api/*
  ├─ scripts/generate_pages.py -> frontend/dist/api/v1/*
  └─ platforms/* / install scripts
```

这张图里真正的统一事实出口仍然只有 `catalog/index.json`。`catalog/search-index.json`、featured 数据、前端消费数据和静态 API 都是从它派生出来的消费产物。只要某个修改会改变这份文件，它影响的就不是单一页面或单一平台，而是整个目录出口。

## 常见入口

### 我只想补一条资源

先看 [Contribution Guide](./Contribution-Guide.md) 里的 curated 路径，不要先动自动同步产物。

### 我看到目录字段不合理

先看 [Catalog Governance](./Catalog-Governance.md)，确认这是不是字段定义问题、合并问题，还是上游噪声问题。

### 我看到站点显示怪

先去 [Architecture](./Architecture.md) 确认问题是在目录层还是发布层，再决定看 `frontend/` 还是 `scripts/`.

### 我准备做结构性改动

先确认是否应该先写独立设计稿。只要改动会影响目录模型、平台契约、治理规则或长期维护流程，就不再是普通局部修补。

## 当前边界

这套 wiki 现在重点覆盖：

- 仓库整体结构
- 目录治理边界
- 贡献路径
- 维护和排障入口
- 现有研究与设计记录索引

它不打算替代源码阅读，也不打算把每个脚本参数逐项搬进文档。变化快、细节重、验证依赖强的内容，仍以源码和单独维护的设计文档为准。
