/**
 * Pure responsive-column helper for the virtualized result grid, kept in its
 * own module so ``VirtualGrid.tsx`` only exports a component (react-refresh) and
 * so the breakpoint contract can be unit-tested without a DOM.
 *
 * Mirrors Tailwind's ``grid-cols-1 sm:2 lg:3`` viewport breakpoints
 * (sm=640, lg=1024) so the virtualized layout matches the previous CSS grid.
 */
export function columnsForWidth(width: number): number {
  if (width >= 1024) return 3 // lg
  if (width >= 640) return 2 // sm
  return 1
}

/** Total virtualized rows needed to lay out ``count`` items at ``columns`` wide. */
export function rowCount(count: number, columns: number): number {
  if (columns < 1) return 0
  return Math.ceil(count / columns)
}

/**
 * Slice the cards that belong to virtualized row ``rowIndex`` (``columns`` per
 * row). This is the packing contract the virtualizer relies on: only the rows
 * the virtualizer mounts call this, so the number of cards put into the DOM is
 * ``mountedRows * columns`` — bounded by the viewport + overscan, *independent*
 * of ``items.length``. Kept pure (and split out of the component) so that
 * DOM-free invariant can be unit-tested.
 */
export function rowItems<T>(items: T[], rowIndex: number, columns: number): T[] {
  if (columns < 1) return []
  const start = rowIndex * columns
  return items.slice(start, start + columns)
}
