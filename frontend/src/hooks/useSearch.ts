import { useState, useEffect, useRef, useCallback } from 'react'
import MiniSearch from 'minisearch'
import type { CatalogItem, SearchIndexItem } from '../types'

let cachedIndex: MiniSearch | null = null
let cachedItems: Map<string, SearchIndexItem> | null = null

export function useSearch(query: string) {
  const [results, setResults] = useState<CatalogItem[] | null>(null)
  const [searching, setSearching] = useState(false)
  const [searchReady, setSearchReady] = useState(!!cachedIndex)
  const timerRef = useRef<ReturnType<typeof setTimeout>>(undefined)

  // Load and build index on first call with a query
  const ensureIndex = useCallback(async () => {
    if (cachedIndex) return cachedIndex

    setSearching(true)
    const resp = await fetch('./api/search-index.json')
    const rawItems: SearchIndexItem[] = await resp.json()
    const items = rawItems.map(item => ({
      ...item,
      search_text: item.search_text ?? [
        item.name,
        item.description,
        item.description_zh,
        item.tags.join(' '),
        item.tech_stack.join(' '),
      ].filter(Boolean).join(' '),
    }))

    const ms = new MiniSearch<SearchIndexItem>({
      fields: ['name', 'description', 'description_zh', 'search_text'],
      storeFields: ['id'],
      searchOptions: {
        boost: { name: 3, description: 1, description_zh: 1, search_text: 0.8 },
        prefix: true,
        fuzzy: 0.2,
      },
    })
    ms.addAll(items)

    cachedItems = new Map(items.map(i => [i.id, i]))
    cachedIndex = ms
    setSearchReady(true)
    setSearching(false)
    return ms
  }, [])

  useEffect(() => {
    if (!query.trim()) {
      setResults(null)
      return
    }

    clearTimeout(timerRef.current)
    timerRef.current = setTimeout(async () => {
      const ms = await ensureIndex()
      const hits = ms.search(query).slice(0, 200)
      const mapped = hits
        .map(hit => {
          const item = cachedItems?.get(hit.id)
          return item ? (item as unknown as CatalogItem) : null
        })
        .filter(Boolean) as CatalogItem[]
      setResults(mapped)
    }, 200)

    return () => clearTimeout(timerRef.current)
  }, [query, ensureIndex])

  return { results, searching, searchReady }
}
