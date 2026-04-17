import { useI18n } from '../hooks/useI18n'
import { useTheme } from '../hooks/useTheme'

interface Props {
  signals: {
    freshness: number
    popularity: number
    source_trust: number
  }
}

const AXES = [
  { key: 'popularity' as const, i18nKey: 'health.popularity', angle: -90 },
  { key: 'freshness' as const, i18nKey: 'health.freshness', angle: 30 },
  { key: 'source_trust' as const, i18nKey: 'health.source_trust', angle: 150 },
]

// Layout: generous padding so labels never clip
const PAD_X = 80  // horizontal padding for left/right labels
const PAD_Y = 30  // vertical padding for top/bottom labels
const RADIUS = 65
const CX = PAD_X + RADIUS
const CY = PAD_Y + RADIUS
const WIDTH = 2 * (PAD_X + RADIUS)
const HEIGHT = 2 * (PAD_Y + RADIUS)

function polar(angle: number, r: number) {
  const rad = (angle * Math.PI) / 180
  return { x: CX + r * Math.cos(rad), y: CY + r * Math.sin(rad) }
}

export default function RadarChart({ signals }: Props) {
  const { t } = useI18n()
  const { theme } = useTheme()
  const isDark = theme === 'dark'
  const gridLevels = [0.25, 0.5, 0.75, 1]
  const gridColor = isDark ? '#374151' : '#e5e7eb'
  const labelClass = isDark ? 'text-[11px] fill-gray-400' : 'text-[11px] fill-gray-500'

  const dataPoints = AXES.map(a => polar(a.angle, RADIUS * ((signals[a.key] || 0) / 100)))
  const dataPath = dataPoints.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ') + 'Z'

  // Label positions: place them outside the chart near each vertex
  const labelPos: Record<string, { x: number; y: number; anchor: 'start' | 'middle' | 'end' }> = {
    popularity:   { x: CX,              y: PAD_Y - 14,           anchor: 'middle' }, // top center
    freshness:    { x: WIDTH - 16,      y: CY + RADIUS * 0.6,   anchor: 'end' },    // bottom right
    source_trust: { x: 16,              y: CY + RADIUS * 0.6,   anchor: 'start' },  // bottom left
  }

  return (
    <svg width={WIDTH} height={HEIGHT} viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="block mx-auto">
      {/* Grid polygons */}
      {gridLevels.map(level => {
        const pts = AXES.map(a => polar(a.angle, RADIUS * level))
        const d = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ') + 'Z'
        return <path key={level} d={d} fill="none" stroke={gridColor} strokeWidth={1} />
      })}

      {/* Axis lines */}
      {AXES.map(a => {
        const end = polar(a.angle, RADIUS)
        return <line key={a.key} x1={CX} y1={CY} x2={end.x} y2={end.y} stroke={gridColor} strokeWidth={1} />
      })}

      {/* Data polygon */}
      <path d={dataPath} fill="rgba(0,113,227,0.15)" stroke="#0071e3" strokeWidth={2} />

      {/* Data dots */}
      {dataPoints.map((p, i) => (
        <circle key={i} cx={p.x} cy={p.y} r={3} fill="#0071e3" />
      ))}

      {/* Labels — placed at fixed edge positions */}
      {AXES.map(axis => {
        const val = Math.round(signals[axis.key] || 0)
        const lp = labelPos[axis.key]
        return (
          <text
            key={axis.key}
            x={lp.x}
            y={lp.y}
            textAnchor={lp.anchor}
            dominantBaseline="middle"
            className={labelClass}
          >
            {t(axis.i18nKey)} ({val})
          </text>
        )
      })}
    </svg>
  )
}
