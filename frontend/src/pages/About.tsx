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

function TargetIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <circle cx="12" cy="12" r="6" />
      <circle cx="12" cy="12" r="2" />
    </svg>
  )
}

function PackageIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="m16.5 9.4-9-5.19" />
      <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
      <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
      <line x1="12" y1="22.08" x2="12" y2="12" />
    </svg>
  )
}

const SOURCES = [
  { name: 'awesome-mcp-servers', url: 'https://github.com/punkpeye/awesome-mcp-servers', trust: 4, type: 'MCP' },
  { name: 'mcp.so', url: 'https://mcp.so', trust: 2, type: 'MCP' },
  { name: 'Anthropic Skills', url: 'https://github.com/anthropics/skills', trust: 5, type: 'Skills' },
  { name: 'Ai-Agent-Skills', url: 'https://github.com/skillcreatorai/Ai-Agent-Skills', trust: 3, type: 'Skills' },
  { name: 'antigravity-skills', url: 'https://github.com/antigravities/awesome-claude-code-skills', trust: 3, type: 'Skills' },
  { name: 'awesome-cursorrules', url: 'https://github.com/PatrickJS/awesome-cursorrules', trust: 4, type: 'Rules' },
  { name: 'Rules 2.1', url: 'https://github.com/Mr-chen-05/rules-2.1-optimized', trust: 3, type: 'Rules' },
  { name: 'prompts.chat', url: 'https://github.com/f/prompts.chat', trust: 4, type: 'Prompts' },
  { name: 'wonderful-prompts', url: 'https://github.com/langgptai/wonderful-prompts', trust: 3, type: 'Prompts' },
]

const TRUST_LEVELS = [
  { score: 5, label: 'Tier 1', sources: ['anthropics-skills', 'curated'], color: '#30d158' },
  { score: 4, label: 'Tier 2', sources: ['awesome-mcp-servers', 'awesome-cursorrules', 'prompts-chat'], color: '#0071e3' },
  { score: 3, label: 'Tier 3', sources: ['ai-agent-skills', 'github-search', 'rules-2.1'], color: '#ff9f0a' },
  { score: 2, label: 'Tier 4', sources: ['mcp.so'], color: '#ff453a' },
]

