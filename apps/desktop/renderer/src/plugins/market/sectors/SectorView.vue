<script setup lang="ts">
import { computed, ref } from 'vue'
import { ArrowUpRight, CalendarDays, ChevronDown, Layers3 } from 'lucide-vue-next'
import { usePageWindowState } from '../../../core/page-window'
import { direction, exchangeTag, number, percent } from '../format'
import { useMarketNavigation } from '../navigation'
import { useWorkspace } from '../store'
import { sectorDates, sectorMetrics } from './metrics'
import SectorMap from './SectorMap.vue'

const store = useWorkspace()
const { openStock } = useMarketNavigation()
const scope = ref<'all' | 'watchlist'>('all')
const chosenDate = ref('')
const chosenSector = ref('')

const stocks = computed(() => {
  if (scope.value === 'all') return store.instruments
  const favorites = new Set(store.watchlist)
  return store.instruments.filter(item => favorites.has(item.symbol))
})
const dates = computed(() => sectorDates(stocks.value))
const date = computed(() => dates.value.includes(chosenDate.value) ? chosenDate.value : dates.value[0] ?? '')
const groups = computed(() => sectorMetrics(stocks.value, date.value))
const active = computed(() => groups.value.find(item => item.id === chosenSector.value) ?? groups.value[0])
const sampleCount = computed(() => groups.value.reduce((sum, group) => sum + group.count, 0))
const choose = (sector: string) => { chosenSector.value = sector }
const initial = usePageWindowState(
  () => ({ scope: scope.value, date: date.value, sector: active.value?.id ?? '' }),
  () => active.value ? `板块 · ${active.value.id}` : '板块热力图',
)
scope.value = initial.scope === 'watchlist' ? 'watchlist' : 'all'
chosenDate.value = initial.date ?? ''
chosenSector.value = initial.sector ?? ''
</script>

<template>
  <section class="sectors" aria-labelledby="sector-title">
    <header class="heading">
      <div><h1 id="sector-title">板块热力图</h1><p>按行业查看本地股票的收盘表现</p></div>
      <div class="filters">
        <div class="scope" role="group" aria-label="股票范围">
          <button :aria-pressed="scope === 'all'" @click="scope = 'all'">本地股票</button>
          <button :aria-pressed="scope === 'watchlist'" @click="scope = 'watchlist'">我的自选</button>
        </div>
        <label class="date-picker">
          <CalendarDays :size="15" /><select aria-label="报价日期" :disabled="!dates.length" :value="date"
            @change="chosenDate = ($event.target as HTMLSelectElement).value">
            <option v-if="!dates.length" value="">暂无报价</option>
            <option v-for="day in dates" :key="day" :value="day">{{ day }}</option>
          </select><ChevronDown :size="14" />
        </label>
      </div>
    </header>

    <div v-if="active" class="overview">
      <section class="distribution" aria-label="板块分布">
        <div class="map-header">
          <span>{{ groups.length }} 个板块 <i>·</i> 当日 {{ sampleCount }} / {{ stocks.length }} 只股票</span>
          <div class="legend" aria-label="颜色表示板块平均涨跌幅，达到正负百分之三后色深保持不变">
            <span>≤−3%</span><b></b><span>≥+3%</span>
          </div>
        </div>
        <SectorMap :groups="groups" :selected="active.id" @select="choose" />
        <p class="method">面积按当日报价股票数分配，颜色表示有效涨跌幅的等权平均，红涨绿跌，灰色平盘，斜纹表示暂无涨跌幅。日期取自股票的最新本地报价。</p>
      </section>

      <section class="detail" aria-label="板块成分股">
        <header class="detail-header">
          <label class="sector-picker">
            <select aria-label="查看板块" :value="active.id" @change="choose(($event.target as HTMLSelectElement).value)">
              <option v-for="group in groups" :key="group.id" :value="group.id">{{ group.id }}</option>
            </select><ChevronDown :size="15" />
          </label>
          <span class="count">{{ active.count }} 只成分股</span>
        </header>
        <div class="metric"><span>板块平均涨跌幅</span><strong :class="direction(active.changePercent)">{{ percent(active.changePercent) }}</strong></div>
        <div class="breadth"><span>上涨 {{ active.up }}</span><span>下跌 {{ active.down }}</span><span>平盘 {{ active.flat }}</span><span v-if="active.unknown">暂无 {{ active.unknown }}</span></div>
        <div class="member-head"><span>股票</span><span>收盘价 / 涨跌幅</span></div>
        <ul class="members">
          <li v-for="stock in active.members" :key="stock.symbol">
            <button :aria-label="'查看' + stock.name + '行情'" @click="openStock(stock.symbol)">
              <span class="member-name"><strong>{{ stock.name }}</strong><small>{{ exchangeTag(stock.exchange) }} · {{ stock.symbol }}</small></span>
              <span class="member-price"><strong>{{ number(stock.close) }}</strong><small :class="direction(stock.changePercent)">{{ percent(stock.changePercent) }}</small></span>
              <ArrowUpRight :size="14" aria-hidden="true" />
            </button>
          </li>
        </ul>
      </section>
    </div>
    <div v-else class="empty no-sectors" role="status">
      <Layers3 :size="26" /><strong>{{ scope === 'watchlist' && !stocks.length ? '暂无自选股' : '暂无可用的本地报价' }}</strong>
      <button v-if="scope === 'watchlist'" class="action" @click="scope = 'all'">查看本地股票</button>
    </div>
  </section>
