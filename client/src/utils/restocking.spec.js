import { describe, it, expect } from 'vitest'
import {
  buildCandidates,
  recommendBasket,
  basketTotal,
  basketToOrderLines
} from './restocking'

const forecast = (sku, forecasted, trend = 'stable') => ({
  id: sku,
  item_sku: sku,
  item_name: `Item ${sku}`,
  current_demand: 100,
  forecasted_demand: forecasted,
  trend,
  period: 'Next 30 days'
})

const item = (sku, onHand, unitCost, extra = {}) => ({
  id: sku,
  sku,
  name: `Item ${sku}`,
  category: 'Actuators',
  warehouse: 'Tokyo',
  quantity_on_hand: onHand,
  reorder_point: 50,
  unit_cost: unitCost,
  location: 'Warehouse A-01',
  last_updated: '2025-09-30T10:00:00',
  ...extra
})

describe('buildCandidates', () => {
  it('joins a forecast to its inventory record', () => {
    const [candidate] = buildCandidates([forecast('AAA', 150)], [item('AAA', 100, 10)])

    expect(candidate.sku).toBe('AAA')
    expect(candidate.shortfall).toBe(50)
    expect(candidate.unitCost).toBe(10)
    expect(candidate.fullCost).toBe(500)
  })

  it('drops a forecast with no inventory record, since it cannot be priced', () => {
    expect(buildCandidates([forecast('GHOST', 500)], [item('AAA', 1, 1)])).toEqual([])
  })

  it('drops an item that is already stocked above forecast demand', () => {
    expect(buildCandidates([forecast('AAA', 100)], [item('AAA', 400, 10)])).toEqual([])
  })

  it('ranks the largest shortfall first', () => {
    const candidates = buildCandidates(
      [forecast('SMALL', 110), forecast('BIG', 900)],
      [item('SMALL', 100, 10), item('BIG', 100, 10)]
    )
    expect(candidates.map(c => c.sku)).toEqual(['BIG', 'SMALL'])
  })

  it('breaks a shortfall tie by trend, increasing before stable before decreasing', () => {
    const candidates = buildCandidates(
      [forecast('C', 200, 'decreasing'), forecast('A', 200, 'increasing'), forecast('B', 200, 'stable')],
      [item('A', 100, 1), item('B', 100, 1), item('C', 100, 1)]
    )
    expect(candidates.map(c => c.sku)).toEqual(['A', 'B', 'C'])
  })

  it('handles empty inputs', () => {
    expect(buildCandidates()).toEqual([])
    expect(buildCandidates([], [])).toEqual([])
  })
})

describe('recommendBasket', () => {
  // AAA is the more urgent (shortfall 400) but costs 4000; BBB costs 100.
  const candidates = buildCandidates(
    [forecast('AAA', 500), forecast('BBB', 200)],
    [item('AAA', 100, 10), item('BBB', 100, 1)]
  )

  it('selects nothing on a zero budget', () => {
    const rows = recommendBasket(candidates, 0)
    expect(rows.every(row => row.selected === false)).toBe(true)
    expect(rows.every(row => row.quantity === 0)).toBe(true)
  })

  it('selects nothing when the budget is below the cheapest item', () => {
    const rows = recommendBasket(candidates, 50)
    expect(rows.filter(row => row.selected)).toHaveLength(0)
  })

  it('selects everything when the budget covers it all', () => {
    const rows = recommendBasket(candidates, 100000)
    expect(rows.every(row => row.selected)).toBe(true)
    expect(rows.map(row => row.quantity)).toEqual([400, 100])
  })

  it('skips an unaffordable item and still takes a cheaper one behind it', () => {
    // 4000 for AAA does not fit in 500, but BBB's 100 does.
    const rows = recommendBasket(candidates, 500)
    const selected = rows.filter(row => row.selected).map(row => row.sku)
    expect(selected).toEqual(['BBB'])
  })

  it('never recommends more than the budget allows', () => {
    for (const budget of [0, 1, 99, 100, 101, 3999, 4000, 4100, 99999]) {
      const rows = recommendBasket(candidates, budget)
      expect(basketTotal(rows)).toBeLessThanOrEqual(budget)
    }
  })

  it('returns a row per candidate regardless of affordability', () => {
    expect(recommendBasket(candidates, 0)).toHaveLength(candidates.length)
  })

  it('treats a missing budget as zero rather than throwing', () => {
    expect(recommendBasket(candidates).every(row => !row.selected)).toBe(true)
  })
})

describe('basketTotal', () => {
  it('counts only selected rows with a positive quantity', () => {
    const rows = [
      { selected: true, quantity: 2, unitCost: 10 },
      { selected: false, quantity: 99, unitCost: 10 },
      { selected: true, quantity: 0, unitCost: 10 }
    ]
    expect(basketTotal(rows)).toBe(20)
  })

  it('is zero for an empty basket', () => {
    expect(basketTotal([])).toBe(0)
    expect(basketTotal()).toBe(0)
  })

  it('does not accumulate floating-point drift across many rows', () => {
    const rows = Array.from({ length: 10 }, () => ({ selected: true, quantity: 3, unitCost: 0.1 }))
    expect(basketTotal(rows)).toBe(3)
  })
})

describe('basketToOrderLines', () => {
  it('emits only sku and quantity for selected rows', () => {
    const rows = [
      { selected: true, quantity: 5, sku: 'AAA', unitCost: 1, name: 'x' },
      { selected: false, quantity: 5, sku: 'BBB', unitCost: 1, name: 'y' }
    ]
    expect(basketToOrderLines(rows)).toEqual([{ sku: 'AAA', quantity: 5 }])
  })

  it('coerces a quantity typed into an input back to a number', () => {
    const rows = [{ selected: true, quantity: '7', sku: 'AAA', unitCost: 1 }]
    expect(basketToOrderLines(rows)).toEqual([{ sku: 'AAA', quantity: 7 }])
  })

  it('is empty when nothing is selected', () => {
    expect(basketToOrderLines([{ selected: false, quantity: 1, sku: 'AAA' }])).toEqual([])
  })
})
