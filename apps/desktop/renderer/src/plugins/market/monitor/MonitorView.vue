<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { Activity, ArrowUpRight, CircleAlert, Pause, Play, Plus, RefreshCw } from 'lucide-vue-next'
import { usePageWindowState } from '../../../core/page-window'
import { useWindowUpdates } from '../../../core/window-updates'
import { errorText, getMarketApi, type MonitorSnapshot } from '../api'
import StockAvatar from '../components/StockAvatar.vue'
import { direction, exchangeTag, number, percent, signed } from '../format'
import { useMarketNavigation } from '../navigation'
import { useWorkspace } from '../store'
import { createMonitorPolling } from './polling'

const market = getMarketApi()
const store = useWorkspace()
const { openStock, search } = useMarketNavigation()
const paused = ref(false)
const initial = usePageWindowState(() => ({ paused: paused.value ? '1' : '0' }))
paused.value = initial.paused === '1'
const visible = ref(!document.hidden)
const updating = ref(false)
const error = ref('')
const snapshot = shallowRef<MonitorSnapshot>({ quotes: [], failed: [], checkedAt: null })
const membership = computed(() => store.watchlist.join(','))
let mounted = false

const stamp = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai', hourCycle: 'h23', year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', second: '2-digit',
})
const shanghaiTime = (value: string | null | undefined) => {
  const time = Date.parse(value ?? '')
  return Number.isFinite(time) ? stamp.format(time) : '—'
}
const rows = computed(() => {
  const quotes = new Map(snapshot.value.quotes.map(quote => [quote.symbol, quote]))
  const failed = new Set(snapshot.value.failed)
  return store.favorites.map(stock => {
    const quote = quotes.get(stock.symbol)
    const previous = quote?.previousClose
    const change = quote && previous != null && previous > 0 ? quote.price - previous : null
    const move = change != null && previous ? change / previous * 100 : null
    return { stock, quote, change, move, failed: failed.has(stock.symbol) }
  })
})
const covered = computed(() => rows.value.filter(row => row.quote).length)
const failures = computed(() => rows.value.filter(row => row.failed).length)

const load = async (online: boolean) => {
  const requested = membership.value
  updating.value = true
  try {
    const result = online ? await market.refreshMonitor() : await market.getMonitor()
    if (mounted && requested === membership.value) {
      snapshot.value = result
      error.value = ''
    }
    if (online && mounted) publish('quotes')
  } catch (reason) {
    if (mounted && requested === membership.value) {
      error.value = errorText(reason, online ? '本次报价更新失败，请稍后重试。' : '本地报价读取失败，请稍后重试。')
    }
  } finally {
    if (mounted) updating.value = false
  }
}
const polling = createMonitorPolling({
  visible: () => mounted && visible.value && !!membership.value,
  automatic: () => !paused.value,
  read: () => load(false),
  refresh: () => load(true),
})
const publish = useWindowUpdates('market-monitor', async key => {
  if (key === 'quotes' && visible.value) await polling.readCached()
})
const updateVisibility = () => { visible.value = !document.hidden }
watch([visible, paused, membership], () => {
  error.value = ''
  if (mounted) void polling.sync()
})
onMounted(() => {
  mounted = true
  document.addEventListener('visibilitychange', updateVisibility)
  void polling.sync()
})
onBeforeUnmount(() => {
  mounted = false
  polling.stop()
  document.removeEventListener('visibilitychange', updateVisibility)
})
</script>

