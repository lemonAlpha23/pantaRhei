<script setup lang="ts">
import { computed, onBeforeUnmount, ref, shallowReactive, watch } from 'vue'
import { ChartNoAxesCombined, Plus } from 'lucide-vue-next'
import { usePageWindowState, useWindowContext } from '../../../core/page-window'
import { comparisonDates, comparisonRanges, maxComparisons, restoreComparison, restoreComparisonWindow, type ComparisonLoad } from './compare'
import { errorText, getMarketApi } from '../api'
import { useWorkspace } from '../store'
import CompareCard from './CompareCard.vue'
import { useWindowUpdates } from '../../../core/window-updates'

const store = useWorkspace()
const market = getMarketApi()
const storageKey = 'pantarhei.compare.v1'
const { detached } = useWindowContext()
let storage: Storage | undefined
const catalog = computed(() => new Map(store.instruments.map(stock => [stock.symbol, stock])))
const available = [...new Set([store.selected, ...store.watchlist, ...catalog.value.keys()])].filter(code => catalog.value.has(code))
let saved: string | null = null
try {
  storage = detached ? sessionStorage : localStorage
  saved = storage.getItem(storageKey)
} catch { /* 无持久化权限时保留会话内选择。 */ }
const initial = restoreComparison(detached ? null : saved, available)
const symbols = ref(initial.symbols)
const range = ref(initial.range)
const states = shallowReactive(new Map<string, ComparisonLoad>())
const stocks = computed(() => symbols.value.flatMap(code => {
  const item = catalog.value.get(code)
  return item ? [item] : []
}))
const snapshot = usePageWindowState(
  () => ({ symbols: symbols.value.join(','), range: String(range.value) }),
  () => stocks.value.length ? '对比 · ' + stocks.value.map(stock => stock.name).join(' / ') : '对比',
)
const target = restoreComparisonWindow(snapshot, available, initial)
const restored = detached ? restoreComparison(saved, available, target) : target
symbols.value = restored.symbols
range.value = restored.range
const unused = computed(() => store.instruments.filter(stock => !symbols.value.includes(stock.symbol)))
const dates = computed(() => comparisonDates(symbols.value.flatMap(symbol => {
  const state = states.get(symbol)
  return state?.status === 'ready' ? [state.history] : []
}), range.value))

const read = async (symbol: string, updated = false) => {
  if (!updated && states.get(symbol)?.status === 'loading') return
  const pending: ComparisonLoad = { status: 'loading' }
  states.set(symbol, pending)
  try {
    const history = await market.getHistory(symbol)
    if (states.get(symbol) === pending) states.set(symbol, { status: 'ready', history })
  } catch (error) {
    if (states.get(symbol) === pending) states.set(symbol, { status: 'error', message: errorText(error, '日线读取失败') })
  }
}

useWindowUpdates('market', async symbol => {
  if (symbols.value.includes(symbol)) await read(symbol, true)
})

const replace = (before: string, after: string) => {
  if (!catalog.value.has(after) || symbols.value.includes(after)) return
  symbols.value = symbols.value.map(code => code === before ? after : code)
}
const add = (event: Event) => {
  const input = event.target as HTMLSelectElement
  const code = input.value
  input.value = ''
  if (symbols.value.length < maxComparisons && catalog.value.has(code) && !symbols.value.includes(code)) {
    symbols.value = [...symbols.value, code]
  }
}
const remove = (code: string) => { symbols.value = symbols.value.filter(symbol => symbol !== code) }

watch(symbols, selected => {
  for (const code of states.keys()) if (!selected.includes(code)) states.delete(code)
  for (const code of selected) if (!states.has(code)) void read(code)
}, { immediate: true })
watch([symbols, range], () => {
  try { storage?.setItem(storageKey, JSON.stringify({ symbols: symbols.value, range: range.value })) } catch { /* 会话内仍可使用。 */ }
}, { immediate: detached })

