<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  AreaSeries, CandlestickSeries, ColorType, createChart, createSeriesMarkers, CrosshairMode, HistogramSeries,
  LineSeries, LineStyle, type AutoscaleInfoProvider, type IChartApi, type ISeriesApi, type ISeriesMarkersPluginApi, type Time,
} from 'lightweight-charts'
import { ChartCandlestick, ChartNoAxesCombined, Maximize2, Minimize2 } from 'lucide-vue-next'
import type { Bar } from '../api'
import type { XOrderMark } from '../../../../../shared/xmonitor'
import { chartRanges } from '../chart-settings'
import { direction, number, volume } from '../format'
import { groupOrderMarks, orderPriceMarkers, orderSeriesMarkers } from '../order-marker-series'
import OrderMarkDetails from './OrderMarkDetails.vue'

const props = defineProps<{ bars: Bar[]; symbol: string; adjustment?: string; orderMarks?: XOrderMark[]; orderMarksEnabled?: boolean }>()
const range = defineModel<number>('range', { required: true })
const mode = defineModel<'candle' | 'line'>('mode', { required: true })
const showMA5 = defineModel<boolean>('ma5', { required: true })
const showMA20 = defineModel<boolean>('ma20', { required: true })
const showVolume = defineModel<boolean>('volume', { required: true })
const expanded = ref(false)
const canvas = ref<HTMLDivElement>()
const hoverTime = ref('')
const cursor = computed(() => props.bars.find(bar => bar.time === hoverTime.value) ?? props.bars.at(-1))
const fastColor = '#c68b29'
const slowColor = '#587cdb'
let chart: IChartApi | undefined
let candle: ISeriesApi<'Candlestick'> | undefined
let orderLayer: ISeriesMarkersPluginApi<Time> | undefined
let closing: ISeriesApi<'Area'> | undefined
let fast: ISeriesApi<'Line'> | undefined
let slow: ISeriesApi<'Line'> | undefined
let histogram: ISeriesApi<'Histogram'> | undefined
let observer: ResizeObserver | undefined

const average = (bars: Bar[], period: number) => {
  let sum = 0
  const result: { time: string; value: number }[] = []
  bars.forEach((bar, index) => {
    sum += bar.close
    if (index >= period) sum -= bars[index - period].close
    if (index >= period - 1) result.push({ time: bar.time, value: sum / period })
  })
  return result
}

const ma5 = computed(() => average(props.bars, 5))
const ma20 = computed(() => average(props.bars, 20))

const markDay = ref('')
const showMarks = computed(() => props.orderMarksEnabled && mode.value === 'candle')
const orderDays = computed(() => showMarks.value && props.orderMarks?.length ? groupOrderMarks(props.orderMarks, props.bars) : [])
const priceMarks = computed(() => {
  if (!markDay.value || !candle) return []
  const { upColor, downColor } = candle.options()
  const day = orderDays.value.find(day => day.date === markDay.value)
  return orderPriceMarkers(day, props.adjustment, upColor, downColor)
})
const missingDaysCount = computed(() => (props.orderMarks?.length ?? 0) - orderDays.value.reduce((sum, day) => sum + day.orders.length, 0))

const scaleWithOrderPrices: AutoscaleInfoProvider = original => {
  const info = original()
  const range = chart?.timeScale().getVisibleRange()
  if (!info?.priceRange || !range || markDay.value < dateLabel(range.from) || markDay.value > dateLabel(range.to)) return info
  const prices = { ...info.priceRange }
  for (const { price } of priceMarks.value) {
    prices.minValue = Math.min(prices.minValue, price)
    prices.maxValue = Math.max(prices.maxValue, price)
  }
  return { ...info, priceRange: prices }
}

const setOrderMarks = () => {
  if (!orderDays.value.some(day => day.date === markDay.value)) markDay.value = ''
  if (!candle) return
  const autoscaleInfoProvider = priceMarks.value.length ? scaleWithOrderPrices : null
  if ((candle.options().autoscaleInfoProvider ?? null) !== autoscaleInfoProvider) candle.applyOptions({ autoscaleInfoProvider })
  if (!orderDays.value.length) {
    orderLayer?.detach()
    orderLayer = undefined
    return
  }
  const { upColor, downColor } = candle.options()
  const markers = orderSeriesMarkers(orderDays.value, upColor, downColor)
  if (priceMarks.value.length) {
    markers.push(...priceMarks.value)
    markers.sort((a, b) => a.time.localeCompare(b.time))
  }
  if (orderLayer) orderLayer.setMarkers(markers)
  else orderLayer = createSeriesMarkers(candle, markers)
}

