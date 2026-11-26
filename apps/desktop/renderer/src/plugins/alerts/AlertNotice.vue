<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ArrowRight, BellRing, X } from 'lucide-vue-next'
import type { AlertEvent } from '../../../../shared/alerts'
import { useWorkbench } from '../../core/workbench'
import { useWorkspace } from '../market/store'
import { useAlertsStore } from './store'

const alerts = useAlertsStore()
const market = useWorkspace()
const { navigate } = useWorkbench()
const latest = ref<AlertEvent>()
const count = ref(0)
const name = computed(() => market.instruments.find(stock => stock.symbol === latest.value?.symbol)?.name || latest.value?.symbol)
const cursorKey = 'pantarhei.alerts.lastDisplayedId'
const savedCursor = () => {
  try {
    const value = localStorage.getItem(cursorKey)
    if (value !== null && /^\d+$/.test(value) && Number.isSafeInteger(Number(value))) return Number(value)
  } catch { /* The notice also works in memory when storage is unavailable. */ }
}
let cursor = savedCursor()
let timer: ReturnType<typeof setInterval> | undefined

const displayNewEvents = () => {
  const events = alerts.snapshot?.events
  if (!events || document.hidden) return
  const newest = events[0]?.id ?? 0
  if (cursor !== undefined && newest > cursor) {
    latest.value = events[0]
    const lastId = cursor
    count.value += events.filter(event => event.id > lastId).length
  }
  if (cursor !== newest) {
    cursor = newest
    try { localStorage.setItem(cursorKey, String(newest)) } catch { /* Keep the cursor for this window. */ }
  }
}
watch(() => alerts.snapshot, displayNewEvents)
const read = () => { void alerts.getAlerts().catch(() => {}) }
const onVisibility = () => {
  clearInterval(timer)
  if (document.hidden) return
  displayNewEvents()
  read()
  timer = setInterval(read, 10_000)
}
const dismiss = () => { count.value = 0 }
const openHistory = () => {
  alerts.historyRequested = true
  navigate('alerts')
  dismiss()
}
onMounted(() => {
  document.addEventListener('visibilitychange', onVisibility)
  onVisibility()
})
onBeforeUnmount(() => {
  clearInterval(timer)
  document.removeEventListener('visibilitychange', onVisibility)
})
</script>

<template>
  <aside v-if="count && latest" class="alert-notice" aria-label="价格提醒">
    <BellRing :size="18" aria-hidden="true" />
    <span role="status">
      <strong>{{ count > 1 ? `${count} 条价格提醒已触发` : '价格提醒已触发' }}</strong>
      {{ name }} 报 {{ latest.price.toFixed(2) }} 元
    </span>
    <button type="button" class="view" @click="openHistory">查看记录 <ArrowRight :size="14" /></button>
    <button type="button" class="dismiss" aria-label="关闭价格提醒提示" @click="dismiss"><X :size="16" /></button>
  </aside>
</template>

<style scoped lang="scss">
.alert-notice {
  display: flex; align-items: center; gap: 12px; padding: 12px 16px; margin: 0 0 20px;
  border: 1px solid #dce6ff; border-radius: 12px; background: #f4f7ff; color: var(--primary);
  font-size: 13px;
  > svg { flex-shrink: 0; }
  span { color: var(--text); }
  strong { margin-right: 8px; }
  button { flex-shrink: 0; display: inline-flex; align-items: center; gap: 5px; }
  .view { color: var(--primary); margin-left: auto; font-weight: 600; }
  .dismiss { color: var(--muted); padding: 4px; }
}
@media (max-width: 600px) {
  .alert-notice { gap: 7px; padding: 10px; }
  .alert-notice strong { display: block; }
}
</style>
