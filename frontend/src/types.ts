export type RiskLevel = 'clean' | 'low' | 'medium' | 'high' | 'extreme'
export type SecurityVerdict = 'safe' | 'caution' | 'reject'

export interface SecurityScan {
  risk_level: RiskLevel
  verdict: SecurityVerdict
  red_flags: string[]
  permissions: {
    files: string[]
    network: string[]
    commands: string[]
  }
  summary: string
  recommendations: string[]
  scan_model?: string
  rubric_version?: string
  content_hash?: string
  scanned_at?: string
}

export interface CatalogItem {
  id: string
  name: string
  type: 'mcp' | 'skill' | 'rule' | 'prompt' | 'plugin'
  description: string
  description_zh?: string
  source_url: string
  stars: number | null
  pushed_at?: string
  category: string
  tags: string[]
  tech_stack: string[]
  install?: {
    method: 'mcp_config' | 'mcp_config_template' | 'git_clone' | 'manual' | 'download_file' | 'plugin_marketplace'
    config?: Record<string, unknown>
    repo?: string
    files?: string[]
    branch?: string
    path?: string
    marketplace?: string
    plugin_name?: string
    // Plugin marketplace metadata added by fix-plugin-marketplace-fields.
    // marketplace_repo is the canonical GitHub slug; marketplace_name is the
    // value from marketplace.json::name (used as the suffix in `enabled_key`);
    // marketplace_verified is false when the catalog could not confirm the
    // plugin is actually listed in the marketplace manifest.
    marketplace_repo?: string
    marketplace_name?: string | null
    marketplace_verified?: boolean
  }
  bundle?: {
    skills_count: number
    agents_count: number
    commands_count: number
    mcp_servers_count: number
    hooks_count?: number
    skills_namespaces: string[]
    hook_events?: string[]
    mcp_server_names?: string[]
    bundled_skill_ids?: Array<string | null>
  }
  bundled_in?: string
  // MCP installability (only present when type==='mcp' and entry has been LLM-evaluated)
  mcp_schema_valid?: boolean
  mcp_install_state?: 'ready' | 'needs_config' | 'manual' | 'invalid' | 'unknown'
  mcp_validation_tags?: string[]
  mcp_installability_reason?: string
  // Security scan result (any type, only when LLM evaluated this entry successfully).
  security?: SecurityScan
  source: string
  last_synced: string
  added_at?: string
  evaluation?: {
    coding_relevance: number
    doc_completeness: number
    desc_accuracy: number
    writing_quality: number
    specificity: number
    install_clarity: number
    final_score: number
    decision: string
    model_id?: string
    rubric_version?: string
    evaluated_at?: string
  }
  health?: {
    score: number
    signals: {
      freshness: number
      popularity: number
      source_trust: number
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
  source?: string
  install_method?: string
  search_text?: string
}
