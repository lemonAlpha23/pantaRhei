import assert from 'node:assert/strict'
import { after, test } from 'node:test'
import { fileURLToPath } from 'node:url'
import { createPinia } from 'pinia'
import { createServer } from 'vite'
import type { History, Instrument, MarketApi } from '../../shared/market.ts'
import type { useWorkspace as workspaceFactory } from '../src/plugins/market/store.ts'

const server = await createServer({
  root: fileURLToPath(new URL('../', import.meta.url)),
  configFile: false,
  optimizeDeps: { noDiscovery: true },
  server: { middlewareMode: true, hmr: false },
})
after(() => server.close())
const { useWorkspace } = await server.ssrLoadModule('/src/plugins/market/store.ts') as { useWorkspace: typeof workspaceFactory }

const deferred = <T,>() => {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => { resolve = done })
  return { promise, resolve }
}

const history = (close: number): History => {
  return {
    asOf: '2026-11-25', source: '测试', adjustment: '前复权',
    bars: [{ time: '2026-11-25', open: close, close, high: close, low: close, volume: 100 }],
  }
}

const instrument = (symbol: string): Instrument => {
  return { symbol, name: symbol, exchange: 'SSE', currency: 'CNY', timezone: 'Asia/Shanghai',
    sector: '', close: 10, change: null, changePercent: null, asOf: '2026-11-25' }
}

test('切换股票时去重更新，迟到的本地日线不会覆盖相同交易日的已更新值', async () => {
  const first = '600519'
  const second = '601318'
  const read = deferred<History>()
  const online = deferred<History>()
  let refreshRequests = 0
  let readRequests = 0
  const terminal: Pick<MarketApi, 'refreshHistory' | 'getHistory'> = {
    getHistory: symbol => {
      if (symbol === first) { readRequests++; return read.promise }
      if (symbol === second) return Promise.resolve(history(20))
      throw new Error(`Unexpected symbol ${symbol}`)
    },
    refreshHistory: symbol => {
      assert.equal(symbol, first)
      refreshRequests++
      return online.promise
    },
  }
  Object.defineProperty(globalThis, 'window', { configurable: true, value: { terminal } })
  const store = useWorkspace(createPinia())
  store.instruments = [instrument(first), instrument(second)]
  try {
    const initialRead = store.select(first)
    const firstUpdate = store.refresh()
    await store.select(second)
    assert.equal(store.refreshing, false)
    assert.equal(store.history?.bars[0].close, 20)
    const repeatedRead = store.select(first)
    const repeatedUpdate = store.refresh()
    assert.equal(store.loading, true)
    assert.equal(store.refreshing, true)
    assert.equal(readRequests, 1)
    assert.equal(refreshRequests, 1)
    online.resolve(history(12))
    await Promise.all([firstUpdate, repeatedUpdate])
    assert.equal(store.loading, false)
    assert.equal(store.refreshing, false)
    assert.equal(store.current?.close, 12)
    assert.equal(store.history?.bars[0].close, 12)
    read.resolve(history(10))
    await Promise.all([initialRead, repeatedRead])
    assert.equal(store.current?.close, 12)
    assert.equal(store.history?.bars[0].close, 12)
    await store.select(second)
    assert.equal(store.current?.close, 20)
    assert.equal(store.history?.bars[0].close, 20)
    await store.select(first)
    assert.equal(store.history?.bars[0].close, 12)
  } finally {
    Reflect.deleteProperty(globalThis, 'window')
    store.$dispose()
  }
})
