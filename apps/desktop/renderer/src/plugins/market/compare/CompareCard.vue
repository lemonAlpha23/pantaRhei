<script setup lang="ts">
import { computed } from 'vue'
import { ChevronDown, CircleAlert, RefreshCw, X } from 'lucide-vue-next'
import { comparisonSeries, type ComparisonLoad } from './compare'
import { direction, exchangeTag, number, percent } from '../format'
import type { Instrument } from '../api'
import CompareChart from './CompareChart.vue'
import StockAvatar from '../components/StockAvatar.vue'

const props = defineProps<{ stock: Instrument; options: Instrument[]; load?: ComparisonLoad; dates: string[] }>()
const emit = defineEmits<{ replace: [symbol: string]; remove: []; retry: [] }>()
const history = computed(() => props.load?.status === 'ready' ? props.load.history : null)
const series = computed(() => comparisonSeries(history.value?.bars ?? [], props.dates))
const coverage = computed(() => {
  const data = series.value
  if (!data.missing) return ''
  const missingEnds = [!data.start && '首日', !data.end && '末日'].filter(Boolean).join('、')
  return `缺 ${data.missing} 个交易日` + (missingEnds ? `，含区间${missingEnds}` : '')
})
const choose = (event: Event) => emit('replace', (event.target as HTMLSelectElement).value)
</script>

<template>
  <article class="compare-card" :aria-label="stock.name + '对比行情'">
    <header>
      <label class="stock-picker">
        <StockAvatar :symbol="stock.symbol" :name="stock.name" :sector="stock.sector" :size="38" />
        <span class="stock-label"><strong>{{ stock.name }} <ChevronDown :size="14" /></strong><small>{{ exchangeTag(stock.exchange) }} · {{ stock.symbol }}</small></span>
        <select :value="stock.symbol" :aria-label="'替换对比股票：' + stock.name" @change="choose">
          <option v-for="item in options" :key="item.symbol" :value="item.symbol">{{ item.name }} · {{ item.symbol }}</option>
        </select>
      </label>
      <button class="remove" :aria-label="'移除对比股票：' + stock.name" title="移除对比" @click="emit('remove')"><X :size="15" /></button>
    </header>
    <div v-if="!load || load.status === 'loading'" class="card-state" role="status"><RefreshCw class="spin" :size="20" />正在读取日线</div>
    <div v-else-if="load.status === 'error'" class="card-state" role="alert">
      <CircleAlert :size="19" /><span>{{ load.message }}</span><button class="action" :aria-label="'重试读取' + stock.name" @click="emit('retry')">重试</button>
    </div>
    <template v-else>
      <dl class="metrics">
        <div><dt>区间收盘变动</dt><dd :class="direction(series.change)">{{ percent(series.change) }}</dd></div>
        <div><dt>期末收盘</dt><dd class="price">{{ number(series.end?.close) }} <small>{{ stock.currency }}</small></dd></div>
      </dl>
      <CompareChart v-if="series.points.length > series.missing" :points="series.points" :name="stock.name" :currency="stock.currency" />
      <div v-else class="card-state no-bars">所选区间没有日线记录</div>
      <footer>
        <span>日 K · {{ history?.adjustment }} · {{ history?.source }}</span>
        <span>数据截至 {{ history?.asOf || '—' }}</span>
        <span v-if="coverage" class="coverage">{{ coverage }}</span>
      </footer>
    </template>
  </article>
</template>

<style scoped lang="scss">
.compare-card {
  min-width: 0;
  border: 1px solid var(--line);
  border-radius: 19px;
  padding: clamp(15px, 1.7vw, 24px);
  background: var(--surface);
}
header { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
.stock-picker {
  position: relative;
  display: inline-flex;
  align-items: center;
  min-width: 0;
  gap: 9px;
  border-radius: 7px;
  &:focus-within { outline: 2px solid var(--primary); outline-offset: 4px; }
  &:hover strong { color: var(--primary); }
  select {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    opacity: 0;
    cursor: pointer;
  }
}
.stock-label {
  min-width: 0;
  display: grid;
  gap: 1px;
  strong { display: flex; align-items: center; gap: 5px; font-size: 17px; font-weight: 600; }
  svg, small { color: var(--muted); }
  small { font-size: 12px; font-variant-numeric: tabular-nums; }
}
.remove {
  display: inline-grid;
  place-items: center;
  flex-shrink: 0;
  width: 29px;
  height: 29px;
  padding: 0;
  border-radius: 50%;
  color: var(--muted);
  &:hover { color: var(--text); background: var(--soft); }
}
.metrics {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin: 18px 0 6px;
  dt { color: var(--muted); font-size: 12px; }
  dd { font-size: clamp(22px, 2vw, 30px); font-weight: 550; font-variant-numeric: tabular-nums; line-height: 1.4; letter-spacing: -.035em; }
  div:last-child { text-align: right; }
  .price { font-size: 18px; }
  small { color: var(--muted); font-size: 11px; font-weight: 450; }
}
.card-state {
  display: grid;
  justify-items: center;
  align-content: center;
  gap: 9px;
  min-height: 230px;
  text-align: center;
  color: var(--muted);
  font-size: 13px;
  overflow-wrap: anywhere;
  &.no-bars { min-height: 180px; }
}
footer {
  display: flex;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 3px 10px;
  margin-top: 10px;
  color: var(--muted);
  font-size: 11px;
  .coverage { flex-basis: 100%; }
}
.spin { animation: compare-spin 1s linear infinite; }
@keyframes compare-spin { to { transform: rotate(360deg); } }
</style>