<template>
  <section class="monitor" aria-labelledby="monitor-heading">
    <header class="heading">
      <div><h1 id="monitor-heading">行情监控</h1><p>自选股报价 · 腾讯行情 · 上海时间</p></div>
      <div class="buttons">
        <button class="action" @click="search(true)"><Plus :size="16" />管理自选</button>
        <button class="action primary" aria-label="立即刷新" :disabled="updating || !rows.length" @click="polling.refreshNow">
          <RefreshCw :size="15" :class="{ spin: updating }" />{{ updating ? '更新中' : '立即刷新' }}
        </button>
      </div>
    </header>

    <template v-if="rows.length">
      <div class="summary">
        <div class="coverage"><strong>报价覆盖 {{ covered }} / {{ rows.length }}</strong>
          <span v-if="snapshot.checkedAt">最近检查 {{ shanghaiTime(snapshot.checkedAt) }}</span></div>
        <button class="auto" :aria-label="paused ? '恢复自动刷新' : '暂停自动刷新'" :title="paused ? '恢复自动刷新' : '暂停自动刷新'"
          @click="paused = !paused">
          <i :class="{ live: !paused }"></i>{{ paused ? '已暂停自动刷新' : '自动刷新 · 30 秒' }}<component :is="paused ? Play : Pause" :size="14" />
        </button>
      </div>
      <p v-if="error || failures" class="warning" role="status"><CircleAlert :size="16" />
        {{ error || (failures + ' 只股票本次更新失败。已有报价按原时间保留。') }}</p>
      <table class="quotes">
        <thead><tr><th>股票</th><th>现价（元）</th><th class="delta">涨跌额（元）</th><th>涨跌幅</th><th class="time">报价时间</th></tr></thead>
        <tbody>
          <tr v-for="row in rows" :key="row.stock.symbol">
            <td><button class="stock" :aria-label="'查看' + row.stock.name + '行情'" @click="openStock(row.stock.symbol)">
              <StockAvatar :name="row.stock.name" :symbol="row.stock.symbol" :sector="row.stock.sector" :size="34" />
              <span><strong>{{ row.stock.name }}</strong><small>{{ exchangeTag(row.stock.exchange) }} · {{ row.stock.symbol }}</small>
                <small class="compact-time">{{ row.quote ? shanghaiTime(row.quote.quotedAt) : '暂无报价' }}<template v-if="row.failed"> · 更新失败</template></small></span>
              <ArrowUpRight class="arrow" :size="13" /></button></td>
            <td>{{ number(row.quote?.price) }}</td>
            <td class="delta" :class="direction(row.change)">{{ signed(row.change) }}</td>
            <td :class="direction(row.move)">{{ percent(row.move) }}</td>
            <td class="time"><time v-if="row.quote" :datetime="row.quote.quotedAt">{{ shanghaiTime(row.quote.quotedAt) }}</time>
              <span v-else>暂无报价</span><small v-if="row.failed">更新失败</small></td>
          </tr>
        </tbody>
      </table>
    </template>
    <div v-else class="empty no-stocks"><Activity :size="26" /><strong>暂无自选股</strong><span>点击「管理自选」添加要监控的股票。</span></div>
  </section>
</template>

<style scoped lang="scss">
.monitor { min-width: 0; }
.heading, .buttons, .summary, .coverage, .auto, .stock, .warning { display: flex; align-items: center; }
.heading, .summary { justify-content: space-between; flex-wrap: wrap; gap: 12px; }
.heading {
  margin-bottom: 30px;
  h1 { font-size: clamp(30px, 3vw, 44px); font-weight: 550; letter-spacing: -.05em; }
  p { margin-top: 3px; color: var(--muted); font-size: 14px; }
}
.buttons { gap: 8px; }
.summary { padding: 15px 0; border-top: 1px solid var(--line-soft); }
.coverage { flex-wrap: wrap; gap: 4px 15px; font-size: 14px; strong { font-weight: 550; } span { color: var(--muted); font-size: 12px; } }
.auto { gap: 8px; padding: 6px 10px; border-radius: 100px; color: var(--muted); font-size: 12px;
  background: var(--soft); i { width: 6px; height: 6px; border-radius: 50%; background: var(--dim); }
  i.live { background: #15825b; } &:hover { color: var(--text); }
}
.warning { gap: 7px; align-items: baseline; margin: 0 0 12px; padding: 9px 12px; border-radius: 9px;
  background: var(--soft); color: var(--muted); font-size: 13px; svg { align-self: center; } }
.quotes {
  width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums;
  th, td { text-align: right; padding: 14px 9px; }
  th { color: var(--muted); font-size: 12px; font-weight: 500; border-block: 1px solid var(--line-soft); }
  td { font-size: 16px; border-bottom: 1px solid var(--line-soft); }
  th:first-child, td:first-child { text-align: left; padding-left: 0; } th:last-child, td:last-child { padding-right: 0; }
  td.time { font-size: 13px; color: var(--muted); small { display: block; font-size: 11px; } }
}
.stock { gap: 10px; text-align: left; padding: 0; strong, small { display: block; }
  strong { font-size: 16px; font-weight: 550; } small { font-size: 12px; color: var(--muted); }
  .compact-time { display: none; } .arrow { color: var(--muted); opacity: 0; }
  &:hover strong, &:focus-visible strong { color: var(--primary); }
  &:hover .arrow, &:focus-visible .arrow { opacity: 1; }
}
.no-stocks { min-height: 260px; border-top: 1px solid var(--line-soft); span { font-size: 13px; } }
.spin { animation: rotate 1s linear infinite; }
@keyframes rotate { to { transform: rotate(360deg); } }
@media (max-width: 680px) {
  .heading { margin-bottom: 18px; align-items: flex-start; }
  .summary { align-items: flex-start; }
  .coverage { display: grid; }
  .quotes { .time, .delta { display: none; }
    th, td { padding-inline: 2px; } td { font-size: 15px; }
    th:nth-child(4), td:nth-child(4) { padding-right: 0; } }
  .stock { gap: 7px; .compact-time { display: block; font-size: 10px; } .arrow { display: none; } }
}
</style>
