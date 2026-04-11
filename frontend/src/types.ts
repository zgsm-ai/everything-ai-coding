export interface CatalogItem {
  id: string
  name: string
  type: 'mcp' | 'skill' | 'rule' | 'prompt'
  description: string
  description_zh?: string
  source_url: string
  stars: number | null
  pushed_at?: string
  category: string
  tags: string[]
  tech_stack: string[]
  install?: {
    method: 'mcp_config' | 'git_clone' | 'manual' | 'download_file'
    config?: Record<string, unknown>
    repo?: string
    files?: string[]
  }
  source: string
  last_synced: string
  added_at?: string
  evaluation?: {
    evaluated_at: string
    evaluator: string
    coding_relevance: number
    content_quality: number
    specificity: number
    source_trust: number
    confidence: number
    reason: string
    final_score: number
    decision: string
  }
  health?: {
    score: number
    signals: {
      popularity: number
      freshness: number
      quality: number
      installability: number
    }
    freshness_label: string
    last_commit?: string
  }
  final_score: number
  decision: string
}

export interface Stats {
  total: number
  byType: Record<string, number>
  byCategory: Record<string, number>
}

export interface FeaturedSection {
  title: string
  items: FeaturedItem[]
}

export interface FeaturedItem {
  id: string
  name: string
  type: string
  description: string
  description_zh?: string
  stars: number | null
  source_url: string
  source: string
  final_score: number
}

export interface SearchIndexItem {
  id: string
  name: string
  type: string
  category: string
  tags: string[]
  tech_stack: string[]
  stars: number | null
  description: string
  description_zh?: string
  source_url: string
  final_score: number
  decision: string
  install_method?: string
  search_text?: string
}
