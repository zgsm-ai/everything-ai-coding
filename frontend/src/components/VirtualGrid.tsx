import { useEffect, useRef, useState } from 'react'
import { useWindowVirtualizer } from '@tanstack/react-virtual'
import { columnsForWidth, rowCount as computeRowCount, rowItems } from './gridColumns'

/**
 * Window-scrolling virtualized card grid for large result sets (the Browse
 * page can render thousands of cards). Only the rows in (or near) the viewport
 * are mounted, so the DOM node count stays bounded regardless of result size.
 *
 * Design notes:
 *  - We virtualize *rows*, where each row packs ``columns`` cards. The column
 *    count mirrors the previous Tailwind grid (``grid-cols-1 sm:2 lg:3``) by
 *    reading the same viewport breakpoints (sm=640, lg=1024), so the responsive
 *    layout is unchanged.
 *  - We use the *window* as the scroll element (``useWindowVirtualizer``). The
 *    page already scrolls the document (sticky nav, no inner scroll container),
 *    so introducing an inner scrollbar would break the sticky nav and the
 *    overall layout. Window virtualization keeps the existing scroll behaviour.
 *  - Rows are dynamically measured (``measureElement``) so variable card heights
 *    (2- vs 3-line clamp, optional score bar / category tag) are never clipped.
 */

const GAP_PX = 16 // Tailwind gap-4 = 1rem = 16px
const ESTIMATED_ROW_PX = 168 // card (~152) + gap; refined live via measureElement

function useColumns(): number {
  const [columns, setColumns] = useState(() =>
    columnsForWidth(typeof window === 'undefined' ? 1024 : window.innerWidth)
  )
  useEffect(() => {
    const update = () => setColumns(columnsForWidth(window.innerWidth))
    update()
    window.addEventListener('resize', update)
    return () => window.removeEventListener('resize', update)
  }, [])
  return columns
}

interface Props<T> {
  items: T[]
  /** Stable key per item (used for React keys). */
  getKey: (item: T) => string
  renderItem: (item: T) => React.ReactNode
}

export default function VirtualGrid<T>({ items, getKey, renderItem }: Props<T>) {
  const columns = useColumns()
  const parentRef = useRef<HTMLDivElement>(null)
  // Offset of the grid container from the top of the document, so the window
  // virtualizer knows where this list begins within the page scroll.
  const [scrollMargin, setScrollMargin] = useState(0)

  useEffect(() => {
    const el = parentRef.current
    if (!el) return
    const measure = () => {
      setScrollMargin(el.getBoundingClientRect().top + window.scrollY)
    }
    measure()
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [])

  const rowCount = computeRowCount(items.length, columns)

  const virtualizer = useWindowVirtualizer({
    count: rowCount,
    estimateSize: () => ESTIMATED_ROW_PX,
    overscan: 4,
    scrollMargin,
    // Re-key the virtualizer's measurement cache when the column count changes
    // so a resize that reflows rows re-measures from scratch.
    getItemKey: (rowIdx) => `${columns}:${rowIdx}`,
  })

  const virtualRows = virtualizer.getVirtualItems()

  return (
    <div ref={parentRef}>
      <div
        style={{
          height: virtualizer.getTotalSize(),
          position: 'relative',
          width: '100%',
        }}
      >
        {virtualRows.map((virtualRow) => {
          const cells = rowItems(items, virtualRow.index, columns)
          return (
            <div
              key={virtualRow.key}
              data-index={virtualRow.index}
              ref={virtualizer.measureElement}
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                transform: `translateY(${virtualRow.start - virtualizer.options.scrollMargin}px)`,
              }}
            >
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`,
                  gap: GAP_PX,
                  paddingBottom: GAP_PX,
                }}
              >
                {cells.map((item) => (
                  <div key={getKey(item)}>{renderItem(item)}</div>
                ))}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
