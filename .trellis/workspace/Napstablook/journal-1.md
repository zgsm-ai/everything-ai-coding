# Journal - Napstablook (Part 1)

> AI development session journal
> Started: 2026-06-16

---



## Session 1: 促升一等源 + github-trending 跨轮持久化 + security scan 复发超时修复

**Date**: 2026-06-22
**Task**: 促升一等源 + github-trending 跨轮持久化 + security scan 复发超时修复
**Branch**: `main`

### Summary

促升 10 个 monorepo 仓为逐仓一等 source（promote 清单+迁移+SOURCE_REGISTRY 登记），mattpocock 经 seed→促升路由入库 32 条。发现并根治 github-trending/促升 entry 跨轮被 sync_skills/sync_plugins blanket-overwrite 抹掉的既有 bug（覆盖前保留 active-discovery + recover 脚本回灌 2820 条），CI 实测 github-trending 1072→1911 持久化生效、促升源 10/10 存活。再根治 aggregate security scan 重扫已扫 entry 撞 6h 上限取消（A: rubric 短路跳过已扫；B1: commit 前置不被 security 连累）。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `af43a5f` | (see git log) |
| `798e6cf` | (see git log) |
| `8c26923` | (see git log) |
| `8739f9d` | (see git log) |
| `7df490d` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 2: security scan B2 回填 + 全链验证收口

**Date**: 2026-06-22
**Task**: security scan B2 回填 + 全链验证收口
**Branch**: `main`

### Summary

补 B2：aggregate security scan 后加第二次 commit 回填 security 风险评估（B1 commit 前置导致 security 结果进不了提交，实测仅 13322/23470）。CI run 27936439858 实测 A+B1+B2 全生效：aggregate 仅 34min（A 短路全 cache 命中）、commit #1+#2 双提交、已提交 catalog security 13322→23589、bundle 发布。复发 6h 超时 + security 不落地两问题根治。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `0c20c67` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 3: search-index + 前端搜索性能重构（瘦身/MiniSearch/分片/虚拟滚动）

**Date**: 2026-06-23
**Task**: search-index + 前端搜索性能重构（瘦身/MiniSearch/分片/虚拟滚动）
**Branch**: `main`

### Summary

排查'搜 mattpocock 看不到'发现前端 search-index 21MB+客户端 O(n) 全表扫、search_text 不含来源、source 字段全空。重构：build_frontend_data 产 slim 索引（最小卡片字段+含source/owner的截断search_text+每条shard）+填source+per-entry 256分片；useSearch 换 MiniSearch；Detail 按 shard 拉单片；Browse 用 @tanstack/react-virtual 虚拟滚动。实测搜 mattpocock 召回整源(2→32)、raw 21→11MB/gzip 3.46→2.18MB。check 在真实23590条上验 shard契约零失配。已部署 Pages(run 27996266964 success)。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `54515a6` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete
