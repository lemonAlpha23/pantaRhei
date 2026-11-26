import { computed, inject, onScopeDispose, ref, shallowRef, watch, type InjectionKey } from 'vue'
import type { XApi, XOrderMark } from '../../../../shared/xmonitor'
import { useWindowUpdates } from '../../core/window-updates'
import type { Bar } from './api'

export const orderMarkSourceKey: InjectionKey<XApi['getOrderMarks']> = Symbol('chart-order-marks')
const preferenceKey = 'pantarhei.chart.orderMarks'

export const useChartOrderMarks = (symbol: () => string, bars: () => Bar[] | undefined, candle: () => boolean) => {
  const source = inject(orderMarkSourceKey, null)
  const enabled = ref(false)
  const items = shallowRef<XOrderMark[]>([])
  const status = ref<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const query = computed(() => {
    if (!source || !enabled.value || !candle()) return null
    const history = bars()
    if (!history?.length) return null
    return { symbol: symbol(), start: history[0].time, end: history[history.length - 1].time }
  })
  let request = 0
  let timer: ReturnType<typeof setInterval> | undefined

  const restore = () => {
    try { enabled.value = localStorage.getItem(preferenceKey) === '1' } catch { /* Keep this window's choice. */ }
  }
  const setEnabled = (value: boolean) => {
    enabled.value = value
    try { localStorage.setItem(preferenceKey, value ? '1' : '0') } catch { /* Still usable for this session. */ }
  }
  const onStorage = (event: StorageEvent) => {
    if (event.key === preferenceKey || event.key === null) restore()
  }
  const refresh = async () => {
    const target = query.value
    if (!source || !target || document.hidden) return
    const current = ++request
    if (status.value !== 'ready') status.value = 'loading'
    try {
      const data = await source(target.symbol, target.start, target.end)
      if (current !== request) return
      items.value = data.items
      status.value = 'ready'
    } catch {
      if (current !== request) return
      items.value = []
      status.value = 'error'
    }
  }
  const schedule = () => {
    clearInterval(timer)
    if (document.hidden || !query.value) return
    void refresh()
    timer = setInterval(refresh, 60_000)
  }
  restore()
  watch(query, () => {
    ++request
    items.value = []
    status.value = 'idle'
    schedule()
  }, { immediate: true })
  useWindowUpdates('x-monitor', async key => {
    if (key === 'snapshot') await refresh()
  })
  window.addEventListener('storage', onStorage)
  document.addEventListener('visibilitychange', schedule)
  onScopeDispose(() => {
    ++request
    clearInterval(timer)
    window.removeEventListener('storage', onStorage)
    document.removeEventListener('visibilitychange', schedule)
  })
  return { available: !!source, enabled, items, status, setEnabled, refresh }
}