onBeforeUnmount(() => { states.clear() })
</script>

<template>
  <section class="compare" aria-labelledby="compare-title">
    <header class="view-heading">
      <h1 id="compare-title">多图对比</h1>
      <label class="add-stock" :class="{ unavailable: !unused.length || symbols.length >= maxComparisons }" :title="symbols.length >= maxComparisons ? '最多对比四只股票' : '从本地股票库添加'">
        <Plus :size="16" />添加股票
        <select value="" aria-label="添加对比股票" :disabled="!unused.length || symbols.length >= maxComparisons" @change="add">
          <option value="" disabled>选择股票</option>
          <option v-for="stock in unused" :key="stock.symbol" :value="stock.symbol">{{ stock.name }} · {{ stock.symbol }}</option>
        </select>
      </label>
    </header>

    <div v-if="stocks.length" class="toolbar">
      <div class="ranges" role="group" aria-label="对比交易日区间">
        <button v-for="choice in comparisonRanges" :key="choice" :aria-pressed="range === choice" @click="range = choice">
          {{ choice === 'all' ? '全部' : choice + '日' }}
        </button>
      </div>
      <span v-if="dates.length" class="interval">{{ dates[0] }} 至 {{ dates.at(-1) }} · {{ dates.length }} 个交易日</span>
    </div>
    <div v-if="stocks.length" class="chart-grid">
      <CompareCard v-for="stock in stocks" :key="stock.symbol" :stock="stock" :dates="dates" :load="states.get(stock.symbol)"
        :options="store.instruments.filter(item => item.symbol === stock.symbol || !symbols.includes(item.symbol))"
        @replace="next => replace(stock.symbol, next)" @remove="remove(stock.symbol)" @retry="read(stock.symbol)" />
    </div>
    <p v-if="stocks.length" class="method">各图按所选股票的交易日对齐。区间变动为末日收盘价相对首日收盘价的变化，缺少任一端点时显示「—」。不复权行情受除权除息影响。</p>
    <div v-else class="empty compare-empty">
      <ChartNoAxesCombined :size="26" /><strong>{{ catalog.size ? '添加股票开始对比' : '本地股票库为空' }}</strong>
    </div>
  </section>
</template>

<style scoped lang="scss">
.compare { min-width: 0; }
.view-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 22px;
  h1 { font-size: clamp(30px, 3vw, 44px); font-weight: 550; letter-spacing: -.05em; }
}
.add-stock {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  min-height: 38px;
  padding: 0 16px;
  border-radius: 100px;
  color: white;
  background: var(--primary);
  font-size: 14px;
  font-weight: 550;
  white-space: nowrap;
  &:hover:not(.unavailable) { background: var(--primary-active); }
  &:focus-within { outline: 2px solid var(--primary); outline-offset: 3px; }
  &.unavailable { background: var(--soft); color: var(--dim); }
  select { position: absolute; inset: 0; width: 100%; height: 100%; opacity: 0; cursor: pointer; }
  select:disabled { cursor: default; }
}
.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px 16px;
  margin-bottom: 16px;
}
.ranges {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 2px;
  button {
    min-height: 31px;
    padding: 0 12px;
    color: var(--muted);
    border-radius: 100px;
    font-size: 13px;
    &:hover { background: var(--soft); }
    &[aria-pressed='true'] { color: var(--primary); font-weight: 600; background: var(--primary-soft); }
  }
}
.interval, .method { color: var(--muted); font-size: 12px; }
.interval { font-variant-numeric: tabular-nums; }
.chart-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: clamp(14px, 2vw, 26px); }
.method { margin-top: 17px; line-height: 1.7; }
.compare-empty { min-height: 300px; border-top: 1px solid var(--line); }
@media (max-width: 760px) {
  .view-heading { margin-bottom: 15px; }
  .chart-grid { grid-template-columns: minmax(0, 1fr); }
  .ranges button { padding-inline: 10px; }
}
</style>
