import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createMarketApi, type JsonRequest } from '../../shared/market.ts'

test('行情方法映射到预期的路径和 HTTP 方法', async () => {
  const calls: [string, string][] = []
  const response = { source: 'fixture' }
  const request: JsonRequest = async <T,>(path: string, method = 'GET') => {
    calls.push([method, path])
    return response as T
  }
  const api = createMarketApi(request)
  await api.getHealth()
  await api.listInstruments()
  await api.listInstruments('银行 & #1')
  assert.equal(await api.getHistory('000001'), response)
  await api.refreshHistory('000001')
  await api.importInstrument('600519')
  await api.getWatchlist()
  assert.equal(await api.getMonitor(), response)
  assert.equal(await api.refreshMonitor(), response)
  await api.setFavorite('600519', true)
  await api.setFavorite('600519', false)
  assert.deepEqual(calls, [
    ['GET', '/api/health'],
    ['GET', '/api/instruments'],
    ['GET', '/api/instruments?q=%E9%93%B6%E8%A1%8C+%26+%231'],
    ['GET', '/api/history/000001'],
    ['POST', '/api/history/000001/refresh'],
    ['POST', '/api/instruments/600519/import'],
    ['GET', '/api/watchlist'],
    ['GET', '/api/monitor'],
    ['POST', '/api/monitor/refresh'],
    ['PUT', '/api/watchlist/600519'],
    ['DELETE', '/api/watchlist/600519'],
  ])
})

test('不合法的代码、自选状态和查询不会进入传输层', async () => {
  let calls = 0
  const api = createMarketApi(async () => { calls++; throw new Error('unexpected request') })
  for (const symbol of ['', '12345', '1234567', '123456\n', '１２３４５６', '../123', 600519, null]) {
    for (const op of [api.getHistory, api.refreshHistory, api.importInstrument]) {
      await assert.rejects(Reflect.apply(op, undefined, [symbol]), /六位数字股票代码/)
    }
    await assert.rejects(Reflect.apply(api.setFavorite, undefined, [symbol, true]), /六位数字股票代码/)
  }
  for (const favorite of [undefined, null, 1, 'false']) {
    await assert.rejects(Reflect.apply(api.setFavorite, undefined, ['600519', favorite]), /自选状态/)
  }
  for (const query of ['股'.repeat(201), 123, null]) {
    await assert.rejects(Reflect.apply(api.listInstruments, undefined, [query]), /搜索关键字/)
  }
  assert.equal(calls, 0)
})
