import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router'
import { useI18n } from '../hooks/useI18n'
import { useSearch } from '../hooks/useSearch'
import ResourceCard from '../components/ResourceCard'
import CardSkeleton from '../components/CardSkeleton'
import type { CatalogItem } from '../types'

const TYPES = ['all', 'mcp', 'skill', 'rule', 'prompt'] as const
const CATEGORIES = [
  'all', 'tooling', 'ai-ml', 'backend', 'frontend', 'devops',
  'security', 'documentation', 'testing', 'database', 'mobile', 'fullstack'
]
const BATCH_SIZE = 30

export default function Browse() {
  const { t } = useI18n()
  const [searchParams, setSearchParams] = useSearchParams()
  const [items, setItems] = useState<CatalogItem[]>([])
  const [loading, setLoading] = useState(true)
  const [visibleCount, setVisibleCount] = useState(BATCH_SIZE)
  const sentinelRef = useRef<HTMLDivElement>(null)

  const composingRef = useRef(false)

  const activeType = searchParams.get('type') || 'all'
  const activeCat = searchParams.get('cat') || 'all'
  const activeSort = searchParams.get('sort') || 'score'
  const searchQuery = searchParams.get('q') || ''

  // Local input buffer to avoid URL param updates interrupting IME composition
  const [inputValue, setInputValue] = useState(searchQuery)

  // Sync URL → local when URL changes externally (e.g. browser back/forward)
  useEffect(() => {
    if (!composingRef.current) {
      setInputValue(searchQuery)
    }
  }, [searchQuery])

  const { results: searchResults, searching } = useSearch(searchQuery)

  // Load data by type
  useEffect(() => {
    setLoading(true)
    const files = activeType === 'all'
      ? ['mcp.json', 'skills.json', 'rules.json', 'prompts.json']
      : [activeType === 'skill' ? 'skills.json' : activeType === 'rule' ? 'rules.json' : activeType === 'prompt' ? 'prompts.json' : 'mcp.json']

    Promise.all(files.map(f => fetch(`./api/${f}`).then(r => r.json())))
      .then(arrays => {
        setItems(arrays.flat())
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [activeType])

  // Reset scroll position on filter change
  useEffect(() => {
    setVisibleCount(BATCH_SIZE)
  }, [activeType, activeCat, activeSort, searchQuery])

  // Filter and sort
  const filtered = useMemo(() => {
    let result: CatalogItem[]

    if (searchQuery && searchResults) {
      result = searchResults
      // Apply type filter on search results too
      if (activeType !== 'all') {
        result = result.filter(i => i.type === activeType)
      }
    } else {
      result = items
    }

    if (activeCat !== 'all') {
      result = result.filter(i => i.category === activeCat)
    }

    if (activeSort === 'stars') {
      result = [...result].sort((a, b) => (b.stars ?? -1) - (a.stars ?? -1))
    } else {
      result = [...result].sort((a, b) => (b.final_score ?? 0) - (a.final_score ?? 0))
    }

    return result
  }, [items, searchResults, searchQuery, activeType, activeCat, activeSort])

  const visible = filtered.slice(0, visibleCount)

  // Infinite scroll observer
  const handleObserver = useCallback((entries: IntersectionObserverEntry[]) => {
    if (entries[0]?.isIntersecting && visibleCount < filtered.length) {
      setVisibleCount(c => Math.min(c + BATCH_SIZE, filtered.length))
    }
  }, [visibleCount, filtered.length])

  useEffect(() => {
    const el = sentinelRef.current
    if (!el) return
    const observer = new IntersectionObserver(handleObserver, { rootMargin: '200px' })
    observer.observe(el)
    return () => observer.disconnect()
  }, [handleObserver])

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(searchParams)
    if (value === 'all' || value === '' || (key === 'sort' && value === 'score')) {
      next.delete(key)
    } else {
      next.set(key, value)
    }
    setSearchParams(next, { replace: true })
  }

  return (
    <div className="space-y-6">
      {/* Search bar */}
      <div className="glass rounded-2xl flex items-center px-4 py-3 gap-3">
        <svg className="w-5 h-5 text-gray-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
        <input
          type="text"
          value={inputValue}
          onChange={e => {
            setInputValue(e.target.value)
            if (!composingRef.current) {
              setParam('q', e.target.value)
            }
          }}
          onCompositionStart={() => { composingRef.current = true }}
          onCompositionEnd={e => {
            composingRef.current = false
            setParam('q', (e.target as HTMLInputElement).value)
          }}
          placeholder={t('search.placeholder')}
          className="flex-1 bg-transparent border-none outline-none text-gray-900 dark:text-white placeholder-gray-400"
        />
        {searching && <span className="text-xs text-gray-400">{t('search.loading')}</span>}
        {searchQuery && searchResults && (
          <span className="text-xs text-gray-400">{filtered.length} {t('search.results')}</span>
        )}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Type tabs */}
        <div className="flex gap-1 glass rounded-xl p-1">
          {TYPES.map(type => (
            <button
              key={type}
              onClick={() => setParam('type', type)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium border-none cursor-pointer transition-colors ${
                activeType === type
                  ? 'bg-apple-blue text-white'
                  : 'bg-transparent text-gray-600 dark:text-gray-300 hover:bg-white/50 dark:hover:bg-white/10'
              }`}
            >
              {type === 'all' ? t('browse.all') : type.toUpperCase()}
            </button>
          ))}
        </div>

        {/* Category dropdown */}
        <select
          value={activeCat}
          onChange={e => setParam('cat', e.target.value)}
          className="glass rounded-xl px-3 py-2 text-sm text-gray-600 dark:text-gray-300 border-none cursor-pointer outline-none"
        >
          {CATEGORIES.map(cat => (
            <option key={cat} value={cat}>
              {cat === 'all' ? t('browse.category.all') : (t(`cat.${cat}`) !== `cat.${cat}` ? t(`cat.${cat}`) : cat)}
            </option>
          ))}
        </select>

        {/* Sort */}
        <div className="flex gap-1 glass rounded-xl p-1">
          {(['score', 'stars'] as const).map(sort => (
            <button
              key={sort}
              onClick={() => setParam('sort', sort)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium border-none cursor-pointer transition-colors ${
                activeSort === sort
                  ? 'bg-apple-blue text-white'
                  : 'bg-transparent text-gray-600 dark:text-gray-300 hover:bg-white/50 dark:hover:bg-white/10'
              }`}
            >
              {t(`browse.sort.${sort}`)}
            </button>
          ))}
        </div>
      </div>

      {/* Results grid */}
      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 9 }).map((_, i) => <CardSkeleton key={i} />)}
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-16 text-gray-400 dark:text-gray-500">{t('search.noResults')}</div>
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {visible.map(item => (
              <ResourceCard key={item.id} item={item} highlight={searchQuery} />
            ))}
          </div>
          {visibleCount < filtered.length && (
            <div ref={sentinelRef} className="h-10" />
          )}
        </>
      )}
    </div>
  )
}
