<script setup lang="ts">
import { reactive } from 'vue'
import { ChartCandlestick, CircleAlert, Database, RefreshCw } from 'lucide-vue-next'
import { usePageWindowState } from '../../core/page-window'
import { chartSnapshot, restoreChartSettings } from './chart-settings'
import { useWorkspace } from './store'
import { useMarketNavigation } from './navigation'
import { useChartOrderMarks } from './order-marks'
import HistoryTable from './components/HistoryTable.vue'
import MarketDetails from './components/MarketDetails.vue'
import PriceChart from './components/PriceChart.vue'
import QuoteSummary from './components/QuoteSummary.vue'
import Watchlist from './components/Watchlist.vue'

const store = useWorkspace()
const { search, openStock } = useMarketNavigation()
const chart = reactive(restoreChartSettings({}))
const initial = usePageWindowState(
  () => ({ symbol: store.selected, ...chartSnapshot(chart) }),
  () => store.current ? `行情 · ${store.current.name} ${store.selected}` : '行情',
)
Object.assign(chart, restoreChartSettings(initial))
if (store.selected !== initial.symbol && store.instruments.some(stock => stock.symbol === initial.symbol)) {
  void store.select(initial.symbol)
}
const { available, enabled, items: orderMarks, status, setEnabled, refresh: refreshMarks } =
  useChartOrderMarks(() => store.selected, () => store.history?.bars, () => chart.mode === 'candle')
const toggleMarks = (event: Event) => setEnabled((event.currentTarget as HTMLInputElement).checked)
</script>

<template>
  <div v-if="!store.current" class="empty page-state">
    <Database :size="25" /><strong>本地股票库为空</strong>
    <button class="action primary" @click="search()">查找股票</button>
  </div>
  <div v-else class="market-grid">
    <div class="main-column">
      <QuoteSummary />
      <div v-if="store.loading" class="empty chart-state" role="status">
        <RefreshCw :size="22" class="spin" /><strong>正在加载日线</strong>
      </div>
      <div v-else-if="store.historyError" class="empty chart-state" role="alert">
        <CircleAlert :size="24" /><strong>{{ store.historyError }}</strong>
        <button class="action" @click="store.select(store.selected)">重新加载</button>
      </div>
      <template v-else-if="store.history?.bars.length">
        <PriceChart :bars="store.history.bars" :symbol="store.selected" v-model:range="chart.range" v-model:mode="chart.mode"
          v-model:ma5="chart.ma5" v-model:ma20="chart.ma20" v-model:volume="chart.volume"
          :adjustment="store.history.adjustment" :order-marks="orderMarks" :order-marks-enabled="enabled && chart.mode === 'candle'">
          <template v-if="available && chart.mode === 'candle'" #order-controls>
            <label class="order-toggle">
              <input type="checkbox" role="switch" aria-label="博主下单标记" :checked="enabled" @change="toggleMarks">
              博主下单标记
            </label>
            <span v-if="enabled && status === 'loading'" class="order-status" role="status">读取中…</span>
            <span v-else-if="enabled && status === 'ready' && !orderMarks.length" class="order-status">当前股票日线范围内暂无下单披露</span>
            <span v-else-if="enabled && status === 'error'" class="order-status" role="status">
              标记读取失败 <button type="button" @click="refreshMarks">重试</button>
            </span>
          </template>
        </PriceChart>
        <HistoryTable :bars="store.history.bars" />
      </template>
      <div v-else class="empty chart-state">
        <ChartCandlestick :size="25" /><strong>暂无历史日线</strong>
        <button class="action" :disabled="store.refreshing" @click="store.refresh">联网更新</button>
      </div>
    </div>
    <aside class="side-column" aria-label="股票列表和交易概况">
      <Watchlist @select="openStock" @search="search(true)" />
      <MarketDetails />
    </aside>
  </div>
</template>

<style scoped lang="scss">
.market-grid { display: grid; grid-template-columns: minmax(0, 1fr) clamp(310px, 25vw, 360px); gap: clamp(28px, 4vw, 62px); }
.main-column, .side-column { display: flex; flex-direction: column; min-width: 0; align-self: start; }
.main-column { gap: 30px; }
.side-column { gap: 20px; }
.page-state { min-height: 55vh; }
.chart-state { min-height: 340px; background: var(--soft); border-radius: 20px; }
.order-toggle {
  display: inline-flex; align-items: center; gap: 6px; padding: 4px 0; cursor: pointer;
  color: var(--muted); font-size: 12px; font-weight: 500;
  input {
    appearance: none; position: relative; flex: none; width: 24px; height: 14px; margin: 0; cursor: pointer;
    border: 1px solid var(--muted); border-radius: 10px; background: var(--surface);
    &::after { content: ''; position: absolute; top: 2px; left: 2px; width: 8px; height: 8px; border-radius: 100%; background: var(--muted); }
    &:checked { border-color: var(--primary); background: var(--primary); }
    &:checked::after { transform: translateX(10px); background: white; }
    &:focus-visible { outline: 2px solid var(--primary); outline-offset: 3px; }
  }
}
.order-status { color: var(--muted); font-size: 12px; button { color: var(--primary); } }
.spin { animation: rotate 1s linear infinite; }
@keyframes rotate { to { transform: rotate(360deg); } }
@media (max-width: 940px) {
  .market-grid { grid-template-columns: 1fr; }
  .side-column { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
}
@media (max-width: 680px) {
  .main-column { gap: 24px; }
  .market-grid { gap: 23px; }
  .side-column { grid-template-columns: 1fr; }
}
</style>
