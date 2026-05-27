import { useEffect, useState } from 'react'
import { useI18n } from '../hooks/useI18n'

/* ── Pipeline step SVG icons ── */
function SyncIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21.5 2v6h-6" />
      <path d="M2.5 22v-6h6" />
      <path d="M2.77 15.25A9 9 0 0 0 21.5 8" />
      <path d="M21.23 8.75A9 9 0 0 0 2.5 16" />
    </svg>
  )
}

function LayersIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2 2 7l10 5 10-5-10-5Z" />
      <path d="m2 17 10 5 10-5" />
      <path d="m2 12 10 5 10-5" />
    </svg>
  )
}

function SparklesIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z" />
      <path d="M20 3v4" />
      <path d="M22 5h-4" />
    </svg>
  )
}

function GaugeIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="m12 14 4-4" />
      <path d="M3.34 19a10 10 0 1 1 17.32 0" />
    </svg>
  )
}

/* ── Health signal SVG icons ── */
function StarIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
    </svg>
  )
}

function ClockIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <polyline points="12 6 12 12 16 14" />
    </svg>
  )
}

function CheckIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20 6L9 17l-5-5" />
    </svg>
  )
}

function TargetIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <circle cx="12" cy="12" r="6" />
      <circle cx="12" cy="12" r="2" />
    </svg>
  )
}

// 数据源 / 信任分级两个区块的数据由后端 scripts/source_registry.py 生成到
// frontend/public/api/sources.json（join catalog 实时 count），前端只渲染。
// 过去这里是手敲常量，源演进后会漂移（曾把 antigravity-skills 指到已删的
// antigravities/... 404 库）——改 fetch 后由 sync 管线保证与真实源一致。
type SourceItem = { slug: string; name: string; url: string; type: string; trust: number; count: number }
type TierItem = { score: number; label: string; color: string; sources: string[] }

const TYPE_BADGE: Record<string, string> = {
  MCP: 'bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300',
  Skills: 'bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-300',
  Rules: 'bg-orange-100 dark:bg-orange-900/40 text-orange-700 dark:text-orange-300',
  Prompts: 'bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300',
  Plugins: 'bg-pink-100 dark:bg-pink-900/40 text-pink-700 dark:text-pink-300',
}

function TrustDot({ score }: { score: number }) {
  const colors = ['#ff453a', '#ff453a', '#ff9f0a', '#0071e3', '#30d158']
  return (
    <span className="flex gap-0.5 items-center">
      {[1, 2, 3, 4, 5].map(d => (
        <span
          key={d}
          className="inline-block w-2 h-2 rounded-full"
          style={{ backgroundColor: d <= score ? colors[score - 1] : 'rgba(128,128,128,0.2)' }}
        />
      ))}
    </span>
  )
}

function WeightBar({ label, weight, color }: { label: string; weight: number; color: string }) {
  return (
    <div className="flex items-center gap-3">
      <span className="text-xs text-gray-500 dark:text-gray-400 w-36 shrink-0">{label}</span>
      <div className="flex-1 bg-gray-200/60 dark:bg-white/10 rounded-full h-1.5 overflow-hidden">
        <div className="h-1.5 rounded-full" style={{ width: `${weight * 2}%`, backgroundColor: color }} />
      </div>
      <span className="text-xs font-semibold tabular-nums text-gray-700 dark:text-gray-200 w-8 text-right">{weight}%</span>
    </div>
  )
}

