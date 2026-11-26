<script setup lang="ts">
import { computed } from 'vue'
import { exchangeName, number, volume } from '../format'
import { useWorkspace } from '../store'

const store = useWorkspace()
const last = computed(() => store.history?.bars.at(-1))
const previous = computed(() => store.history?.bars.at(-2))
const rangePosition = computed(() => {
  const bar = last.value
  if (!bar || bar.high <= bar.low) return null
  return 100 * (bar.close - bar.low) / (bar.high - bar.low)
})
</script>

<template>
  <section v-if="store.current" class="market-details" aria-label="交易概况">
    <h2>交易概况</h2>
    <div class="daily-range">
      <div class="range-heading"><span>日内区间</span><span>{{ store.current.currency }}</span></div>
      <div class="range-track" aria-hidden="true" :title="'收盘价 ' + number(last?.close)">
        <i v-if="rangePosition !== null" :style="{ left: rangePosition + '%' }"></i>
      </div>
      <div class="range-values"><span>{{ number(last?.low) }}</span><span>{{ number(last?.high) }}</span></div>
    </div>
    <dl>
      <div><dt>开盘价</dt><dd>{{ number(last?.open) }}</dd></div>
      <div><dt>前收盘价</dt><dd>{{ number(previous?.close) }}</dd></div>
      <div><dt>成交量</dt><dd>{{ volume(last?.volume) }}</dd></div>
      <div><dt>交易所</dt><dd>{{ exchangeName(store.current.exchange) }}</dd></div>
      <div><dt>行情来源</dt><dd>{{ store.history?.source ?? '—' }}<span v-if="store.history"> · {{ store.history.adjustment }}</span></dd></div>
    </dl>
  </section>
</template>

<style scoped lang="scss">
.market-details {
  border: 1px solid var(--line); border-radius: 20px; padding: 20px 22px; background: var(--surface);
  h2 { font-size: 18px; }
}
.daily-range { padding: 17px 0 15px; border-bottom: 1px solid var(--line-soft); }
.range-heading, .range-values, dl > div { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; }
.range-heading { color: var(--muted); font-size: 13px; }
.range-heading > :last-child { font-size: 11px; }
.range-track {
  position: relative; height: 5px; margin: 13px 5px 8px; border-radius: 5px; background: #dce6ff;
  i { position: absolute; top: 50%; transform: translate(-50%, -50%); width: 9px; height: 9px; border-radius: 100%; background: var(--primary); }
}
.range-values, dd { color: var(--text); font-size: 13px; font-weight: 550; font-variant-numeric: tabular-nums; }
dl { padding-top: 10px; }
dl > div { padding-top: 7px; }
dt { color: var(--muted); font-size: 13px; }
dd { text-align: right; }
dd span { font-weight: 400; color: var(--muted); }
</style>