const selectMarkDay = (date: string) => {
  markDay.value = date
  if (!date || !chart) return
  const scale = chart.timeScale()
  const range = scale.getVisibleLogicalRange()
  const index = props.bars.findIndex(bar => bar.time === date)
  if (!range || index < 0 || (index >= range.from && index <= range.to)) return
  const half = (range.to - range.from) / 2
  scale.setVisibleLogicalRange({ from: index - half, to: index + half })
}

const fitRange = () => {
  const count = Math.min(props.bars.length, range.value)
  if (chart && count) chart.timeScale().setVisibleLogicalRange({
    from: props.bars.length - count - 0.5, to: props.bars.length + 1,
  })
}

const setVolume = () => {
  if (!chart) return
  if (!showVolume.value) {
    if (histogram) chart.removeSeries(histogram)
    histogram = undefined
    return
  }
  if (!histogram) {
    histogram = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' }, lastValueVisible: false, priceLineVisible: false,
    }, 1)
    chart.panes()[1].setStretchFactor(0.23)
  }
  histogram.setData(props.bars.map(bar => ({
    time: bar.time, value: bar.volume, color: bar.close >= bar.open ? '#e9b5b8' : '#acd5c4',
  })))
}

const draw = () => {
  if (!chart) return
  hoverTime.value = ''
  candle?.setData(props.bars)
  closing?.setData(props.bars.map(bar => ({ time: bar.time, value: bar.close })))
  fast?.setData(ma5.value)
  slow?.setData(ma20.value)
  setVolume()
  fitRange()
}

const dateLabel = (time: Time) => {
  if (typeof time === 'number') return new Date(time * 1000).toISOString().slice(0, 10)
  if (typeof time === 'string') return time
  return [time.year, String(time.month).padStart(2, '0'), String(time.day).padStart(2, '0')].join('-')
}

const onKey = (event: KeyboardEvent) => {
  if (event.key === 'Escape') expanded.value = false
}

onMounted(() => {
  if (!canvas.value) return
  const colors = getComputedStyle(canvas.value)
  const upColor = colors.getPropertyValue('--up').trim() || '#c73240'
  const downColor = colors.getPropertyValue('--down').trim() || '#087f58'
  chart = createChart(canvas.value, {
    width: canvas.value.clientWidth, height: canvas.value.clientHeight,
    layout: {
      background: { type: ColorType.Solid, color: '#fff' }, textColor: '#69717d',
      fontFamily: 'Inter, "Segoe UI", "Microsoft YaHei", sans-serif', fontSize: 11,
      panes: { separatorColor: '#eef0f3', separatorHoverColor: '#cbd3df', enableResize: true },
    },
    grid: { vertLines: { visible: false }, horzLines: { color: '#eef0f3' } },
    rightPriceScale: { borderVisible: false, scaleMargins: { top: 0.11, bottom: 0.08 }, minimumWidth: 65 },
    timeScale: { borderColor: '#eef0f3', fixLeftEdge: true, rightOffset: 1, minBarSpacing: 0.4, allowBoldLabels: false, lockVisibleTimeRangeOnResize: true },
    crosshair: { mode: CrosshairMode.Normal, vertLine: { color: '#9aa5b4', labelBackgroundColor: '#414b5a', width: 1 },
      horzLine: { color: '#9aa5b4', labelBackgroundColor: '#414b5a', width: 1 } },
    localization: { locale: 'zh-CN', dateFormat: 'yyyy-MM-dd' },
  })
  candle = chart.addSeries(CandlestickSeries, { upColor, downColor, borderVisible: false,
    wickUpColor: upColor, wickDownColor: downColor, priceLineStyle: LineStyle.Dotted,
    priceLineWidth: 1, visible: mode.value === 'candle' })
  closing = chart.addSeries(AreaSeries, {
    lineColor: '#0052ff', topColor: 'rgba(0,82,255,.15)', bottomColor: 'rgba(0,82,255,0)',
    lineWidth: 2, priceLineVisible: false, visible: mode.value === 'line',
  })
  const indicatorOptions = { lineWidth: 1 as const, lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false }
  fast = chart.addSeries(LineSeries, { ...indicatorOptions, color: fastColor, visible: showMA5.value })
  slow = chart.addSeries(LineSeries, { ...indicatorOptions, color: slowColor, visible: showMA20.value })
  chart.subscribeCrosshairMove(event => { hoverTime.value = event.time ? dateLabel(event.time) : '' })
  chart.subscribeClick(event => {
    if (!orderDays.value.length || !event.time || (event.paneIndex ?? 0) !== 0) return
    const date = dateLabel(event.time)
    markDay.value = orderDays.value.some(day => day.date === date) ? date : ''
  })
  observer = new ResizeObserver(() => {
    if (canvas.value) chart?.resize(canvas.value.clientWidth, canvas.value.clientHeight)
  })
  observer.observe(canvas.value)
  window.addEventListener('keydown', onKey)
  draw()
  setOrderMarks()
})
watch(() => props.bars, draw)
watch([orderDays, priceMarks], setOrderMarks)
watch(() => props.symbol, () => { markDay.value = '' })
watch(range, fitRange)
watch(mode, value => {
  candle?.applyOptions({ visible: value === 'candle' })
  closing?.applyOptions({ visible: value === 'line' })
})
watch(showMA5, visible => fast?.applyOptions({ visible }))
watch(showMA20, visible => slow?.applyOptions({ visible }))
watch(showVolume, setVolume)
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
  observer?.disconnect()
  orderLayer?.detach()
  chart?.remove()
})
</script>

