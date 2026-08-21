# build_registry_manifest.py

从 `catalog/index.json` 生成按原始 GitHub 仓库归组的声明式快照 `dist/registry-manifest.json`。产物只声明仓库来源、仓根能力身份、评分和安全事实，不携带能力内容。

它与 `catalog-bundle.tar.gz` 双轨发布，互不替代。bundle 继续承载历史内容搬运链路，registry manifest 面向仓根 discovery + 全量 reconcile 链路。

## 使用

```bash
# 默认输出到 dist/registry-manifest.json
python3 scripts/build_registry_manifest.py

# 自定义输出路径
python3 scripts/build_registry_manifest.py --output /tmp/registry-manifest.json

# 生成后按仓重新投影 catalog，并打印 R2c/R2d 对账统计
python3 scripts/build_registry_manifest.py --verify
```

`--verify` 会重做仓归组并逐字段比较产物，检查 schema、source、0-100 分数、security 四态、重复 ID 和 `subdir=null`，同时打印 N/M/K、丢弃条目数、不可归组条目数、仓覆盖率、新旧 type、四档 verdict、缺 `evaluated_at` 数和 R2c 不聚合统计。

## 产物契约 v1

```json
{
  "schema_version": 1,
  "generated_at": "2026-08-20T12:00:00Z",
  "entries": [
    {
      "catalog_id": "example-plugin",
      "type": "plugin",
      "slug": "example-plugin",
      "source": {
        "url": "https://github.com/example/plugin",
        "sha": null,
        "subdir": null,
        "ref": "main",
        "evaluated_at": "2026-08-20T10:30:00Z"
      },
      "eval": {
        "final_score": 87,
        "llm_score": 90,
        "health_score": 70,
        "security": {
          "verdict": "pass",
          "scanned_at": "2026-08-20T10:35:00Z",
          "reasons": []
        }
      }
    }
  ]
}
```

`schema_version` 当前固定为 `1`。manifest 是仓库级全量快照，不按 security verdict 过滤；`reject` 仍出现，由下游策略决定是否阻断。

## 仓归组

1. 优先从 `source_url` 还原原始 GitHub 仓根；不可用时依次回退 `install.repo`、`bundle.source_repo`、`install.marketplace_repo`。
2. URL 统一为 `https://github.com/<owner>/<repo>`，以大小写不敏感的仓根为分组键。
3. 使用 `source_path`、`install.path/files`、plugin `bundle.plugin_root/plugin_json_path` 和 URL tree/blob/raw 路径判定条目是否位于仓根。
4. 仓内存在根 manifest 候选才出一条；按下表 precedence 选代表条目并决定 type，其余条目收拢。
5. 没有根身份的纯聚合仓整组不输出；无法证明 GitHub 仓根的 catalog 条目单列为 ungroupable，不猜 URL。
6. 输出 `source.subdir` 正常恒为 `null`。当前契约保留该字段只是为了异常兼容，不把嵌套子项重新发成独立条目。

### 根 manifest precedence

下表顺序是契约。仓根同时命中多个文件时，靠前者决定 type：

| 优先级 | 根文件 | type |
|---:|---|---|
| 1 | `.claude-plugin/plugin.json` | `plugin` |
| 2 | `plugin.json` | `plugin` |
| 3 | `SKILL.md` | `skill` |
| 4 | `.mcp.json` | `mcp` |
| 5 | `RULE.md` | `rule` |
| 6 | `PROMPT.md` | `prompt` |
| 7 | `COMMAND.md` | `command` |
| 8 | `AGENT.md` | `subagent` |
| 9 | `TEMPLATE.md` | `template` |

Plugin 必须满足至少一项：`bundle.plugin_json_path` 精确命中上述 plugin 文件；`bundle.plugin_root == ""`；或 `install.marketplace_verified == true`。未验证、没有根路径证据的 registry plugin 壳不构成根身份。

同一根文件对应多个 catalog 条目时，这不属于文件 precedence 平手：代表条目按 `source_priority` 降序、`catalog_id` 字典序、原 catalog 顺序依次决胜。manifest 的仓顺序按该仓第一次出现在 catalog 的顺序保持稳定。

## 字段来源

| manifest 字段 | 上游来源 | 转换规则 |
|---|---|---|
| `schema_version` | 脚本常量 | 固定 `1` |
| `generated_at` | 构建时钟 | UTC 秒级 ISO-8601 |
| `catalog_id` | 根代表条目 `id` | 原样透传；归仓会消除同仓子项和 `cosknow` 同仓重复 |
| `type` | 根 manifest precedence | 不由仓内子项多数票决定 |
| `slug` | 根代表条目 `slug` | 缺失时使用稳定 `id`，不从 name 推导 |
| `source.url` | 规范化原始仓 | 禁止 `gitea.costrict.ai` 与 `costrict-plugin-marketplace` 镜像 |
| `source.sha` | 顶层 `source_sha` 或 `evaluation.source_sha` | OPTIONAL；仅接受 40/64 位 Git SHA，没有则 `null` |
| `source.subdir` | 仓级输出 | 正常恒为 `null` |
| `source.ref` | `install.branch` / URL tree ref / `bundle.source_ref` | `HEAD` 视为未知，填 `null` |
| `source.evaluated_at` | 根代表条目 `evaluation.evaluated_at` | 语义最接近“本轮质量评估发生时刻”；缺失不拿推送/安全扫描时间冒充，填 `null` 并由 verify 计数 |
| `eval.final_score` | 根代表条目顶层 `final_score` | 0-100 原值透传，缺失 `null` |
| `eval.llm_score` | 根代表条目 `evaluation.content_quality` | 0-100 原值透传，缺失 `null`，不从 final_score 反推 |
| `eval.health_score` | `health.effective_score`，回退 `health.score` | 0-100 原值透传，缺失 `null` |
| `eval.security.verdict` | 根代表条目 `security.verdict` | `safe -> pass`、`caution -> warn`、`reject -> reject`；无 security 块为 `unscanned` |
| `eval.security.scanned_at` | `security.scanned_at` | 已扫原样透传；未扫为 `null` |
| `eval.security.reasons` | `security.red_flags` | 仅保留字符串；未扫为 `[]`，不伪造 unavailable reason |

