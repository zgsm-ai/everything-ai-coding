import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router'
import { useI18n } from '../hooks/useI18n'
import ResourceCard from '../components/ResourceCard'
import CardSkeleton from '../components/CardSkeleton'
import HeroWordmark from '../components/HeroWordmark'
import type { Stats, FeaturedSection, CatalogItem } from '../types'

const TYPE_ICONS: Record<string, string> = {
  mcp: '🔌',
  skill: '🎯',
  rule: '📋',
  prompt: '💡',
}

const INITIAL_SHOW = 4

const TYPEWRITER_LINES_EN = [
  'Find your next MCP server',
  'Ship faster with curated skills',
  'Rules that keep your code clean',
  'Prompts crafted by the community',
]

const TYPEWRITER_LINES_ZH = [
  '找到你的下一个 MCP 服务',
  '用精选技能加速开发',
  '让代码风格始终如一',
  '社区打磨的高质量提示词',
]

function useTypewriter(lines: string[], typingSpeed = 120, pauseDuration = 2500) {
  const [display, setDisplay] = useState('')
  const [phase, setPhase] = useState<'typing' | 'pausing' | 'deleting'>('typing')
  const [lineIdx, setLineIdx] = useState(0)
  const [charIdx, setCharIdx] = useState(0)

  useEffect(() => {
    const currentLine = lines[lineIdx]

    if (phase === 'typing') {
      if (charIdx < currentLine.length) {
        const timer = setTimeout(() => {
          setCharIdx(c => c + 1)
          setDisplay(currentLine.slice(0, charIdx + 1))
        }, typingSpeed)
        return () => clearTimeout(timer)
      }
      // Done typing, pause
      const timer = setTimeout(() => setPhase('deleting'), pauseDuration)
      return () => clearTimeout(timer)
    }

    if (phase === 'deleting') {
      if (charIdx > 0) {
        const timer = setTimeout(() => {
          setCharIdx(c => c - 1)
          setDisplay(currentLine.slice(0, charIdx - 1))
        }, typingSpeed / 3)
        return () => clearTimeout(timer)
      }
      // Done deleting, next line
      setLineIdx(i => (i + 1) % lines.length)
      setCharIdx(0)
      setDisplay('')
      setPhase('typing')
    }
  }, [lines, lineIdx, charIdx, phase, typingSpeed, pauseDuration])

  return display
}

export default function Home() {
  const { t, lang } = useI18n()
  const navigate = useNavigate()
  const lines = lang === 'zh' ? TYPEWRITER_LINES_ZH : TYPEWRITER_LINES_EN
  const typed = useTypewriter(lines)
  const [stats, setStats] = useState<Stats | null>(null)
  const [featured, setFeatured] = useState<FeaturedSection[]>([])
  const [trending, setTrending] = useState<CatalogItem[]>([])
  const [searchQuery, setSearchQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set())

  useEffect(() => {
    Promise.all([
      fetch('./api/stats.json').then(r => r.json()),
      fetch('./api/featured.json').then(r => r.json()),
      ...['mcp.json', 'skills.json'].map(f => fetch(`./api/${f}`).then(r => r.json())),
    ]).then(([s, f, ...typeArrays]) => {
      setStats(s)
      setFeatured(f)
      // Trending: top 20 by stars, deduplicated by repo (monorepo items share stars)
      const all = (typeArrays as CatalogItem[][]).flat().filter(i => i.stars != null && i.stars! > 0)
      all.sort((a, b) => (b.stars ?? 0) - (a.stars ?? 0))
      const seen = new Set<string>()
      const deduped: CatalogItem[] = []
      for (const item of all) {
        // Extract GitHub repo base: https://github.com/org/repo
        const repoBase = item.source_url?.split('/').slice(0, 5).join('/') || item.id
        if (seen.has(repoBase)) continue
        seen.add(repoBase)
        deduped.push(item)
        if (deduped.length >= 20) break
      }
      setTrending(deduped)
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    if (searchQuery.trim()) {
      navigate(`/browse?q=${encodeURIComponent(searchQuery.trim())}`)
    }
  }

  const toggleSection = (title: string) => {
    setExpandedSections(prev => {
      const next = new Set(prev)
      if (next.has(title)) next.delete(title)
      else next.add(title)
      return next
    })
  }

  return (
    <div className="space-y-16">
      {/* Hero */}
      <section className="text-center pt-12 pb-4">
        <div className="mb-3">
          <span className="sr-only">{t('hero.title')}</span>
          <HeroWordmark />
        </div>
        <p className="text-xl sm:text-2xl text-gray-500 dark:text-gray-400 mb-8 h-9">
          <span>{typed}</span>
          <span className="inline-block w-[2px] h-[1em] bg-apple-blue ml-0.5 align-middle animate-[blink_1s_step-end_infinite]" />
        </p>
        <form onSubmit={handleSearch} className="max-w-xl mx-auto">
          <div className="glass rounded-2xl flex items-center px-4 py-3 gap-3">
            <svg className="w-5 h-5 text-gray-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <input
              type="text"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              placeholder={t('hero.search')}
              className="flex-1 bg-transparent border-none outline-none text-gray-900 dark:text-white placeholder-gray-400"
            />
          </div>
        </form>

        {/* Stats */}
        {stats && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-10 max-w-2xl mx-auto">
            {(['mcp', 'skill', 'rule', 'prompt'] as const).map(type => (
              <div key={type} className="glass rounded-2xl p-4 text-center cursor-pointer hover:scale-105 transition-transform"
                onClick={() => navigate(`/browse?type=${type}`)}>
                <div className="text-2xl mb-1">{TYPE_ICONS[type]}</div>
                <div className="text-2xl font-bold text-gray-900 dark:text-white">
                  {stats.byType[type] || 0}
                </div>
                <div className="text-sm text-gray-500 dark:text-gray-400">{t(`stats.${type}`)}</div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Trending — moved above Featured */}
      {trending.length > 0 && (
        <section>
          <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-6">{t('trending.title')}</h2>
          {loading ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {Array.from({ length: 6 }).map((_, i) => <CardSkeleton key={i} />)}
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {trending.map(item => (
                <ResourceCard key={item.id} item={item} compact />
              ))}
            </div>
          )}
        </section>
      )}

      {/* Featured — collapsible grid sections */}
      {featured.length > 0 && (
        <section>
          <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-6">{t('featured.title')}</h2>
          <div className="space-y-6">
            {featured.map(section => {
              const expanded = expandedSections.has(section.title)
              const sectionTitle = t(`featured.${section.title}`) !== `featured.${section.title}`
                ? t(`featured.${section.title}`)
                : section.title
              const visibleItems = expanded ? section.items : section.items.slice(0, INITIAL_SHOW)
              const hasMore = section.items.length > INITIAL_SHOW

              return (
                <div key={section.title} className="glass rounded-2xl p-5">
                  <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-200 mb-4">{sectionTitle}</h3>
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                    {visibleItems.map(item => (
                      <ResourceCard key={item.id} item={item as CatalogItem} compact />
                    ))}
                  </div>
                  {hasMore && (
                    <button
                      onClick={() => toggleSection(section.title)}
                      className="mt-4 text-sm text-apple-blue hover:text-apple-blue-hover font-medium bg-transparent border-none cursor-pointer"
                    >
                      {expanded
                        ? (lang === 'zh' ? '收起' : 'Show less')
                        : (lang === 'zh' ? `展开全部 ${section.items.length} 项` : `Show all ${section.items.length} items`)}
                    </button>
                  )}
                </div>
              )
            })}
          </div>
        </section>
      )}
    </div>
  )
}