<template>
  <section class="price-chart" :class="{ expanded }" aria-label="历史行情图表">
    <header class="chart-heading">
      <h2>价格走势</h2>
      <div class="chart-mode" role="group" aria-label="图表类型">
        <button title="日 K 线" aria-label="日 K 线" :aria-pressed="mode === 'candle'" @click="mode = 'candle'"><ChartCandlestick :size="15" />日 K</button>
        <button title="收盘价折线" aria-label="收盘价折线" :aria-pressed="mode === 'line'" @click="mode = 'line'"><ChartNoAxesCombined :size="15" />折线</button>
      </div>
      <div class="ranges" role="group" aria-label="图表可见区间">
        <button v-for="r in chartRanges" :key="r.label" :aria-pressed="r.count === range" @click="range = r.count">{{ r.label }}</button>
      </div>
      <button class="icon-button expand" :aria-label="expanded ? '收起图表' : '放大图表'" :title="expanded ? '收起图表' : '放大图表'" @click="expanded = !expanded">
        <component :is="expanded ? Minimize2 : Maximize2" :size="15" />
      </button>
    </header>
    <div class="ohlc" v-if="cursor">
      <span class="ohlc-date">{{ cursor.time }}</span>
      <span>开 <b>{{ number(cursor.open) }}</b></span><span>高 <b>{{ number(cursor.high) }}</b></span>
      <span>低 <b>{{ number(cursor.low) }}</b></span><span>收 <b :class="direction(cursor.close - cursor.open)">{{ number(cursor.close) }}</b></span>
    </div>
    <div ref="canvas" class="chart-canvas" role="img" title="TradingView Lightweight Charts™ · Copyright © 2025 TradingView, Inc." :aria-label="symbol + ' 历史日线图，详细价格见下方历史行情表'"></div>
    <footer class="chart-controls" aria-label="技术指标">
      <button class="indicator-toggle" :aria-pressed="showMA5" @click="showMA5 = !showMA5"><i class="swatch" :style="{ backgroundColor: fastColor }"></i>MA5</button>
      <button class="indicator-toggle" :aria-pressed="showMA20" @click="showMA20 = !showMA20"><i class="swatch" :style="{ backgroundColor: slowColor }"></i>MA20</button>
      <button class="indicator-toggle" :aria-pressed="showVolume" @click="showVolume = !showVolume"><i class="swatch vol"></i>成交量</button>
      <slot name="order-controls" />
      <span v-if="showVolume && cursor" class="cursor-volume mono">{{ volume(cursor.volume) }}</span>
    </footer>
    <OrderMarkDetails v-if="orderDays.length" :days="orderDays" :selected="markDay" :adjustment="adjustment" :show-prices="priceMarks.length > 0" @select="selectMarkDay" />
    <p v-if="showMarks && missingDaysCount > 0" class="missing-marks">{{ orderDays.length ? missingDaysCount + ' 条委托的发帖日期暂无日 K' : '这些发帖日期暂无日 K' }}</p>
  </section>
