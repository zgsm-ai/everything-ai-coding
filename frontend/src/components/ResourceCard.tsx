import { Link } from 'react-router'
import { useI18n } from '../hooks/useI18n'
import type { CatalogItem } from '../types'

const TYPE_COLORS: Record<string, string> = {
  mcp: 'bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300',
  skill: 'bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-300',
  rule: 'bg-orange-100 text-orange-700 dark:bg-orange-900/50 dark:text-orange-300',
  prompt: 'bg-purple-100 text-purple-700 dark:bg-purple-900/50 dark:text-purple-300',
}

const TYPE_ICONS: Record<string, string> = {
  mcp: '🔌',
  skill: '🎯',
  rule: '📋',
  prompt: '💡',
}

function formatStars(stars: number | null): string {
  if (stars == null) return ''
  if (stars >= 1000) return `${(stars / 1000).toFixed(1)}k`
  return String(stars)
}

interface Props {
  item: CatalogItem
  compact?: boolean
  highlight?: string
}

export default function ResourceCard({ item, compact, highlight }: Props) {
  const { lang } = useI18n()
  const desc = lang === 'zh' && item.description_zh ? item.description_zh : item.description
  const freshnessLabel = item.health?.freshness_label

  return (
    <Link
      to={`/detail/${item.id}`}
      className="glass rounded-2xl p-4 block no-underline hover:scale-[1.02] transition-transform"
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${TYPE_COLORS[item.type] || 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300'}`}>
            {TYPE_ICONS[item.type]} {item.type.toUpperCase()}
          </span>
          {freshnessLabel && (
            <span className={`text-xs px-1.5 py-0.5 rounded-full ${
              freshnessLabel === 'active' ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-300' :
              freshnessLabel === 'recent' ? 'bg-sky-100 text-sky-700 dark:bg-sky-900/50 dark:text-sky-300' :
              'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'
            }`}>
              {freshnessLabel}
            </span>
          )}
        </div>
        {item.stars != null && item.stars > 0 && (
          <span className="text-xs text-gray-400 whitespace-nowrap">
            ⭐ {formatStars(item.stars)}
          </span>
        )}
        {/* Rules/Prompts: show source badge instead of stars */}
        {(item.type === 'rule' || item.type === 'prompt') && (!item.stars || item.stars === 0) && item.source && (
          <span className="text-xs text-gray-400 whitespace-nowrap truncate max-w-24">
            {item.source}
          </span>
        )}
      </div>

      <h3 className="text-sm font-semibold text-gray-900 dark:text-white truncate mb-1">
        {highlight ? highlightText(item.name, highlight) : item.name}
      </h3>

      <p className={`text-xs text-gray-500 dark:text-gray-400 leading-relaxed ${compact ? 'line-clamp-2' : 'line-clamp-3'}`}>
        {highlight ? highlightText(desc, highlight) : desc}
      </p>

      {/* Score bar */}
      {item.final_score > 0 && (
        <div className="mt-3 flex items-center gap-2">
          <div className="score-bar flex-1">
            <div className="score-bar-fill" style={{ width: `${item.final_score}%` }} />
          </div>
          <span className="text-xs text-gray-400 dark:text-gray-500 font-medium">{Math.round(item.final_score)}</span>
        </div>
      )}

      {/* Category tag */}
      {item.category && !compact && (
        <div className="mt-2">
          <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400">
            {item.category}
          </span>
        </div>
      )}
    </Link>
  )
}

function highlightText(text: string, query: string) {
  if (!query) return text
  const parts = text.split(new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi'))
  return parts.map((part, i) =>
    part.toLowerCase() === query.toLowerCase()
      ? <mark key={i} className="bg-yellow-200 dark:bg-yellow-700/50 rounded px-0.5">{part}</mark>
      : part
  )
}
