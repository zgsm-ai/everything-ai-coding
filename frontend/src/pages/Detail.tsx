import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router'
import { useI18n } from '../hooks/useI18n'
import RadarChart from '../components/RadarChart'
import type { CatalogItem } from '../types'
import { buildInstallGuidance } from '../lib/installGuidance'

export default function Detail() {
  const { id } = useParams<{ id: string }>()
  const { t, lang } = useI18n()
  const [item, setItem] = useState<CatalogItem | null>(null)
  const [loading, setLoading] = useState(true)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    // Search across all type files to find the item
    Promise.all(
      ['mcp.json', 'skills.json', 'rules.json', 'prompts.json'].map(f =>
        fetch(`./api/${f}`).then(r => r.json())
      )
    ).then(arrays => {
      const all: CatalogItem[] = arrays.flat()
      const found = all.find(i => i.id === id)
      setItem(found || null)
      setLoading(false)
    }).catch(() => setLoading(false))
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
          {installGuidance?.kind === 'manual' && item.source_url && (
            <p className="text-sm text-gray-600 dark:text-gray-300">
              {t('detail.install.manual')}:{' '}
              <a href={item.source_url} target="_blank" rel="noreferrer" className="text-apple-blue hover:underline">
                README →
              </a>
            </p>
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