</template>

<style scoped lang="scss">
.price-chart {
  min-width: 0;
  container-type: inline-size;
  background: var(--surface, #fff);
}

.chart-heading {
  display: flex;
  align-items: center;
  gap: 14px;
  min-height: 42px;

  h2 {
    margin: 0;
    color: var(--text);
    font-size: 18px;
    font-weight: 600;
    letter-spacing: -.025em;
  }
}

.chart-mode, .ranges {
  display: flex;
  align-items: center;

  button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 5px;
    border: 0;
    border-radius: 100px;
    font-size: 12px;
    line-height: 1;
    white-space: nowrap;
    color: var(--muted);
  }
}

.chart-mode {
  gap: 2px;
  padding: 3px;
  border-radius: 100px;
  background: var(--soft, #f4f5f7);

  button {
    padding: 6px 10px;
    background: transparent;

    &[aria-pressed='true'] {
      color: var(--text);
      background: #fff;
      box-shadow: inset 0 0 0 1px var(--line);
    }
  }
}

.ranges {
  gap: 3px;
  margin-left: auto;

  button {
    min-width: 35px;
    height: 29px;
    padding: 0 8px;
    background: transparent;

    &:hover { background: var(--soft); }

    &[aria-pressed='true'] {
      color: var(--primary);
      background: var(--primary-soft);
      font-weight: 600;
    }
  }
}

.expand {
  display: inline-flex;
  width: 30px;
  height: 30px;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  color: var(--muted);
  background: var(--soft);

  &:hover { color: var(--text); }
}

.ohlc {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 5px 14px;
  margin: 9px 0 7px;
  color: var(--muted);
  font-size: 12px;
  font-variant-numeric: tabular-nums;

  b {
    margin-left: 2px;
    color: var(--text);
    font-weight: 500;
  }
}

.ohlc-date {
  padding-right: 12px;
  border-right: 1px solid var(--line);
}

.chart-canvas {
  position: relative;
  width: 100%;
  height: clamp(300px, 35vh, 430px);
}

.chart-controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 14px;
  margin-top: 7px;
  min-height: 33px;
}

.indicator-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 0;
  color: var(--muted);
  background: none;
  font-size: 12px;
  font-weight: 500;

  &:hover { color: var(--text); }
  &[aria-pressed='false'] .swatch { background: var(--line) !important; }
  &[aria-pressed='false'] { text-decoration: line-through; }
}

.swatch {
  display: inline-block;
  width: 13px;
  height: 3px;
  border-radius: 3px;

  &.vol {
    height: 7px;
    width: 9px;
    border-radius: 2px;
    background: #8ca99c;
  }
}

.cursor-volume {
  margin-left: auto;
  color: var(--muted);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.missing-marks { margin: 6px 0; color: var(--muted); font-size: 12px; }

.price-chart.expanded {
  position: fixed;
  inset: 0;
  z-index: 20;
  display: flex;
  flex-direction: column;
  padding: clamp(14px, 3vw, 44px);
  background: #fff;

  .chart-canvas {
    flex: 1;
    min-height: 0;
  }
}

@container (max-width: 550px) {
  .chart-heading {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto auto;
    gap: 7px 9px;

    h2 { font-size: 17px; }
  }

  .ranges {
    grid-column: 1 / -1;
    grid-row: 2;
    justify-content: flex-start;
    margin: 0;
  }

  .expand { grid-column: 3; grid-row: 1; }

  .ohlc {
    margin: 5px 0;
    gap: 3px 8px;
    font-size: 11px;
  }

  .ohlc-date { padding-right: 7px; }
  .chart-canvas { height: 260px; }
  .chart-controls { gap: 4px 10px; }
  .cursor-volume { font-size: 11px; }
}
</style>
