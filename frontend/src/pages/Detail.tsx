import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router'
import { useI18n } from '../hooks/useI18n'
import RadarChart from '../components/RadarChart'
import McpInstallabilityBanner from '../components/McpInstallabilityBanner'
import SecurityBanner from '../components/SecurityBanner'
import type { CatalogItem, SearchIndexItem } from '../types'
import { buildInstallGuidance } from '../lib/installGuidance'

/**
 * Normalize a slim search-index entry into a render-safe CatalogItem. Used only
 * when the per-entry shard fetch could not supply the full record (missing
 * shard file / id not in shard). Every heavy field the Detail render path
 * touches (tags / tech_stack / description / category …) is defaulted so the
 * page renders a minimal card instead of crashing.
 */
function slimToFallbackItem(slim: SearchIndexItem): CatalogItem {
  return {
    id: slim.id,
    name: slim.name,
    type: slim.type as CatalogItem['type'],
    description: slim.snippet ?? '',
    source_url: '',
    stars: slim.stars,
    category: '',
    tags: [],
    tech_stack: [],
    source: slim.source ?? '',
    last_synced: '',
    final_score: slim.final_score ?? 0,
    decision: '',
    health: slim.freshness_label
      ? {
          score: 0,
          signals: { freshness: 0, popularity: 0, source_trust: 0 },
          freshness_label: slim.freshness_label,
        }
      : undefined,
  }
}

