# download_catalog 抓取层加固 RemoteDisconnected

## Goal

CI「Release Catalog Bundle」的 `Download catalog` 步骤会在下载 ~12383 个 skill 时，
因**单个** GitHub raw 请求碰到瞬时 `http.client.RemoteDisconnected` 而整批崩溃（exit 1）。
该错误偶发、非必然触发（同一 run rerun 后 43m 成功），但底层是脆弱性 bug：
任意一个瞬时断连就能端掉整个 release。目标是加固抓取层 + 下载兜底，让偶发网络错误
不再阻断 release bundle。

## What I already know

* 失败 run: 28797563033，job `build-and-release`，step「Download catalog」，脚本 `scripts/download_catalog.py`
* 直接触发：`utils.fetch_raw_content`（`scripts/utils.py:505`）内 `urlopen` 抛 `RemoteDisconnected`
* 异常继承链：`RemoteDisconnected` = `ConnectionResetError`(→`ConnectionError`→`OSError`) + `http.client.BadStatusLine`(→`HTTPException`)
* 为什么没被接住：`fetch_raw_content` 的 except 只有 `HTTPError` 和 `(URLError, TimeoutError)`；`RemoteDisconnected` 两条都不属于 → 漏出
  * 根因在 urllib `do_open`：只对 `h.request()` 做了 `OSError→URLError` 包装，`h.getresponse()`（真正抛错处）不在保护内
* 冒泡路径：`_download_skill`(:244) → `fetch_raw_content` → 未 catch → `_download_batch` 的 `future.result()`(:682) 重抛 → 进程 exit 1
* rerun 证实非必然触发（run 28797563033 现为 completed success）

## Requirements (evolving)

* R1（治本）：`fetch_raw_content` 的重试循环要能接住 `RemoteDisconnected` 及同类瞬时连接错误，走已有的退避重试；重试仍失败则返回 `None`（与 404/超时同款降级），不抛
* R2（兜底）：`download_catalog._download_batch` 的 `future.result()` 包 try/except，任何未预料异常转成 `(name, False, err)` 错误元组 —— 保证单个 entry 永远不能杀死整批下载

## Acceptance Criteria (evolving)

* [ ] 模拟 `fetch_raw_content` 抓取时抛 `RemoteDisconnected`，函数不抛、重试后返回 `None`
* [ ] 模拟某个 downloader 抛任意异常，`_download_batch` 不崩，该 entry 计入 errors、其余 entry 正常完成
* [ ] `python -m pytest tests/ -v` 全绿
* [ ] 不改变正常路径行为（成功抓取、404 静默、429/5xx 退避均不变）

## Definition of Done

* 单元测试覆盖 R1 + R2 两条路径
* lint / 现有测试 CI 绿
* 提交遵循 `[fix] 中文描述` 原子化规范

## Out of Scope (explicit)

* 不改 CI workflow 的 timeout / retry 结构
* 不为 download_catalog 引入外部依赖（保持 stdlib 原则）
* 不动其它 sync 脚本的调用点（fetch_raw_content 是共享层，改它自然惠及全部调用方）
* 不做整体重试/断点续传架构改造（本任务只堵单点崩溃）

## Technical Notes

* `fetch_raw_content` 被全部 sync/download 脚本共享 → R1 是最广收益的修法，但需保证只**扩大**捕获范围、不改正常路径语义
* utils.py 当前 import：`from urllib.error import HTTPError, URLError`，无 `http.client` → R1 需 `import http.client`
* `TimeoutError`/`URLError`/`ConnectionError` 均为 `OSError` 子类；`http.client.HTTPException` 不是 OSError 而是独立 Exception
  → 建议第二个 except 扩为 `(URLError, TimeoutError, ConnectionError, http.client.HTTPException)`，同时覆盖 OSError 侧与 HTTPException 侧
* `_download_batch` 位于 `scripts/download_catalog.py:657`

## Decision (ADR-lite)

**Context**: 需要决定补丁范围（治本 vs 治本+兜底、是否加单测）。
**Decision**: R1 + R2 + 单测三者全做。R1 治本（fetch_raw_content 接住 RemoteDisconnected 走重试），
R2 兜底（_download_batch 保证单 entry 不杀整批），并为两条路径加单元测试。
**Consequences**: 一次根治，回归有保护；R1 改共享抓取层惠及全部 sync 脚本，需保证只扩大捕获、不改正常路径语义。