</template>

<style scoped lang="scss">
.sectors { min-width: 0; }
.heading, .filters, .map-header, .legend, .detail-header, .breadth, .member-head { display: flex; align-items: center; }
.heading {
  justify-content: space-between; flex-wrap: wrap; gap: 16px 24px; margin-bottom: 30px;
  h1 { font-size: clamp(30px, 3vw, 44px); letter-spacing: -.05em; font-weight: 550; }
  p { margin-top: 3px; font-size: 14px; color: var(--muted); }
}
.filters { gap: 12px; flex-wrap: wrap; }
.scope {
  display: flex; padding: 3px; background: var(--soft); border-radius: 100px;
  button { padding: 7px 13px; border-radius: 100px; color: var(--muted); font-size: 13px; white-space: nowrap; }
  button[aria-pressed='true'] { color: var(--primary); background: #fff; box-shadow: 0 1px 4px #1f304119; font-weight: 600; }
}
.date-picker, .sector-picker {
  display: inline-flex; align-items: center; gap: 7px;
  select { appearance: none; cursor: pointer; color: inherit; border: 0; background: transparent; font: inherit; padding: 4px 21px 4px 0; }
  select:focus-visible { outline: 2px solid var(--primary); outline-offset: 1px; border-radius: 3px; }
  svg:last-child { pointer-events: none; margin-left: -24px; }
}
.date-picker { color: var(--muted); font-size: 13px; font-variant-numeric: tabular-nums; }
.overview { display: grid; grid-template-columns: minmax(0, 1fr) minmax(255px, 27%); gap: clamp(23px, 3.1vw, 48px); }
.distribution, .detail { min-width: 0; }
.map-header { justify-content: space-between; gap: 16px; flex-wrap: wrap; min-height: 33px; margin: 0 2px 10px; color: var(--muted); font-size: 13px; i { font-style: normal; margin: 0 4px; } }
.legend { gap: 6px; font-size: 11px; b { width: 69px; height: 6px; border-radius: 8px; background: linear-gradient(90deg,hsl(158 44% 61%),#e7eaed,hsl(4 76% 69%)); } }
.method { margin: 14px 2px 0; color: var(--muted); font-size: 12px; line-height: 1.7; }
.detail { align-self: start; padding-left: clamp(16px, 2vw, 29px); border-left: 1px solid var(--line-soft); }
.detail-header { justify-content: space-between; flex-wrap: wrap; gap: 8px; }
.sector-picker { font-size: 22px; font-weight: 600; letter-spacing: -.04em; svg { color: var(--muted); } }
.count, .metric > span, .breadth, .member-head { font-size: 12px; color: var(--muted); }
.metric { margin-top: 20px; display: grid; gap: 1px; strong { font-size: clamp(29px, 2.7vw, 38px); font-weight: 550; letter-spacing: -.045em; } }
.breadth { gap: 9px; flex-wrap: wrap; margin-top: 4px; }
.member-head { justify-content: space-between; padding: 20px 17px 8px 0; border-bottom: 1px solid var(--line); }
.members {
  list-style: none; padding: 0; margin: 0;
  li + li { border-top: 1px solid var(--line-soft); }
  button { width: 100%; display: flex; align-items: center; gap: 5px; text-align: left; padding: 12px 1px; }
  svg { color: var(--dim); }
  button:hover .member-name strong, button:hover svg { color: var(--primary); }
  strong, small { display: block; }
  strong { font-size: 14px; font-weight: 550; }
  small { margin-top: 2px; font-size: 12px; color: var(--muted); }
}
.member-price { margin-left: auto; text-align: right; font-variant-numeric: tabular-nums; }
.no-sectors { min-height: 260px; border-top: 1px solid var(--line); }
@media (max-width: 900px) {
  .overview { grid-template-columns: minmax(0, 1fr); gap: 24px; }
  .detail { padding: 19px 0 0; border-left: 0; border-top: 1px solid var(--line); }
}
@media (max-width: 540px) {
  .heading { margin-bottom: 18px; }
  .filters { justify-content: space-between; gap: 6px; width: 100%; }
  .scope button { padding-inline: 10px; }
  .map-header { gap: 7px; font-size: 12px; margin-bottom: 7px; }
}
</style>