export default function Detail() {
  const { id } = useParams<{ id: string }>()
  const { t, lang } = useI18n()
  const [item, setItem] = useState<CatalogItem | null>(null)
  const [loading, setLoading] = useState(true)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!id) {
      setItem(null)
      setLoading(false)
      return
    }
    let cancelled = false
    setLoading(true)
    setItem(null)

    // 06-22 search-index perf refactor: Detail no longer pulls all 5 per-type
    // JSON files. Instead it reads the slim search-index once to learn this
    // id's shard, then fetches exactly that one per-entry shard
    // (api/entries/<shard>.json) and renders its full field set.
    //   1. search-index.json → slim entry (has `shard`)
    //   2. api/entries/<shard>.json → full entry by id (all heavy fields)
    //   3. fallback: if the shard is missing the id, render the slim entry's
    //      minimal fields (preserves the old "always show something" behavior).
    ;(async () => {
      try {
        const siRes = await fetch('./api/search-index.json')
        if (cancelled) return
        const index: SearchIndexItem[] = siRes.ok ? await siRes.json() : []
        if (cancelled) return
        const slim = index.find(i => i.id === id)

        if (!slim) {
          setItem(null)
          setLoading(false)
          return
        }

        // Fetch only the one shard this entry lives in.
        try {
          const shardRes = await fetch(`./api/entries/${slim.shard}.json`)
          if (cancelled) return
          if (shardRes.ok) {
            const shard: Record<string, CatalogItem> = await shardRes.json()
            if (cancelled) return
            const full = shard[id]
            if (full) {
              setItem(full)
              setLoading(false)
              return
            }
          }
        } catch {
          // shard fetch failed — fall through to slim fallback below
        }

        // Fallback: render the slim entry's minimal fields. Normalize into a
        // valid CatalogItem so the render path (which reads item.tags.length,
        // item.description, …) never hits an undefined heavy field.
        setItem(slimToFallbackItem(slim))
        setLoading(false)
      } catch {
        if (!cancelled) {
          setItem(null)
          setLoading(false)
        }
      }
    })()

    return () => {
      cancelled = true
    }
  }, [id])

  if (loading) {
    return (
      <div className="max-w-3xl mx-auto space-y-6">
        <div className="skeleton h-8 w-64" />
        <div className="skeleton h-4 w-full" />
        <div className="skeleton h-4 w-3/4" />
        <div className="glass rounded-2xl p-6 skeleton h-64" />
      </div>
    )
  }

  if (!item) {
    return (
      <div className="text-center py-20">
        <p className="text-gray-400 dark:text-gray-500 text-lg">Resource not found</p>
        <Link to="/browse" className="text-apple-blue mt-4 inline-block">{t('nav.browse')}</Link>
      </div>
    )
  }

  const desc = lang === 'zh' && item.description_zh ? item.description_zh : item.description
  const installGuidance = item.install ? buildInstallGuidance(item, lang) : null
  const TYPE_COLORS: Record<string, string> = {
    mcp: 'bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300',
    skill: 'bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-300',
    rule: 'bg-orange-100 text-orange-700 dark:bg-orange-900/50 dark:text-orange-300',
    prompt: 'bg-purple-100 text-purple-700 dark:bg-purple-900/50 dark:text-purple-300',
    plugin: 'bg-pink-100 text-pink-700 dark:bg-pink-900/50 dark:text-pink-300',
  }

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      {/* Header */}
      <div>
        <div className="flex items-center gap-3 mb-3 flex-wrap">
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${TYPE_COLORS[item.type] || 'bg-gray-100 dark:bg-gray-700'}`}>
            {item.type.toUpperCase()}
          </span>
          {item.stars != null && item.stars > 0 && (
            <span className="text-sm text-gray-400">⭐ {item.stars.toLocaleString()}</span>
          )}
          {item.source_url && (
            <a href={item.source_url} target="_blank" rel="noreferrer"
              className="text-sm text-apple-blue hover:underline">
              {t('detail.github')} →
            </a>
          )}
        </div>
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-3">{item.name}</h1>
        <p className="text-gray-600 dark:text-gray-300 leading-relaxed">{desc}</p>
      </div>

      {/* Metadata chips */}
      <div className="flex flex-wrap gap-2">
        {item.category && (
          <span className="text-xs px-2.5 py-1 rounded-full bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300 font-medium">
            {item.category}
          </span>
        )}
        {item.source && (
          <span className="text-xs px-2.5 py-1 rounded-full bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400">
            {t('detail.source')}: {item.source}
          </span>
        )}
        {item.health?.freshness_label && (
          <span className={`text-xs px-2.5 py-1 rounded-full ${
            item.health.freshness_label === 'active' ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-300' :
            item.health.freshness_label === 'recent' ? 'bg-sky-100 text-sky-700 dark:bg-sky-900/50 dark:text-sky-300' :
            'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'
          }`}>
            {item.health.freshness_label}
          </span>
        )}
        {item.health?.last_commit && (
          <span className="text-xs px-2.5 py-1 rounded-full bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400">
            {t('detail.lastCommit')}: {new Date(item.health.last_commit).toLocaleDateString()}
          </span>
        )}
      </div>

      {/* Tags */}
      {item.tags.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">{t('detail.tags')}</h3>
          <div className="flex flex-wrap gap-1.5">
            {item.tags.map(tag => (
              <span key={tag} className="text-xs px-2 py-0.5 rounded-full bg-blue-50 text-blue-600 dark:bg-blue-900/40 dark:text-blue-300">
                {tag}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Tech stack */}
      {item.tech_stack && item.tech_stack.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">{t('detail.techStack')}</h3>
          <div className="flex flex-wrap gap-1.5">
            {item.tech_stack.map(tech => (
              <span key={tech} className="text-xs px-2 py-0.5 rounded-full bg-violet-50 text-violet-600 dark:bg-violet-900/40 dark:text-violet-300">
                {tech}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Security review banner (any type — only renders when entry has been scanned) */}
      <SecurityBanner item={item} />

      {/* Plugin bundle: skills/agents/commands/mcp_servers/hooks inside this plugin */}
      {item.type === 'plugin' && item.bundle && (
        item.bundle.skills_count > 0 ||
        item.bundle.agents_count > 0 ||
        item.bundle.commands_count > 0 ||
        item.bundle.mcp_servers_count > 0 ||
        (item.bundle.hooks_count ?? 0) > 0
      ) && (
        <div className="glass rounded-2xl p-6">
          <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-4">
            🧩 {lang === 'zh' ? '插件包内容' : 'Plugin Bundle'}
          </h3>
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-4">
            {item.bundle.skills_count > 0 && (
              <div className="rounded-xl bg-pink-50 dark:bg-pink-900/30 px-4 py-3">
                <div className="text-2xl font-bold text-pink-700 dark:text-pink-300">{item.bundle.skills_count}</div>
                <div className="text-xs text-pink-600/80 dark:text-pink-400/80">{lang === 'zh' ? '技能' : 'Skills'}</div>
              </div>
            )}
            {item.bundle.agents_count > 0 && (
              <div className="rounded-xl bg-purple-50 dark:bg-purple-900/30 px-4 py-3">
                <div className="text-2xl font-bold text-purple-700 dark:text-purple-300">{item.bundle.agents_count}</div>
                <div className="text-xs text-purple-600/80 dark:text-purple-400/80">{lang === 'zh' ? '代理' : 'Agents'}</div>
              </div>
            )}
            {item.bundle.commands_count > 0 && (
              <div className="rounded-xl bg-blue-50 dark:bg-blue-900/30 px-4 py-3">
                <div className="text-2xl font-bold text-blue-700 dark:text-blue-300">{item.bundle.commands_count}</div>
                <div className="text-xs text-blue-600/80 dark:text-blue-400/80">{lang === 'zh' ? '命令' : 'Commands'}</div>
              </div>
            )}
            {item.bundle.mcp_servers_count > 0 && (
              <div className="rounded-xl bg-emerald-50 dark:bg-emerald-900/30 px-4 py-3">
                <div className="text-2xl font-bold text-emerald-700 dark:text-emerald-300">{item.bundle.mcp_servers_count}</div>
                <div className="text-xs text-emerald-600/80 dark:text-emerald-400/80">MCP</div>
              </div>
            )}
            {(item.bundle.hooks_count ?? 0) > 0 && (
              <div className="rounded-xl bg-amber-50 dark:bg-amber-900/30 px-4 py-3">
                <div className="text-2xl font-bold text-amber-700 dark:text-amber-300">{item.bundle.hooks_count}</div>
                <div className="text-xs text-amber-600/80 dark:text-amber-400/80">{lang === 'zh' ? '钩子' : 'Hooks'}</div>
              </div>
            )}
          </div>
          {item.bundle.skills_namespaces && item.bundle.skills_namespaces.length > 0 && (
            <div className="mb-3">
              <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-2">
                {lang === 'zh' ? '内含技能' : 'Bundled skills'}
              </h4>
              <div className="flex flex-wrap gap-1.5">
                {item.bundle.skills_namespaces.map((ns, idx) => {
                  const skillName = ns.includes(':') ? ns.split(':', 2)[1] : ns
                  const skillId = item.bundle?.bundled_skill_ids?.[idx]
                  if (skillId) {
                    return (
                      <Link
                        key={ns}
                        to={`/detail/${skillId}`}
                        className="text-xs px-2 py-0.5 rounded-full bg-pink-50 text-pink-700 dark:bg-pink-900/40 dark:text-pink-300 font-mono hover:underline"
                      >
                        {skillName}
                      </Link>
                    )
                  }
                  return (
                    <span key={ns} className="text-xs px-2 py-0.5 rounded-full bg-pink-50 text-pink-700 dark:bg-pink-900/40 dark:text-pink-300 font-mono">
                      {skillName}
                    </span>
                  )
                })}
              </div>
            </div>
          )}
          {item.bundle.mcp_server_names && item.bundle.mcp_server_names.length > 0 && (
            <div className="mb-3">
              <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-2">
                {lang === 'zh' ? '内含 MCP 服务' : 'Bundled MCP servers'}
              </h4>
              <div className="flex flex-wrap gap-1.5">
                {item.bundle.mcp_server_names.map(name => (
                  <span key={name} className="text-xs px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300 font-mono">
                    {name}
                  </span>
                ))}
              </div>
            </div>
          )}
          {item.bundle.hook_events && item.bundle.hook_events.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-2">
                {lang === 'zh' ? '触发事件' : 'Hook events'}
              </h4>
              <div className="flex flex-wrap gap-1.5">
                {item.bundle.hook_events.map(evt => (
                  <span key={evt} className="text-xs px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300 font-mono">
                    {evt}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Bundled-in indicator: this skill is bundled by a plugin */}
      {item.type === 'skill' && item.bundled_in && (
        <div className="glass rounded-2xl p-4 flex items-center gap-3">
          <span className="text-xl">🧩</span>
          <div className="flex-1 text-sm text-gray-600 dark:text-gray-300">
            {lang === 'zh' ? '此技能被插件捆绑：' : 'Bundled in plugin: '}
            <Link to={`/detail/${item.bundled_in}`} className="text-apple-blue hover:underline font-medium">
              {item.bundled_in}
            </Link>
          </div>
        </div>
      )}

      {/* Health Radar */}
      {item.health?.signals && (
        <div className="glass rounded-2xl p-6">
          <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-4">{t('detail.health')}</h3>
          <div className="flex justify-center">
            <RadarChart signals={item.health.signals} />
          </div>
        </div>
      )}

      {/* Evaluation */}
      {item.evaluation && (
        <div className="glass rounded-2xl p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">{t('detail.evaluation')}</h3>
            {item.evaluation.final_score > 0 && (
              <span className="text-lg font-bold text-apple-blue">{Math.round(item.evaluation.final_score)}</span>
            )}
          </div>
          <div className="space-y-3">
            {(['coding_relevance', 'doc_completeness', 'desc_accuracy', 'writing_quality', 'specificity', 'install_clarity'] as const).map(dim => {
              const val = item.evaluation![dim]
              if (val == null) return null
              return (
                <div key={dim} className="flex items-center gap-3">
                  <span className="text-xs text-gray-500 dark:text-gray-400 w-32 shrink-0">{t(`eval.${dim}`)}</span>
                  <div className="flex gap-1 flex-1">
                    {[1, 2, 3, 4, 5].map(i => (
                      <div
                        key={i}
                        className={`h-2 flex-1 rounded-full ${
                          i <= val ? 'bg-apple-blue' : 'bg-gray-200 dark:bg-gray-600'
                        }`}
                      />
                    ))}
                  </div>
                  <span className="text-xs text-gray-400 dark:text-gray-500 w-4">{val}</span>
                </div>
              )
            })}
          </div>
          {item.evaluation.evaluated_at && (
            <p className="text-xs text-gray-400 dark:text-gray-500 mt-4">
              {t('eval.evaluator')}: {item.evaluation.model_id === '__cached__' ? 'deepseek-chat' : (item.evaluation.model_id || 'unknown')} · {new Date(item.evaluation.evaluated_at).toLocaleDateString()}
            </p>
          )}
        </div>
      )}

      {/* Install guidance */}
      {item.install && (
        <div className="glass rounded-2xl p-6">
          <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-4">{t('detail.install')}</h3>
          {/* MCP installability pre-check: only renders when type=mcp + entry has install_state */}
          {item.type === 'mcp' && <McpInstallabilityBanner item={item} />}
          {installGuidance?.kind === 'mcp_config' && item.install.config && (
            <div className="relative">
              <pre className="bg-gray-900 text-gray-100 rounded-xl p-4 text-xs overflow-x-auto">
                {JSON.stringify(item.install.config, null, 2)}
              </pre>
              <button
                onClick={() => handleCopy(JSON.stringify(item.install!.config, null, 2))}
                className="absolute top-2 right-2 px-2 py-1 rounded-lg bg-white/10 text-white text-xs hover:bg-white/20 border-none cursor-pointer"
              >
                {copied ? t('detail.install.copied') : t('detail.install.copy')}
              </button>
            </div>
          )}
          {installGuidance?.kind === 'skill_extract' && (
            <div className="space-y-3">
              <p className="text-sm text-gray-600 dark:text-gray-300">
                {t('detail.install.skillExtract')}
              </p>
              {installGuidance.sourceUrl && (
                <p className="text-xs text-gray-500 dark:text-gray-400 break-all">
                  {t('detail.install.sourcePathLabel')}:{' '}
                  <a href={installGuidance.sourceUrl} target="_blank" rel="noreferrer" className="text-apple-blue hover:underline">
                    {installGuidance.sourceUrl}
                  </a>
                </p>
              )}
              <p className="text-xs text-gray-400 dark:text-gray-500">
                {t('detail.install.skillExtractHint')}
              </p>
            </div>
          )}
          {installGuidance?.kind === 'git_clone' && item.install.repo && (
            <div className="relative">
              <pre className="bg-gray-900 text-gray-100 rounded-xl p-4 text-xs overflow-x-auto">
                {installGuidance.copyText}
              </pre>
              <button
                onClick={() => handleCopy(installGuidance.copyText)}
                className="absolute top-2 right-2 px-2 py-1 rounded-lg bg-white/10 text-white text-xs hover:bg-white/20 border-none cursor-pointer"
              >
                {copied ? t('detail.install.copied') : t('detail.install.copy')}
              </button>
            </div>
          )}
          {installGuidance?.kind === 'plugin_marketplace' && (
            <div className="space-y-3">
              <p className="text-sm text-gray-600 dark:text-gray-300">
                {lang === 'zh'
                  ? '在 Claude Code 中依次执行以下两条 slash 命令：'
                  : 'Run these two slash commands in Claude Code:'}
              </p>
              <div className="relative">
                <pre className="bg-gray-900 text-gray-100 rounded-xl p-4 text-xs overflow-x-auto whitespace-pre-wrap break-all leading-relaxed">{installGuidance.copyText}</pre>
                <button
                  onClick={() => handleCopy(installGuidance.copyText)}
                  className="absolute top-2 right-2 px-2 py-1 rounded-lg bg-white/10 text-white text-xs hover:bg-white/20 border-none cursor-pointer"
                >
                  {copied ? t('detail.install.copied') : t('detail.install.copy')}
                </button>
              </div>
              <div className="text-xs text-gray-500 dark:text-gray-400 space-y-1">
                <p>
                  <span className="font-medium">{lang === 'zh' ? '步骤 1' : 'Step 1'}:</span>{' '}
                  {lang === 'zh' ? '注册 marketplace ' : 'Register marketplace '}
                  <code className="bg-gray-100 dark:bg-gray-700 px-1.5 py-0.5 rounded font-mono">{installGuidance.marketplace}</code>
                </p>
                <p>
                  <span className="font-medium">{lang === 'zh' ? '步骤 2' : 'Step 2'}:</span>{' '}
                  {lang === 'zh' ? '安装 plugin ' : 'Install plugin '}
                  <code className="bg-gray-100 dark:bg-gray-700 px-1.5 py-0.5 rounded font-mono">{installGuidance.pluginName}</code>
                </p>
              </div>
              {item.source_url && (
                <p className="text-xs text-gray-400 dark:text-gray-500">
                  {lang === 'zh' ? '源码：' : 'Source: '}
                  <a href={item.source_url} target="_blank" rel="noreferrer" className="text-apple-blue hover:underline break-all">
                    {item.source_url}
                  </a>
                </p>
              )}
            </div>
          )}
          {installGuidance?.kind === 'manual' && item.source_url && (
            <p className="text-sm text-gray-600 dark:text-gray-300">
              {t('detail.install.manual')}:{' '}
              <a href={item.source_url} target="_blank" rel="noreferrer" className="text-apple-blue hover:underline">
                README →
              </a>
            </p>
          )}
          {installGuidance?.kind === 'plugin_unverified' && (
            <div className="space-y-2 rounded-xl border border-amber-300 bg-amber-50 dark:border-amber-700 dark:bg-amber-900/30 p-4">
              <p className="text-sm font-medium text-amber-900 dark:text-amber-200">
                {lang === 'zh' ? '⚠️ marketplace 元数据未验证' : '⚠️ Marketplace metadata not verified'}
              </p>
              <p className="text-xs text-amber-800 dark:text-amber-300">
                {installGuidance.reason === 'missing_fields'
                  ? lang === 'zh'
                    ? '该 plugin 缺少安装所需的 marketplace 字段，可能是 catalog 数据陈旧或上游未发布有效 marketplace.json。'
                    : "This plugin is missing required marketplace fields. Catalog data may be stale, or the upstream hasn't published a valid marketplace.json."
                  : lang === 'zh'
                    ? '我们没能在该 plugin 的 marketplace.json 中找到匹配的 plugin 条目。自动安装不可用，请参考源仓库说明。'
                    : "We couldn't find a matching entry in this plugin's marketplace.json. Automated install is unavailable — please refer to the upstream source for instructions."}
              </p>
              {item.source_url && (
                <p className="text-xs">
                  <a href={item.source_url} target="_blank" rel="noreferrer" className="text-apple-blue hover:underline break-all">
                    {item.source_url} →
                  </a>
                </p>
              )}
            </div>
          )}
          {installGuidance?.kind === 'download_file' && item.install.files && item.install.files.length > 0 && (() => {
            return (
              <div>
                <p className="text-sm text-gray-600 dark:text-gray-300 mb-2">
                  {lang === 'zh' ? '下载到项目规则目录：' : 'Download to project rules directory:'}
                </p>
                <p className="text-xs text-gray-400 dark:text-gray-500 mb-3">
                  {lang === 'zh' ? '目标路径' : 'Target'}: <code className="bg-gray-100 dark:bg-gray-700 px-1.5 py-0.5 rounded">{installGuidance.targetFile}</code>
                </p>
                <div className="relative">
                  <pre className="bg-gray-900 text-gray-100 rounded-xl p-4 text-xs overflow-x-auto whitespace-pre-wrap break-all">
                    {installGuidance.copyText}
                  </pre>
                  <button
                    onClick={() => handleCopy(installGuidance.copyText)}
                    className="absolute top-2 right-2 px-2 py-1 rounded-lg bg-white/10 text-white text-xs hover:bg-white/20 border-none cursor-pointer"
                  >
                    {copied ? t('detail.install.copied') : t('detail.install.copy')}
                  </button>
                </div>
                {lang === 'zh'
                  ? <p className="text-xs text-gray-400 dark:text-gray-500 mt-2">全局安装可改为 <code className="bg-gray-100 dark:bg-gray-700 px-1.5 py-0.5 rounded">~/.claude/rules/{item.id}.md</code></p>
                  : <p className="text-xs text-gray-400 dark:text-gray-500 mt-2">For global install, use <code className="bg-gray-100 dark:bg-gray-700 px-1.5 py-0.5 rounded">~/.claude/rules/{item.id}.md</code></p>
                }
              </div>
            )
          })()}
        </div>
      )}
    </div>
  )
}
