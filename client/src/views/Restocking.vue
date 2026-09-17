<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.budget') }}</h3>
        </div>
        <div class="budget-panel">
          <div class="budget-amount">{{ formatMoney(budget) }}</div>
          <input
            v-model.number="budget"
            type="range"
            class="budget-slider"
            min="0"
            :max="budgetCeiling"
            :step="budgetStep"
            @input="resetBasket"
          />
          <div class="budget-scale">
            <span>{{ formatMoney(0) }}</span>
            <span>{{ formatMoney(budgetCeiling) }}</span>
          </div>
          <p class="budget-help">{{ t('restocking.budgetHelp') }}</p>
        </div>
      </div>

      <div v-if="rows.length === 0" class="card">
        <div class="empty-state">{{ t('restocking.noCandidates') }}</div>
      </div>

      <div v-else class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.recommended') }}</h3>
          <span class="card-subtitle">{{ t('restocking.recommendedHelp') }}</span>
        </div>

        <div class="table-container">
          <table class="restocking-table">
            <thead>
              <tr>
                <th class="col-include">{{ t('restocking.table.include') }}</th>
                <th class="col-sku">{{ t('restocking.table.sku') }}</th>
                <th class="col-name">{{ t('restocking.table.itemName') }}</th>
                <th class="col-num">{{ t('restocking.table.onHand') }}</th>
                <th class="col-num">{{ t('restocking.table.forecast') }}</th>
                <th class="col-num">{{ t('restocking.table.shortfall') }}</th>
                <th class="col-trend">{{ t('restocking.table.trend') }}</th>
                <th class="col-num">{{ t('restocking.table.unitCost') }}</th>
                <th class="col-qty">{{ t('restocking.table.quantity') }}</th>
                <th class="col-num">{{ t('restocking.table.lineTotal') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in rows" :key="row.sku" :class="{ 'row-excluded': !row.selected }">
                <td class="col-include">
                  <input v-model="row.selected" type="checkbox" class="row-check" />
                </td>
                <td class="col-sku"><strong>{{ row.sku }}</strong></td>
                <td class="col-name">{{ translateProductName(row.name) }}</td>
                <td class="col-num">{{ row.onHand.toLocaleString() }}</td>
                <td class="col-num">{{ row.forecastDemand.toLocaleString() }}</td>
                <td class="col-num shortfall">{{ row.shortfall.toLocaleString() }}</td>
                <td class="col-trend">
                  <span :class="['badge', row.trend]">{{ t(`trends.${row.trend}`) }}</span>
                </td>
                <td class="col-num">{{ formatMoney(row.unitCost) }}</td>
                <td class="col-qty">
                  <input
                    v-model.number="row.quantity"
                    type="number"
                    class="qty-input"
                    min="0"
                    :disabled="!row.selected"
                  />
                </td>
                <td class="col-num">{{ formatMoney(lineTotal(row)) }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="budget-meter">
          <div class="meter-figures">
            <div class="meter-figure">
              <span class="meter-label">{{ t('restocking.allocated') }}</span>
              <span class="meter-value">{{ formatMoney(allocated) }}</span>
            </div>
            <div class="meter-figure">
              <span class="meter-label">{{ t('restocking.remaining') }}</span>
              <span :class="['meter-value', { negative: overBudget }]">
                {{ formatMoney(Math.max(0, budget - allocated)) }}
              </span>
            </div>
            <div class="meter-figure">
              <span class="meter-label">{{ t('restocking.itemsSelected', { count: selectedCount, total: rows.length }) }}</span>
            </div>
          </div>

          <div class="meter-track">
            <div class="meter-fill" :class="{ over: overBudget }" :style="{ width: meterWidth }"></div>
          </div>

          <div v-if="overBudget" class="meter-warning">
            {{ t('restocking.overBudget', { amount: formatMoney(allocated - budget) }) }}
          </div>
          <div v-else-if="selectedCount === 0" class="meter-hint">
            {{ t('restocking.noSelection') }}
          </div>
        </div>

        <div class="order-actions">
          <div v-if="submitMessage" :class="['submit-message', submitFailed ? 'failed' : 'succeeded']">
            {{ submitMessage }}
          </div>
          <button class="place-order-btn" :disabled="!canPlaceOrder" @click="placeOrder">
            {{ submitting ? t('restocking.placing') : t('restocking.placeOrder') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted, watch } from 'vue'
import { api } from '../api'
import { useFilters } from '../composables/useFilters'
import { useI18n } from '../composables/useI18n'
import { formatCurrency } from '../utils/currency'
import {
  buildCandidates,
  recommendBasket,
  basketTotal,
  basketToOrderLines
} from '../utils/restocking'

export default {
  name: 'Restocking',
  setup() {
    const { t, currentCurrency, translateProductName } = useI18n()

    const loading = ref(true)
    const error = ref(null)
    const candidates = ref([])
    const rows = ref([])
    const budget = ref(0)
    const submitting = ref(false)
    const submitMessage = ref('')
    const submitFailed = ref(false)

    // Restocking is a forward-looking decision, so only the two spatial
    // filters apply. Time period and order status are deliberately ignored.
    const { selectedLocation, selectedCategory, getCurrentFilters } = useFilters()

    // The slider spans nothing to everything, rounded up so the top of the
    // track is a round number rather than a stray total like $70,311.
    const budgetCeiling = computed(() => {
      const total = candidates.value.reduce((sum, c) => sum + c.fullCost, 0)
      if (total <= 0) return 1000
      const magnitude = Math.pow(10, Math.floor(Math.log10(total)) - 1)
      return Math.ceil(total / magnitude) * magnitude
    })

    const budgetStep = computed(() => Math.max(1, Math.round(budgetCeiling.value / 200)))

    const allocated = computed(() => basketTotal(rows.value))
    const selectedCount = computed(() => rows.value.filter(r => r.selected && r.quantity > 0).length)
    const overBudget = computed(() => allocated.value > budget.value)

    const meterWidth = computed(() => {
      if (budget.value <= 0) return '0%'
      return `${Math.min(100, (allocated.value / budget.value) * 100)}%`
    })

    const canPlaceOrder = computed(() =>
      !submitting.value && selectedCount.value > 0 && !overBudget.value
    )

    const formatMoney = (value) => formatCurrency(value, currentCurrency.value)
    const lineTotal = (row) => (row.selected ? row.quantity * row.unitCost : 0)

    // Rows are user-editable after the slider proposes them, so the basket is
    // a ref the slider rewrites rather than a computed that would throw away
    // hand-edits on every unrelated re-render.
    const resetBasket = () => {
      rows.value = recommendBasket(candidates.value, budget.value)
      submitMessage.value = ''
    }

    const load = async () => {
      try {
        loading.value = true
        error.value = null
        const filters = getCurrentFilters()
        const [forecasts, inventory] = await Promise.all([
          api.getDemandForecasts(),
          api.getInventory({ warehouse: filters.warehouse, category: filters.category })
        ])

        candidates.value = buildCandidates(forecasts, inventory)
        // Open on half the ceiling so the screen arrives with a basket to look
        // at rather than an empty table the user has to discover the slider to fill.
        budget.value = Math.round(budgetCeiling.value / 2)
        resetBasket()
      } catch (err) {
        error.value = 'Failed to load restocking data: ' + err.message
      } finally {
        loading.value = false
      }
    }

    const placeOrder = async () => {
      try {
        submitting.value = true
        submitMessage.value = ''
        submitFailed.value = false

        const filters = getCurrentFilters()
        const order = await api.createRestockOrder({
          lines: basketToOrderLines(rows.value),
          budget: budget.value,
          // The API treats absent as "no constraint"; 'all' is a UI value.
          warehouse: filters.warehouse === 'all' ? null : filters.warehouse,
          category: filters.category === 'all' ? null : filters.category
        })

        submitMessage.value = t('restocking.orderPlaced', {
          orderNumber: order.order_number,
          days: order.lead_time_days
        })
        resetBasket()
      } catch (err) {
        submitFailed.value = true
        const detail = err.response?.data?.detail || err.message
        submitMessage.value = t('restocking.orderFailed', { message: detail })
      } finally {
        submitting.value = false
      }
    }

    watch([selectedLocation, selectedCategory], load)
    onMounted(load)

    return {
      t,
      loading,
      error,
      rows,
      budget,
      budgetCeiling,
      budgetStep,
      allocated,
      selectedCount,
      overBudget,
      meterWidth,
      canPlaceOrder,
      submitting,
      submitMessage,
      submitFailed,
      formatMoney,
      lineTotal,
      resetBasket,
      placeOrder,
      translateProductName
    }
  }
}
</script>

<style scoped>
.budget-panel {
  padding: 1.5rem;
}

.budget-amount {
  font-size: 2rem;
  font-weight: 700;
  color: #0f172a;
  margin-bottom: 1rem;
}

.budget-slider {
  width: 100%;
  appearance: none;
  height: 6px;
  border-radius: 3px;
  background: #e2e8f0;
  outline: none;
  cursor: pointer;
}

.budget-slider::-webkit-slider-thumb {
  appearance: none;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #2563eb;
  border: 2px solid #ffffff;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.3);
  cursor: pointer;
}

.budget-slider::-moz-range-thumb {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #2563eb;
  border: 2px solid #ffffff;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.3);
  cursor: pointer;
}

.budget-scale {
  display: flex;
  justify-content: space-between;
  font-size: 0.75rem;
  color: #94a3b8;
  margin-top: 0.5rem;
}

.budget-help {
  font-size: 0.875rem;
  color: #64748b;
  margin: 0.75rem 0 0;
}

.card-subtitle {
  font-size: 0.875rem;
  color: #64748b;
}

.empty-state {
  padding: 2.5rem 1.5rem;
  text-align: center;
  color: #64748b;
}

.restocking-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
}

.restocking-table th,
.restocking-table td {
  padding: 0.75rem 1rem;
  border-bottom: 1px solid #e2e8f0;
  text-align: left;
  font-size: 0.875rem;
}

.restocking-table th {
  color: #64748b;
  font-weight: 600;
  white-space: nowrap;
}

.col-include { width: 70px; }
.col-sku { width: 100px; }
.col-name { width: 220px; }
.col-num { width: 110px; text-align: right; }
.col-trend { width: 110px; }
.col-qty { width: 110px; }

.restocking-table td.col-num { text-align: right; }

.row-excluded {
  opacity: 0.45;
}

.shortfall {
  font-weight: 600;
  color: #b45309;
}

.row-check {
  width: 16px;
  height: 16px;
  cursor: pointer;
  accent-color: #2563eb;
}

.qty-input {
  width: 90px;
  padding: 0.375rem 0.5rem;
  border: 2px solid #e2e8f0;
  border-radius: 6px;
  font-size: 0.875rem;
  font-family: inherit;
  text-align: right;
  transition: border-color 0.2s ease;
}

.qty-input:focus {
  outline: none;
  border-color: #2563eb;
}

.qty-input:disabled {
  background: #f8fafc;
  color: #94a3b8;
  cursor: not-allowed;
}

.budget-meter {
  padding: 1.25rem 1.5rem;
  border-top: 1px solid #e2e8f0;
}

.meter-figures {
  display: flex;
  gap: 2.5rem;
  flex-wrap: wrap;
  margin-bottom: 0.75rem;
}

.meter-figure {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.meter-label {
  font-size: 0.75rem;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.meter-value {
  font-size: 1.25rem;
  font-weight: 600;
  color: #0f172a;
}

.meter-value.negative {
  color: #dc2626;
}

.meter-track {
  height: 8px;
  border-radius: 4px;
  background: #e2e8f0;
  overflow: hidden;
}

.meter-fill {
  height: 100%;
  background: #2563eb;
  transition: width 0.2s ease;
}

.meter-fill.over {
  background: #dc2626;
}

.meter-warning {
  margin-top: 0.75rem;
  font-size: 0.875rem;
  font-weight: 600;
  color: #dc2626;
}

.meter-hint {
  margin-top: 0.75rem;
  font-size: 0.875rem;
  color: #64748b;
}

.order-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 1rem;
  padding: 1.25rem 1.5rem;
  border-top: 1px solid #e2e8f0;
  flex-wrap: wrap;
}

.submit-message {
  font-size: 0.875rem;
  font-weight: 500;
  margin-right: auto;
}

.submit-message.succeeded {
  color: #15803d;
}

.submit-message.failed {
  color: #dc2626;
}

.place-order-btn {
  padding: 0.75rem 1.75rem;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border: none;
  border-radius: 8px;
  font-weight: 600;
  font-size: 0.938rem;
  font-family: inherit;
  cursor: pointer;
  transition: transform 0.2s ease, opacity 0.2s ease;
  white-space: nowrap;
}

.place-order-btn:hover:not(:disabled) {
  transform: translateY(-2px);
}

.place-order-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
