<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { CandlestickSeries, ColorType, createChart, CrosshairMode, LineStyle, type IChartApi, type ISeriesApi } from 'lightweight-charts'
import type { Bar } from '../api'

const props = defineProps<{ points: (Bar | { time: string })[]; name: string; currency: string }>()
const host = ref<HTMLDivElement>()
let chart: IChartApi | undefined
let candles: ISeriesApi<'Candlestick'> | undefined
let observer: ResizeObserver | undefined

const draw = () => {
  if (!chart || !candles) return
  candles.setData(props.points)
  if (props.points.length) {
    chart.timeScale().setVisibleLogicalRange({ from: -0.5, to: props.points.length - 0.5 })
  }
}

onMounted(() => {
  if (!host.value) return
  const colors = getComputedStyle(host.value)
  const upColor = colors.getPropertyValue('--up').trim() || '#bc3042'
  const downColor = colors.getPropertyValue('--down').trim() || '#08794f'
  chart = createChart(host.value, {
    width: host.value.clientWidth, height: host.value.clientHeight,
    layout: {
      background: { type: ColorType.Solid, color: '#ffffff' }, textColor: '#69717d',
      fontFamily: 'Inter, "Segoe UI", "Microsoft YaHei", sans-serif', fontSize: 11,
    },
    grid: { vertLines: { visible: false }, horzLines: { color: '#eef0f3' } },
    rightPriceScale: { borderVisible: false, minimumWidth: 63, scaleMargins: { top: 0.10, bottom: 0.10 } },
    timeScale: { borderColor: '#eef0f3', minBarSpacing: 0.01, lockVisibleTimeRangeOnResize: true, allowBoldLabels: false },
    localization: { locale: 'zh-CN', dateFormat: 'yyyy-MM-dd' },
    handleScroll: false, handleScale: false,
    crosshair: { mode: CrosshairMode.Normal,
      vertLine: { color: '#a8b0bd', width: 1, labelBackgroundColor: '#414b5a' },
      horzLine: { color: '#a8b0bd', width: 1, labelBackgroundColor: '#414b5a' } },
  })
  candles = chart.addSeries(CandlestickSeries, {
    upColor, downColor, borderVisible: false, wickUpColor: upColor, wickDownColor: downColor,
    priceLineStyle: LineStyle.Dotted, lastValueVisible: false, priceLineVisible: false,
  })
  observer = new ResizeObserver(() => {
    if (host.value?.clientWidth && host.value.clientHeight) chart?.resize(host.value.clientWidth, host.value.clientHeight)
  })
  observer.observe(host.value)
  draw()
})
watch(() => props.points, draw)
onBeforeUnmount(() => { observer?.disconnect(); chart?.remove() })
</script>

<template>
  <div ref="host" class="compare-chart" role="img" :aria-label="name + ' 日 K 线，单位 ' + currency + '，' + points[0]?.time + ' 至 ' + points.at(-1)?.time"
    title="TradingView Lightweight Charts™ · Copyright © 2025 TradingView, Inc."></div>
</template>

<style scoped lang="scss">
.compare-chart { width: 100%; min-width: 0; height: clamp(185px, 22vh, 265px); position: relative; }
@media (max-width: 600px) { .compare-chart { height: 180px; } }
</style>
