import { describe, expect, it } from 'vitest'

import { buildSearchIndex } from './useSearch'
import type { SearchIndexItem } from '../types'

/**
 * These tests exercise the exact MiniSearch index + options the useSearch hook
 * builds (via the shared ``buildSearchIndex`` helper), without needing a DOM or
 * fetch mock. They lock in the two behaviours the 06-22 refactor cares about:
 *   1. "search by source/author" — a bare owner token recalls every entry from
 *      that source via ``search_text`` provenance, not just name-matched ones.
 *   2. boost ordering — a direct name match still outranks a recall-only hit.
 */

function slim(overrides: Partial<SearchIndexItem>): SearchIndexItem {
  return {
    id: 'x',
    name: 'x',
    type: 'skill',
    source: 'mattpocock/skills',
    stars: 132000,
    final_score: 70,
    freshness_label: 'active',
    snippet: 'does a thing for engineering workflows',
    // mirrors build_search_text: tags + source provenance (source id,
    // owner/repo, bare owner) + search_terms — NOT name/description.
    search_text: 'engineering workflow mattpocock/skills mattpocock',
    shard: 0,
    ...overrides,
  }
}

describe('useSearch MiniSearch index', () => {
  it('recalls every entry of a source when searching the owner token', () => {
    // 3 entries from mattpocock/skills; only one name contains "matt".
    const items: SearchIndexItem[] = [
      slim({ id: 'grilling', name: 'grilling' }),
      slim({ id: 'handoff', name: 'handoff' }),
      slim({ id: 'ask-matt', name: 'ask-matt' }),
    ]
    const ms = buildSearchIndex(items)

    const ids = ms.search('mattpocock').map(h => h.id)
    expect(ids.sort()).toEqual(['ask-matt', 'grilling', 'handoff'])

    // Prefix match on the shorter "matt" token also recalls all three
    // (search_text carries the owner on every entry).
    const prefixIds = ms.search('matt').map(h => h.id)
    expect(prefixIds.sort()).toEqual(['ask-matt', 'grilling', 'handoff'])
  })

  it('ranks a direct name match above a recall-only (search_text) hit', () => {
    const items: SearchIndexItem[] = [
      // Name match for "router".
      slim({ id: 'router-skill', name: 'router', search_text: 'mattpocock/skills mattpocock' }),
      // Only a search_text (recall) hit for "router".
      slim({ id: 'other', name: 'other', search_text: 'router mattpocock/skills mattpocock' }),
    ]
    const ms = buildSearchIndex(items)

    const hits = ms.search('router')
    expect(hits.length).toBe(2)
    // name boost (3) > search_text boost (0.8): the name match comes first.
    expect(hits[0].id).toBe('router-skill')
  })

  it('matches against the description snippet field', () => {
    const items: SearchIndexItem[] = [
      slim({ id: 'eng', name: 'eng', snippet: 'helps with database migrations' }),
      slim({ id: 'noise', name: 'noise', snippet: 'unrelated text' }),
    ]
    const ms = buildSearchIndex(items)
    const ids = ms.search('database').map(h => h.id)
    expect(ids).toContain('eng')
    expect(ids).not.toContain('noise')
  })
})
