import { describe, expect, it } from 'vitest'

import { columnsForWidth, rowCount, rowItems } from './gridColumns'

/**
 * The grid virtualizer packs ``columnsForWidth`` cards per virtualized row, so
 * this mapping is the contract that keeps the virtualized layout identical to
 * the previous Tailwind ``grid-cols-1 sm:2 lg:3`` grid. A regression here would
 * silently change the visible column count (and miscompute row geometry), so it
 * is worth locking down. Pure function → no DOM needed (test env is node).
 */
describe('VirtualGrid columnsForWidth', () => {
  it('mirrors the Tailwind sm=640 / lg=1024 breakpoints', () => {
    // < sm → 1 column
    expect(columnsForWidth(0)).toBe(1)
    expect(columnsForWidth(320)).toBe(1)
    expect(columnsForWidth(639)).toBe(1)
    // [sm, lg) → 2 columns
    expect(columnsForWidth(640)).toBe(2)
    expect(columnsForWidth(800)).toBe(2)
    expect(columnsForWidth(1023)).toBe(2)
    // >= lg → 3 columns
    expect(columnsForWidth(1024)).toBe(3)
    expect(columnsForWidth(1920)).toBe(3)
  })

  it('never returns fewer than one column (slicing items by 0 would loop)', () => {
    for (const w of [-100, 0, 1, 639, 640, 1024, 4000]) {
      expect(columnsForWidth(w)).toBeGreaterThanOrEqual(1)
    }
  })
})

describe('VirtualGrid row packing', () => {
  it('computes the row count from item count and columns (ceil)', () => {
    expect(rowCount(0, 3)).toBe(0)
    expect(rowCount(1, 3)).toBe(1) // partial first row
    expect(rowCount(3, 3)).toBe(1)
    expect(rowCount(4, 3)).toBe(2) // 4th card spills to row 2
    expect(rowCount(10, 3)).toBe(4)
    expect(rowCount(10, 2)).toBe(5)
  })

  it('packs each row with exactly `columns` items (last row may be short)', () => {
    const items = Array.from({ length: 10 }, (_, i) => i)
    expect(rowItems(items, 0, 3)).toEqual([0, 1, 2])
    expect(rowItems(items, 1, 3)).toEqual([3, 4, 5])
    expect(rowItems(items, 2, 3)).toEqual([6, 7, 8])
    expect(rowItems(items, 3, 3)).toEqual([9]) // short tail row
    expect(rowItems(items, 4, 3)).toEqual([]) // out-of-range row → no cells
  })

  it('bounds mounted DOM cells to (mountedRows × columns) regardless of total size', () => {
    // The virtualization invariant: the virtualizer only renders the visible
    // rows + overscan, so only those rows call rowItems(). Summing the cells of
    // a *fixed* window of mounted rows yields a node count independent of the
    // full result size — this is what keeps thousands of results from flooding
    // the DOM. We assert it directly on the packing helper.
    const columns = 3
    const overscanWindow = 12 // e.g. ~8 visible rows + 4 overscan
    for (const total of [50, 500, 5000, 23590]) {
      const items = Array.from({ length: total }, (_, i) => i)
      let mountedCells = 0
      for (let r = 0; r < overscanWindow; r++) {
        mountedCells += rowItems(items, r, columns).length
      }
      // Never more than the window can hold, no matter how big `total` is.
      expect(mountedCells).toBeLessThanOrEqual(overscanWindow * columns)
      // And far below the full set once the result list is large.
      if (total > overscanWindow * columns) {
        expect(mountedCells).toBeLessThan(total)
      }
    }
  })

  it('renders cleanly for a tiny (sub-one-row) result set', () => {
    const items = [0, 1]
    expect(rowCount(items.length, 3)).toBe(1)
    expect(rowItems(items, 0, 3)).toEqual([0, 1])
    expect(rowItems(items, 1, 3)).toEqual([])
  })

  it('returns empty (never loops) for a zero/negative column count', () => {
    expect(rowCount(10, 0)).toBe(0)
    expect(rowItems([1, 2, 3], 0, 0)).toEqual([])
  })
})
