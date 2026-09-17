// Restocking recommendation logic.
//
// Kept free of Vue on purpose: this is the part worth unit-testing, and a pure
// module can be tested without mounting a component.

// Two forecast items can carry the same shortfall, so trend decides which is
// the more urgent. Lower rank wins.
const TREND_RANK = {
  increasing: 0,
  stable: 1,
  decreasing: 2
}

/**
 * Join demand forecasts to inventory records and keep the items that are short.
 *
 * Forecasts carry no cost, stock level, warehouse or category, so every one of
 * those comes from the matching inventory row. A forecast with no inventory
 * record cannot be priced and is dropped rather than shown at zero.
 */
export function buildCandidates(forecasts = [], inventory = []) {
  const bySku = new Map(inventory.map(item => [item.sku, item]))

  return forecasts
    .map(forecast => {
      const item = bySku.get(forecast.item_sku)
      if (!item) return null

      const shortfall = forecast.forecasted_demand - item.quantity_on_hand
      if (shortfall <= 0) return null

      return {
        sku: item.sku,
        name: item.name,
        category: item.category,
        warehouse: item.warehouse,
        unitCost: item.unit_cost,
        onHand: item.quantity_on_hand,
        reorderPoint: item.reorder_point,
        forecastDemand: forecast.forecasted_demand,
        currentDemand: forecast.current_demand,
        trend: forecast.trend,
        shortfall,
        fullCost: round2(shortfall * item.unit_cost)
      }
    })
    .filter(Boolean)
    .sort(compareUrgency)
}

/** Most short first; trend breaks a tie. */
function compareUrgency(a, b) {
  if (b.shortfall !== a.shortfall) return b.shortfall - a.shortfall
  const rankA = TREND_RANK[a.trend] ?? TREND_RANK.stable
  const rankB = TREND_RANK[b.trend] ?? TREND_RANK.stable
  return rankA - rankB
}

/**
 * Pick a basket that fits the budget, most urgent first.
 *
 * Greedy rather than optimal: walk the ranked list and take each item whose
 * full shortfall fits in what is left. An item that does not fit is skipped
 * rather than part-ordered, and the walk continues, so a cheap urgent item
 * still gets in after an expensive one was passed over.
 */
export function recommendBasket(candidates = [], budget = 0) {
  let remaining = Number(budget) || 0

  return candidates.map(candidate => {
    const affordable = candidate.fullCost > 0 && candidate.fullCost <= remaining
    if (affordable) remaining = round2(remaining - candidate.fullCost)

    return {
      ...candidate,
      selected: affordable,
      quantity: affordable ? candidate.shortfall : 0
    }
  })
}

/** Total cost of the rows the user currently has selected. */
export function basketTotal(rows = []) {
  return round2(
    rows
      .filter(row => row.selected && row.quantity > 0)
      .reduce((sum, row) => sum + row.quantity * row.unitCost, 0)
  )
}

/** The lines a submitted order carries, in the shape the API expects. */
export function basketToOrderLines(rows = []) {
  return rows
    .filter(row => row.selected && row.quantity > 0)
    .map(row => ({ sku: row.sku, quantity: Number(row.quantity) }))
}

// Money in this app is plain floats, so round at each step to stop the
// budget meter drifting by fractions of a cent as rows are toggled.
function round2(value) {
  return Math.round(value * 100) / 100
}