export default function About() {
  const { t, lang } = useI18n()

  const [sources, setSources] = useState<SourceItem[]>([])
  const [tiers, setTiers] = useState<TierItem[]>([])

  useEffect(() => {
    fetch('./api/sources.json')
      .then(r => (r.ok ? r.json() : { sources: [], tiers: [] }))
      .then(d => {
        setSources(d.sources || [])
        setTiers(d.tiers || [])
      })
      .catch(() => {})
  }, [])

  const pipelineSteps = [
    {
      icon: <SyncIcon />,
      bg: 'bg-blue-50 dark:bg-blue-500/10',
      text: 'text-blue-600 dark:text-blue-400',
      labelKey: 'about.pipeline.step1.label',
      descKey: 'about.pipeline.step1.desc',
    },
    {
      icon: <LayersIcon />,
      bg: 'bg-violet-50 dark:bg-violet-500/10',
      text: 'text-violet-600 dark:text-violet-400',
      labelKey: 'about.pipeline.step2.label',
      descKey: 'about.pipeline.step2.desc',
    },
    {
      icon: <SparklesIcon />,
      bg: 'bg-amber-50 dark:bg-amber-500/10',
      text: 'text-amber-600 dark:text-amber-400',
      labelKey: 'about.pipeline.step3.label',
      descKey: 'about.pipeline.step3.desc',
    },
    {
      icon: <GaugeIcon />,
      bg: 'bg-emerald-50 dark:bg-emerald-500/10',
      text: 'text-emerald-600 dark:text-emerald-400',
      labelKey: 'about.pipeline.step4.label',
      descKey: 'about.pipeline.step4.desc',
    },
  ]

  const mcpWeights = [
    { label: 'Coding Relevance', weight: 25, color: '#0071e3' },
    { label: 'Doc Completeness', weight: 20, color: '#34aadc' },
    { label: 'Desc Accuracy',    weight: 15, color: '#5ac8fa' },
    { label: 'Writing Quality',  weight: 15, color: '#30d158' },
    { label: 'Specificity',      weight: 15, color: '#64d2ff' },
    { label: 'Install Clarity',  weight: 10, color: '#ff9f0a' },
  ]

  const ruleWeights = [
    { label: 'Coding Relevance', weight: 28, color: '#0071e3' },
    { label: 'Doc Completeness', weight: 22, color: '#34aadc' },
    { label: 'Desc Accuracy',    weight: 17, color: '#5ac8fa' },
    { label: 'Writing Quality',  weight: 17, color: '#30d158' },
    { label: 'Specificity',      weight: 16, color: '#64d2ff' },
  ]

  // Plugin 用 5 维（剔除 install_clarity — marketplace 安装统一是
  // /plugin install <name> 流程，该维度对 plugin 是噪声）。0.10 权重并入
  // doc_completeness（区分度最高的维度）。详见 plugin.yaml v2 注释。
  const pluginWeights = [
    { label: 'Coding Relevance', weight: 25, color: '#0071e3' },
    { label: 'Doc Completeness', weight: 30, color: '#34aadc' },
    { label: 'Desc Accuracy',    weight: 15, color: '#5ac8fa' },
    { label: 'Writing Quality',  weight: 15, color: '#30d158' },
    { label: 'Specificity',      weight: 15, color: '#64d2ff' },
  ]

  // Default health weights (mcp/skill/rule/prompt 共用 freshness 0.30 +
  // popularity 0.30 + source_trust 0.40)。Plugin 走 30/30/30/10 + 第 4 维
  // manifest_completeness（plugin.json 字段完整度阶梯 0/0.3/0.7/1.0）。
  const healthSignals = [
    { icon: <ClockIcon />,   bg: 'bg-sky-50 dark:bg-sky-500/10',       text: 'text-sky-600 dark:text-sky-400',       labelKey: 'about.signal.freshness',     descKey: 'about.signal.freshness.desc',     weight: 30 },
    { icon: <StarIcon />,    bg: 'bg-amber-50 dark:bg-amber-500/10',   text: 'text-amber-600 dark:text-amber-400',   labelKey: 'about.signal.popularity',    descKey: 'about.signal.popularity.desc',    weight: 30 },
    { icon: <TargetIcon />,  bg: 'bg-violet-50 dark:bg-violet-500/10', text: 'text-violet-600 dark:text-violet-400', labelKey: 'about.signal.sourceTrust',   descKey: 'about.signal.sourceTrust.desc',   weight: 40 },
    { icon: <CheckIcon />,   bg: 'bg-pink-50 dark:bg-pink-500/10',     text: 'text-pink-600 dark:text-pink-400',     labelKey: 'about.signal.manifestCompleteness',     descKey: 'about.signal.manifestCompleteness.desc',     weight: 10, pluginOnly: true },
  ]

  const thresholds = [
    { labelKey: 'about.decision.accept', score: '≥ 65', color: '#30d158', ring: 'ring-green-500/30',  bg: 'bg-green-500/8 dark:bg-green-500/12'  },
    { labelKey: 'about.decision.review', score: '50 – 64', color: '#ff9f0a', ring: 'ring-yellow-500/30', bg: 'bg-yellow-500/8 dark:bg-yellow-500/12' },
    { labelKey: 'about.decision.reject', score: '< 50',  color: '#ff453a', ring: 'ring-red-500/30',   bg: 'bg-red-500/8 dark:bg-red-500/12'       },
  ]

  return (
    <div className="max-w-3xl mx-auto space-y-10 pb-16">

      {/* ── Hero ── */}
      <div className="text-center space-y-4 pt-4">
        <h1 className="text-4xl font-bold text-gray-900 dark:text-white tracking-tight">
          {t('about.title')}
        </h1>
        <p className="text-gray-500 dark:text-gray-400 text-base leading-relaxed max-w-xl mx-auto">
          {t('about.description')}
        </p>
        <div className="flex items-center justify-center gap-3 flex-wrap pt-2">
          <a
            href="https://github.com/zgsm-ai/everything-ai-coding"
            target="_blank" rel="noreferrer"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-gray-900 dark:bg-white/10 text-white text-sm font-medium no-underline hover:opacity-80 transition-opacity"
          >
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
              <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z" />
            </svg>
            everything-ai-coding
          </a>
          <a
            href="https://github.com/zgsm-ai/costrict"
            target="_blank" rel="noreferrer"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl glass text-gray-700 dark:text-gray-200 text-sm font-medium no-underline hover:opacity-80 transition-opacity"
          >
            <img src={`${import.meta.env.BASE_URL}costrict_logo.png`} alt="Costrict" className="w-4 h-4 rounded-sm" />
            Powered by Costrict
          </a>
        </div>
      </div>

      {/* ── Data Pipeline ── */}
      <div className="glass rounded-2xl p-6 space-y-6">
        <h2 className="text-base font-semibold text-gray-900 dark:text-white">{t('about.pipeline.title')}</h2>

        <div className="relative">
          {/* Vertical connector line */}
          <div className="absolute left-6 top-8 bottom-8 w-px bg-gray-200 dark:bg-white/10" />

          <div className="space-y-3">
            {pipelineSteps.map((step, i) => (
              <div key={i} className="flex items-start gap-4">
                {/* Icon bubble — opaque backdrop masks the connector line */}
                <div className="relative z-10 w-12 h-12 shrink-0">
                  <div className="absolute inset-0 rounded-2xl bg-white dark:bg-gray-900" />
                  <div className={`relative w-full h-full rounded-2xl ${step.bg} ${step.text} flex items-center justify-center`}>
                    {step.icon}
                  </div>
                  <span className="absolute -top-1.5 -right-1.5 text-[10px] font-bold bg-white dark:bg-gray-900 text-gray-500 dark:text-gray-400 rounded-full w-4 h-4 flex items-center justify-center leading-none ring-1 ring-gray-200 dark:ring-white/10">
                    {i + 1}
                  </span>
                </div>

                {/* Content */}
                <div className="flex-1 min-w-0 bg-white/50 dark:bg-white/5 rounded-xl px-4 py-3 border border-white/60 dark:border-white/8">
                  <div className="flex items-baseline gap-2 flex-wrap">
                    <span className="text-sm font-semibold text-gray-900 dark:text-white">{t(step.labelKey)}</span>
                    <span className="text-xs text-gray-500 dark:text-gray-400">{t(step.descKey)}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── Scoring Weights ── */}
      <div className="glass rounded-2xl p-6 space-y-5">
        <div>
          <h2 className="text-base font-semibold text-gray-900 dark:text-white">{t('about.scoring.title')}</h2>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
            {t('about.scoring.desc')}{' '}
            <code className="bg-gray-100 dark:bg-white/10 px-1.5 py-0.5 rounded text-gray-700 dark:text-gray-300">final_score</code>
          </p>
        </div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
          <div className="space-y-2.5">
            <div className="text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500 mb-3">MCP / Skill</div>
            {mcpWeights.map(w => <WeightBar key={w.label} {...w} />)}
          </div>
          <div className="space-y-2.5">
            <div className="text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500 mb-3">Rule / Prompt</div>
            {ruleWeights.map(w => <WeightBar key={w.label} {...w} />)}
          </div>
          <div className="space-y-2.5">
            <div className="text-xs font-semibold uppercase tracking-wider text-pink-500 dark:text-pink-400 mb-3">🧩 Plugin</div>
            {pluginWeights.map(w => <WeightBar key={w.label} {...w} />)}
            <div className="text-[10px] text-gray-400 dark:text-gray-500 leading-snug pt-1">
              {lang === 'zh' ? '剔除 install_clarity（marketplace 安装统一），权重并入 doc_completeness。' : 'install_clarity dropped (marketplace install is uniform); weight folded into doc_completeness.'}
            </div>
          </div>
        </div>
      </div>

      {/* ── Decision Thresholds ── */}
      <div className="glass rounded-2xl p-6 space-y-4">
        <h2 className="text-base font-semibold text-gray-900 dark:text-white">{t('about.thresholds.title')}</h2>
        <div className="grid grid-cols-3 gap-3">
          {thresholds.map(th => (
            <div key={th.labelKey} className={`rounded-xl p-4 ring-1 ${th.ring} ${th.bg}`}>
              <div className="flex items-center gap-2 mb-3">
                <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: th.color }} />
                <span className="text-sm font-semibold text-gray-900 dark:text-white">{t(th.labelKey)}</span>
              </div>
              <div className="text-xl font-mono font-bold" style={{ color: th.color }}>{th.score}</div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Health Score ── */}
      <div className="glass rounded-2xl p-6 space-y-4">
        <div>
          <h2 className="text-base font-semibold text-gray-900 dark:text-white">{t('about.health.title')}</h2>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{t('about.health.desc')}</p>
        </div>
        <div className="grid sm:grid-cols-2 gap-3">
          {healthSignals.map(s => (
            <div key={s.labelKey} className="flex items-start gap-3 bg-white/40 dark:bg-white/5 rounded-xl p-3 border border-white/40 dark:border-white/8">
              <div className={`w-9 h-9 shrink-0 rounded-xl ${s.bg} ${s.text} flex items-center justify-center`}>
                {s.icon}
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <span className="text-sm font-semibold text-gray-900 dark:text-white truncate">{t(s.labelKey)}</span>
                    {s.pluginOnly && (
                      <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-pink-100 dark:bg-pink-900/40 text-pink-700 dark:text-pink-300 shrink-0">
                        🧩 plugin
                      </span>
                    )}
                  </div>
                  <span className="text-xs font-mono font-bold text-gray-400 dark:text-gray-500 shrink-0">{s.weight}%</span>
                </div>
                <div className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 leading-relaxed">{t(s.descKey)}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Source Trust ── */}
      <div className="glass rounded-2xl p-6 space-y-4">
        <div>
          <h2 className="text-base font-semibold text-gray-900 dark:text-white">{t('about.trust.title')}</h2>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{t('about.trust.desc')}</p>
        </div>
        <div className="space-y-2.5">
          {tiers.map(tier => (
            <div key={tier.label} className="flex items-center gap-4">
              <span className="text-xs font-bold w-12 shrink-0 tabular-nums" style={{ color: tier.color }}>{tier.label}</span>
              <TrustDot score={tier.score} />
              <div className="flex flex-wrap gap-1">
                {tier.sources.map(s => (
                  <span key={s} className="text-xs bg-gray-100 dark:bg-white/10 text-gray-600 dark:text-gray-400 px-2 py-0.5 rounded-full font-mono">
                    {s}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Data Sources ── */}
      <div className="glass rounded-2xl p-6 space-y-4">
        <h2 className="text-base font-semibold text-gray-900 dark:text-white">{t('about.sources')}</h2>
        <div className="grid gap-2">
          {sources.map(s => (
            <a
              key={s.slug}
              href={s.url}
              target="_blank" rel="noreferrer"
              className="flex items-center gap-3 bg-white/40 dark:bg-white/5 hover:bg-white/70 dark:hover:bg-white/10 rounded-xl px-4 py-2.5 border border-white/40 dark:border-white/8 no-underline transition-colors group"
            >
              <span className={`text-xs font-semibold px-2 py-0.5 rounded-full shrink-0 ${TYPE_BADGE[s.type]}`}>{s.type}</span>
              <span className="text-sm text-gray-700 dark:text-gray-200 group-hover:text-apple-blue transition-colors flex-1">{s.name}</span>
              <span className="text-xs text-gray-400 dark:text-gray-500 tabular-nums shrink-0">{s.count.toLocaleString()}</span>
              <TrustDot score={s.trust} />
            </a>
          ))}
        </div>
      </div>

    </div>
  )
}