## R2c：评分不聚合

代表条目有仓级/plugin 级评分时原样使用。只有子项有分时选择“不填”：根条目对应字段保持 `null`，不做 min/mean，也不从其他字段反推。

理由是子项分数衡量的是不同能力文件，min 会把最差子项当成整仓结论，mean 会让子项数量和重复镜像改变整仓分数；两者都会产生上游没有给出的新事实。`--verify` 同时打印实际聚合条目数（固定 0）和“子项有值但根字段仍保持 null”的影响面。

Security 同样不聚合。根条目未扫描时，即使某些子项已扫描，仓级事实仍为 `unscanned`。

## R2d：仓级对账口径

- `N`：有根身份、最终输出的仓数，也就是 manifest `entries` 数。
- `M`：这些已收录仓中除代表条目外被收拢的 catalog 条目数；包含嵌套子项和同仓较低 precedence 的根候选。
- `K`：能证明 GitHub 仓根、但没有根身份候选而整组丢弃的聚合仓数；另报它们原本包含的 catalog 条目数。
- `ungroupable`：连原始 GitHub 仓根都不能证明的条目，不混入 `K`。
- 仓覆盖率：`N / (N + K) * 100%`。分母只含可证明仓根的 repo group；ungroupable 没有 repo 身份，单列而不伪装成仓。
- 总量恒等式：`input catalog items = N + M + discarded group items + ungroupable items`。
- type 新旧表：old 按输入 catalog 条目计数；new 按 precedence 选出的仓代表计数。

该覆盖率回答“可证明的仓里有多少能进入仓根 discovery”，不是原始子项保留率，也不是 security 扫描覆盖率。旧的 `subdir=null / catalog 总条目` 文件粒度口径不再使用。

## source.sha 的已知缺口

当前 catalog 没有记录“本轮评分所依据源仓 commit”。`security.content_hash` 是内容 SHA-256，`pushed_at`、`health.last_commit`、`scanned_at`、`evaluated_at` 都是时间，不能写进 Git SHA 字段。

下期应在 fetch/eval 边界先解析不可变 commit，再按该 SHA 下载、评分并持久化 `evaluation.source_sha`。本期脚本只透传已有明确 SHA，不做 resolve-then-download。

## 消费方式

1. 下载 release 附件 `registry-manifest.json`，校验 release notes 或 webhook 中的 SHA-256。
2. 校验 `schema_version == 1`；未知版本停止消费。
3. 按仓级 `catalog_id` 与下游状态做全量 diff，缺失 ID 进入退场流程。
4. 使用同一套 root manifest precedence 预览和发现仓根能力；若 consumer precedence 不一致，停止上线并同步契约。
5. 分数按 0-100 使用；security 四态只表达上游事实，策略层自行决定 `warn/reject/unscanned` 的行为。
6. `source.sha=null` 表示本期没有不可变 commit 锚，不能伪装成 commit-pinned 同步。

GitHub Release 稳定下载地址：

```text
https://github.com/<owner>/<repo>/releases/download/<release-tag>/registry-manifest.json
```

配置 `COSTRICT_MANIFEST_WEBHOOK_URL` 与 `COSTRICT_MANIFEST_WEBHOOK_SECRET` 后，release workflow 会发送 HMAC-SHA256 签名的全量 reconcile 通知；未配置时发送步骤跳过。

## 故障

| 现象 | 原因 | 修法 |
|---|---|---|
| `unsupported type` | catalog 新增了 v1 未声明类型 | 明确新类型与 root manifest 后同步生产者/消费者 |
| `unsupported security verdict` | 上游 security 枚举变化 | 先明确语义再改映射，不静默降级 |
| `missing evaluated_at` 非 0 | 根代表条目缺 `evaluation.evaluated_at` | 上游补真实评估时刻；不能拿 `pushed_at` 或 `scanned_at` 代替 |
| ungroupable 非 0 | 现有字段不能证明原始 GitHub 仓 | sync 层持久化原始 repo，不在 manifest 阶段猜测 |
| duplicate `catalog_id` | 不同仓仍共享同一稳定 ID | 构建 fail-closed，在 catalog identity 层修复 |
| root manifest 统计突变 | 上游路径字段或 consumer precedence 漂移 | 对照 precedence 表和丢弃组样本后再发布 |
