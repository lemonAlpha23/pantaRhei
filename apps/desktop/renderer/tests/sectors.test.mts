import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { Instrument } from '../../shared/market.ts'
import { sectorDates, sectorMetrics } from '../src/plugins/market/sectors/metrics.ts'

const latest = '2026-11-25'
const earlier = '2026-11-24'
const stock = (symbol: string, sector: string, changePercent: number | null, asOf = latest): Instrument => ({
  symbol, sector, changePercent, asOf, name: symbol, currency: 'CNY', exchange: 'SSE',
  timezone: 'Asia/Shanghai', close: 10, change: null,
})

test('仅使用股票池内同日的最新报价，历史日期和陈旧成分分别处理', () => {
  const current = stock('600001', '银行', 2)
  const stale = stock('600002', '银行', 40, earlier)
  const stocks = [stale, current, stock('600003', '电力', 5), stock('600004', '银行', 6, '2026-02-30')]
  assert.deepEqual(sectorDates(stocks), [latest, earlier])
  assert.deepEqual(sectorMetrics(stocks, latest).find(item => item.id === '银行')?.members, [current])
  assert.deepEqual(sectorMetrics(stocks, earlier)[0].members, [stale])
  assert.deepEqual(sectorMetrics(stocks, '2026-02-30'), [])
  assert.deepEqual(sectorMetrics([], latest), [])
})

test('按有效个股等权统计，平盘、缺值和未分类保留各自口径', () => {
  const stocks = [
    stock('600004', ' 银行 ', null), stock('600002', '银行', -2),
    stock('600003', '银行', 0), stock('600001', '银行', 8),
    stock('600005', '', NaN), stock('600006', '未分类', Infinity),
  ]
  const [bank, other] = sectorMetrics(stocks, latest)
  assert.deepEqual(bank, {
    id: '银行', count: 4, valid: 3, changePercent: 2,
    up: 1, down: 1, flat: 1, unknown: 1, members: [stocks[3], stocks[2], stocks[1], stocks[0]],
  })
  assert.equal(other.id, '未分类')
  assert.equal(other.count, 2)
  assert.equal(other.unknown, 2)
  assert.equal(other.flat, 0)
  assert.equal(other.changePercent, null)
  assert.equal(sectorMetrics([stocks[2]], latest)[0].changePercent, 0)
  assert.equal(stocks[0].symbol, '600004')
})
