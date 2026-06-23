import { useState, useEffect, useRef, useCallback } from 'react'
import MiniSearch from 'minisearch'
import type { CatalogItem, SearchIndexItem } from '../types'

let cachedIndex: MiniSearch<SearchIndexItem> | null = null
let cachedItems: Map<string, SearchIndexItem> | null = null
let loadPromise: Promise<MiniSearch<SearchIndexItem>> | null = null

// Field boosts mirror the previous hand-rolled ranker: name dominates, the
// description snippet is the mid-weight signal, and search_text (tags + source
// provenance + search_terms) is recall-only so a bare owner token like
// "mattpocock" surfaces every entry from that source without those expansion
// hits drowning out direct name/desc matches.
export const SEARCH_OPTIONS = {
  boost: { name: 3, snippet: 1, search_text: 0.8 },
  prefix: true,
  fuzzy: 0.2,
  combineWith: 'AND' as const,
}

/** MiniSearch index fields — exported so tests build an identical index. */
export const INDEX_FIELDS = ['name', 'snippet', 'search_text'] as const

/** Build a MiniSearch index over slim search-index entries (shared by hook + tests). */
export function buildSearchIndex(items: SearchIndexItem[]): MiniSearch<SearchIndexItem> {
  const ms = new MiniSearch<SearchIndexItem>({
    fields: [...INDEX_FIELDS],
    storeFields: ['id'],
    searchOptions: SEARCH_OPTIONS,
  })
  ms.addAll(items)
  return ms
}

/**
 * Adapt a slim search-index entry into the partial ``CatalogItem`` shape the
 * list cards render. The slim entry intentionally lacks the heavy fields
 * (full description / category / tags / install / bundle …) — those now live in
 * the per-entry shards and are only fetched on the Detail view. ResourceCard
 * guards every heavy field with optional chaining, so the snippet-as-description
 * mapping below is enough for a faithful card.
 */
function slimToCard(entry: SearchIndexItem): CatalogItem {
  return {
    id: entry.id,
    name: entry.name,
    type: entry.type as CatalogItem['type'],
    description: entry.snippet ?? '',
    source_url: '',
    stars: entry.stars,
    category: '',
    tags: [],
    tech_stack: [],
    source: entry.source ?? '',
    last_synced: '',
    final_score: entry.final_score ?? 0,
    decision: '',
    health: entry.freshness_label
      ? {
          score: 0,
          signals: { freshness: 0, popularity: 0, source_trust: 0 },
          freshness_label: entry.freshness_label,
        }
      : undefined,
  }
}

export function useSearch(query: string) {
  const [results, setResults] = useState<CatalogItem[] | null>(null)
  const [searching, setSearching] = useState(false)
  const [searchReady, setSearchReady] = useState(!!cachedIndex)
  const timerRef = useRef<ReturnType<typeof setTimeout>>(undefined)

  // Load the slim search-index once and feed it straight into MiniSearch via
  // addAll (the slim array is already addAll-ready). Building the index this
  // way (rather than MiniSearch.loadJSON of a serialized index) keeps the
  // build pipeline unchanged while still killing the old O(n) per-keystroke
  // full-table scan — MiniSearch maintains an inverted index internally.
  const ensureIndex = useCallback(async () => {
    if (cachedIndex) return cachedIndex
    if (loadPromise) return loadPromise

    setSearching(true)
    loadPromise = (async () => {
      const resp = await fetch('./api/search-index.json')
      const rawItems: SearchIndexItem[] = await resp.json()

      const ms = buildSearchIndex(rawItems)

      cachedItems = new Map(rawItems.map(i => [i.id, i]))
      cachedIndex = ms
      setSearchReady(true)
      setSearching(false)
      return ms
    })()
    return loadPromise
  }, [])

  useEffect(() => {
    if (!query.trim()) {
      setResults(null)
      return
    }

    clearTimeout(timerRef.current)
    timerRef.current = setTimeout(async () => {
      const ms = await ensureIndex()
      const hits = ms.search(query)
      const ranked = hits
        .map(hit => {
          const entry = cachedItems?.get(hit.id)
          return entry ? slimToCard(entry) : null
        })
        .filter((card): card is CatalogItem => card !== null)
        .slice(0, 200)
      setResults(ranked)
    }, 200)

    return () => clearTimeout(timerRef.current)
  }, [query, ensureIndex])

  return { results, searching, searchReady }
}
