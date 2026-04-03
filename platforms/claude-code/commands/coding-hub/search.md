---
description: '搜索 coding 资源（MCP/Skills/Rules/Prompts）。用法: /coding-hub:search <query>'
---

# Coding Hub - Search

$ARGUMENTS

---

## 数据处理（重要：用 Bash 预过滤，避免全量 JSON 进入上下文）

索引 URL: `https://zgsm-sangfor.github.io/costrict-coding-hub/api/v1/search-index.json`
Fallback URL: `https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/catalog/search-index.json`
本地备用: `/Volumes/Work/Projects/costrict-coding-hub/catalog/search-index.json`
单条 API: `https://zgsm-sangfor.github.io/costrict-coding-hub/api/v1/{type}/{id}.json`
全量索引 fallback: `https://raw.githubusercontent.com/zgsm-sangfor/costrict-coding-hub/main/catalog/index.json`

将搜索关键词和可选 type 过滤从 $ARGUMENTS 中提取后，用 Bash 执行预过滤。**注意：搜索命中结果不等于推荐，只有通过验证门的候选才可以被明确表述为“推荐”。**

1. 从 `$ARGUMENTS` 中提取搜索关键词和可选的类型过滤参数
   - 支持 `type:mcp`、`type:skill`、`type:rule`、`type:prompt` 过滤
   - 示例: `/coding-hub:search typescript type:mcp` — 只搜索 MCP 类型
   - 如果参数中包含 `type:<值>`，提取为过滤条件，剩余部分作为搜索关键词
2. 为 discovery 生成最多 3 组检索词：
   - **原始关键词**：用户输入的实际查询
   - **压缩关键词**：去掉“帮我、怎么、有没有、想找、请问”等虚词，保留“领域 + 任务”核心词
   - **备选同义词**：只在明显场景下添加一个轻量备选，如 `deploy → deployment/ci-cd/release/publish`、`pr review → code review/pull request review/review automation`、`readme → docs`
   - **禁止**为了好看而改写 install 目标；改写只用于 search 召回
   - **宽意图抑制规则**：如果 query 像“部署 / 上线 / 发版”这种头部宽意图，首屏优先保留“直接执行型”结果（部署流程、CI/CD、平台发布、上线操作）；把 changelog / release notes / 公告类结果默认降到补充区，除非 query 明确强调“发版说明/Release Notes”
3. 下载索引到临时文件: `curl -sf --compressed <索引 URL> -o "$TMPDIR/coding-hub-index.json"`
   - 如果 curl 失败，尝试 Fallback URL: `curl -sf --compressed <Fallback URL> -o "$TMPDIR/coding-hub-index.json"`
   - 如果仍失败，用本地备用路径 `/Volumes/Work/Projects/costrict-coding-hub/catalog/search-index.json`
4. 用 python 脚本过滤（跨平台：macOS/Linux 用 python3，Windows 用 python，探测命令 `$(command -v python3 || command -v python)`）:
   - 读取 JSON 文件
   - 在 `name`、`description`、`tags`、`tech_stack` 中搜索原始关键词与改写关键词（不区分大小写）
   - 如果指定了 type 过滤，先按 type 字段过滤
   - 先按匹配字段数排序，再按 stars 排序
   - 输出 top 15，每行格式: `id\tname\ttype\tcategory\tstars\tinstall_method\tsource_url\tdescription`（TSV 纯文本）
5. 从预过滤结果中选出前 3-5 个最可能的候选，用单条 API 获取详情做候选验证：
   - 优先请求 `https://.../api/v1/{type}/{id}.json`
   - 如果单条 API 失败，再回退到全量索引中按 `id` 精确筛选
   - 读取候选条目的 `source`、`evaluation`、`health`、`install`、`source_url`、`tags` 等字段，但只提取少量直接可用的信号
6. **候选验证门（必须执行）**
   - **禁止**仅凭搜索命中或 stars 就把结果称为“推荐”
   - 只有同时满足下面这条简化规则时，才可放入“优先候选”区：**至少 1 个可信信号 + 至少 1 个可执行信号**
   - 可信信号示例：官方/知名来源、curated、明显更高的质量/健康信号
   - 可执行信号示例：`install.method` 明确、单条 API 有可用安装信息
   - 如果做不到这条规则，就只能把结果称为“匹配结果”或“值得先看”的候选，不能称为“已验证推荐”或过度承诺
7. 将结果格式化为“优先候选 + 其他匹配结果”两层输出，而不是单表格平铺
   - 对宽意图 query，优先候选默认聚焦同一主方向，不要在首屏同时混入太多 adjacent categories

## 输出格式

```
## 搜索结果: "<query>"

检索词：原始=<original query>｜压缩=<reformulated query>｜备选=<fallback query or 无>

### 优先候选（仅展示通过候选验证门的结果；如果没有则写“暂无高置信候选”）

1. <名称>（<类型> / <分类>）
   - 为什么值得先看：<为什么和用户当前问题匹配>
   - 候选依据：<来源/质量/安装可行性中的简短可理解依据>
   - 下一步：`/coding-hub:install <名称>`

### 其他匹配结果

| # | 名称 | 类型 | 分类 | Stars | 安装方式 | 说明 |
|---|------|------|------|-------|----------|------|
| 1 | xxx  | MCP  | xxx  | 1234  | mcp_config | xxx |
```

8. 提示用户：
   - 如果存在优先候选："输入 `/coding-hub:install <名称>` 安装，或继续搜索更具体的关键词"
   - 如果没有高置信候选："我找到了若干匹配结果，但暂时没有足够高置信的优先候选。你可以继续细化关键词，或直接安装其中一个候选"
