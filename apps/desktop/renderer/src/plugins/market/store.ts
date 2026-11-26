import { computed, onScopeDispose, ref, shallowReactive, shallowRef } from 'vue'
import { defineStore } from 'pinia'
import { useWindowUpdates } from '../../core/window-updates'
import { errorText, getMarketApi, type History, type Instrument } from './api'

export const useWorkspace = defineStore('workspace', () => {
  const market = getMarketApi()
  const instruments = shallowRef<Instrument[]>([])
  const watchlist = ref<string[]>([])
  const selected = ref('600519')
  const histories = shallowReactive(new Map<string, History>())
  const reads = shallowReactive(new Map<string, Promise<void>>())
  const refreshes = shallowReactive(new Map<string, Promise<void>>())
  const readErrors = shallowReactive(new Map<string, string>())
  const history = computed(() => histories.get(selected.value) ?? null)
  const starting = ref(true)
  const loading = computed(() => reads.has(selected.value) && !history.value)
  const refreshing = computed(() => refreshes.has(selected.value))
  const saving = ref(false)
  const startupError = ref('')
  const historyError = computed(() => readErrors.get(selected.value) ?? '')
  const notice = ref('')
  const searchMode = ref<'stock' | 'favorites' | null>(null)
  const current = computed(() => instruments.value.find(item => item.symbol === selected.value))
  const favorites = computed(() => watchlist.value.flatMap(symbol => instruments.value.filter(i => i.symbol === symbol)))
  let noticeTimer: ReturnType<typeof setTimeout> | undefined
  onScopeDispose(() => clearTimeout(noticeTimer))

  const notify = (message: string) => {
    clearTimeout(noticeTimer)
    notice.value = message
    noticeTimer = setTimeout(() => { notice.value = '' }, 5000)
  }

  const acceptHistory = (symbol: string, data: History, online: boolean) => {
    const cached = histories.get(symbol)
    // A late disk read must not replace an online update from the same trading day.
    if (cached && (!data.bars.length || cached.asOf > data.asOf || (cached.asOf === data.asOf && !online))) return cached
    histories.set(symbol, data)
    readErrors.delete(symbol)
    const latest = data.bars.at(-1)
    const previous = data.bars.at(-2)
    if (latest) {
      const change = previous ? latest.close - previous.close : null
      const changePercent = change !== null && previous?.close ? change / previous.close * 100 : null
      instruments.value = instruments.value.map(item => item.symbol === symbol
        ? { ...item, asOf: data.asOf, close: latest.close, change, changePercent } : item)
    }
    return data
  }

  const select = async (symbol: string) => {
    selected.value = symbol
    if (histories.has(symbol)) return
    const pending = reads.get(symbol)
    if (pending) return pending
    readErrors.delete(symbol)
    const read = market.getHistory(symbol)
      .then(data => { acceptHistory(symbol, data, false) })
      .catch(error => {
        if (!histories.has(symbol)) readErrors.set(symbol, errorText(error, '历史行情读取失败'))
      })
      .finally(() => { reads.delete(symbol) })
    reads.set(symbol, read)
    return read
  }

  let initialization: Promise<void> | undefined
  const loadInitial = async () => {
    starting.value = true
    startupError.value = ''
    try {
      const [catalog, saved] = await Promise.all([
        market.listInstruments(), market.getWatchlist(),
      ])
      instruments.value = catalog
      watchlist.value = saved
      const first = catalog.find(item => item.symbol === selected.value) ?? catalog[0]
      if (first) await select(first.symbol)
    } catch {
      startupError.value = '无法连接本地行情服务'
    } finally {
      starting.value = false
    }
  }

  const initialize = () => {
    initialization ??= loadInitial().finally(() => { initialization = undefined })
    return initialization
  }

  const publish = useWindowUpdates('market', async key => {
    await initialization
    if (key === 'watchlist') watchlist.value = await market.getWatchlist()
    else if (key === 'catalog') instruments.value = await market.listInstruments()
    else if (/^[0-9]{6}$/.test(key)) {
      if (histories.has(key) || reads.has(key) || selected.value === key) {
        acceptHistory(key, await market.getHistory(key), true)
      } else {
        instruments.value = await market.listInstruments()
      }
    }
  })

  const toggleFavorite = async (symbol: string) => {
    if (saving.value) return
    saving.value = true
    try {
      const exists = watchlist.value.includes(symbol)
      watchlist.value = await market.setFavorite(symbol, !exists)
      publish('watchlist')
      notify(exists ? '已移出自选' : '已加入自选')
    } catch (error) {
      notify(errorText(error, '自选股保存失败，请重试'))
    } finally {
      saving.value = false
    }
  }

  const importInstrument = async (symbol: string) => {
    const result = await market.importInstrument(symbol)
    instruments.value = [...instruments.value.filter(item => item.symbol !== result.symbol), result]
    publish('catalog')
    return result
  }

  const refresh = async () => {
    if (!current.value) return
    const symbol = selected.value
    const pending = refreshes.get(symbol)
    if (pending) return pending
    const update = market.refreshHistory(symbol)
      .then(data => {
        const accepted = acceptHistory(symbol, data, true)
        publish(symbol)
        if (selected.value === symbol) notify(`数据截至 ${accepted.asOf}`)
      })
      .catch(error => {
        if (selected.value === symbol) notify(errorText(error, '在线更新失败，可继续查看本地行情'))
      })
      .finally(() => { refreshes.delete(symbol) })
    refreshes.set(symbol, update)
    return update
  }

  return { instruments, watchlist, selected, history, current, favorites, starting, loading, searchMode,
    refreshing, saving, startupError, historyError, notice, select, initialize, toggleFavorite, refresh, importInstrument }
})