const TYPE_BADGE: Record<string, string> = {
  MCP: 'bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300',
  Skills: 'bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-300',
  Rules: 'bg-orange-100 dark:bg-orange-900/40 text-orange-700 dark:text-orange-300',
  Prompts: 'bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300',
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
  const { t } = useI18n()

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
    { label: 'Coding Relevance', weight: 30, color: '#0071e3' },
    { label: 'Content Quality',  weight: 25, color: '#34aadc' },
    { label: 'Specificity',      weight: 20, color: '#5ac8fa' },
    { label: 'Source Trust',     weight: 15, color: '#30d158' },
    { label: 'Confidence',       weight: 10, color: '#64d2ff' },
  ]

  const ruleWeights = [
    { label: 'Coding Relevance', weight: 35, color: '#0071e3' },
    { label: 'Content Quality',  weight: 35, color: '#34aadc' },
    { label: 'Source Trust',     weight: 15, color: '#30d158' },
    { label: 'Confidence',       weight: 15, color: '#64d2ff' },
  ]

  const healthSignals = [
    { icon: <StarIcon />,    bg: 'bg-amber-50 dark:bg-amber-500/10',   text: 'text-amber-600 dark:text-amber-400',   labelKey: 'about.signal.popularity',     descKey: 'about.signal.popularity.desc',     weight: 30 },
    { icon: <ClockIcon />,   bg: 'bg-sky-50 dark:bg-sky-500/10',       text: 'text-sky-600 dark:text-sky-400',       labelKey: 'about.signal.freshness',      descKey: 'about.signal.freshness.desc',      weight: 25 },
    { icon: <TargetIcon />,  bg: 'bg-violet-50 dark:bg-violet-500/10', text: 'text-violet-600 dark:text-violet-400', labelKey: 'about.signal.quality',        descKey: 'about.signal.quality.desc',        weight: 25 },
    { icon: <PackageIcon />, bg: 'bg-teal-50 dark:bg-teal-500/10',     text: 'text-teal-600 dark:text-teal-400',     labelKey: 'about.signal.installability', descKey: 'about.signal.installability.desc', weight: 20 },
  ]

  const thresholds = [
    { labelKey: 'about.decision.accept', mcp: '≥ 40', rp: '≥ 30', color: '#30d158', ring: 'ring-green-500/30',  bg: 'bg-green-500/8 dark:bg-green-500/12'  },
    { labelKey: 'about.decision.review', mcp: '≥ 25', rp: '≥ 15', color: '#ff9f0a', ring: 'ring-yellow-500/30', bg: 'bg-yellow-500/8 dark:bg-yellow-500/12' },
    { labelKey: 'about.decision.reject', mcp: '< 25',  rp: '< 15',  color: '#ff453a', ring: 'ring-red-500/30',   bg: 'bg-red-500/8 dark:bg-red-500/12'       },
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
            href="https://github.com/zgsm-sangfor/costrict-coding-hub"
            target="_blank" rel="noreferrer"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-gray-900 dark:bg-white/10 text-white text-sm font-medium no-underline hover:opacity-80 transition-opacity"
          >
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
              <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z" />
            </svg>
            costrict-coding-hub
          </a>
          <a
            href="https://github.com/zgsm-ai/costrict"
            target="_blank" rel="noreferrer"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl glass text-gray-700 dark:text-gray-200 text-sm font-medium no-underline hover:opacity-80 transition-opacity"
          >
            <img src="./costrict_logo.png" alt="Costrict" className="w-4 h-4 rounded-sm" />
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
        <div className="grid sm:grid-cols-2 gap-6">
          <div className="space-y-2.5">
            <div className="text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500 mb-3">MCP / Skill</div>
            {mcpWeights.map(w => <WeightBar key={w.label} {...w} />)}
          </div>
          <div className="space-y-2.5">
            <div className="text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500 mb-3">Rule / Prompt</div>
            {ruleWeights.map(w => <WeightBar key={w.label} {...w} />)}
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
              <div className="space-y-2">
                <div>
                  <div className="text-[10px] uppercase tracking-wide text-gray-400 dark:text-gray-500">MCP / Skill</div>
                  <div className="text-base font-mono font-bold" style={{ color: th.color }}>{th.mcp}</div>
                </div>
                <div>
                  <div className="text-[10px] uppercase tracking-wide text-gray-400 dark:text-gray-500">Rule / Prompt</div>
                  <div className="text-base font-mono font-bold" style={{ color: th.color }}>{th.rp}</div>
                </div>
              </div>
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
                  <span className="text-sm font-semibold text-gray-900 dark:text-white">{t(s.labelKey)}</span>
                  <span className="text-xs font-mono font-bold text-gray-400 dark:text-gray-500">{s.weight}%</span>
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
          {TRUST_LEVELS.map(tier => (
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
          {SOURCES.map(s => (
            <a
              key={s.name}
              href={s.url}
              target="_blank" rel="noreferrer"
              className="flex items-center gap-3 bg-white/40 dark:bg-white/5 hover:bg-white/70 dark:hover:bg-white/10 rounded-xl px-4 py-2.5 border border-white/40 dark:border-white/8 no-underline transition-colors group"
            >
              <span className={`text-xs font-semibold px-2 py-0.5 rounded-full shrink-0 ${TYPE_BADGE[s.type]}`}>{s.type}</span>
              <span className="text-sm text-gray-700 dark:text-gray-200 group-hover:text-apple-blue transition-colors flex-1">{s.name}</span>
              <TrustDot score={s.trust} />
            </a>
          ))}
        </div>
      </div>

    </div>
  )
}
