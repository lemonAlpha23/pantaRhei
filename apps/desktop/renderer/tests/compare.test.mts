import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { History } from '../../shared/market.ts'
import { comparisonDates, comparisonSeries, restoreComparison } from '../src/plugins/market/compare/compare.ts'

const date = (day: number) => '2026-09-' + String(day).padStart(2, '0')
const history = (days: number[]): History => ({
  source: '测试', adjustment: '前复权', asOf: date(days.at(-1) ?? 1),
  bars: days.map(day => ({ time: date(day), open: day, low: day, high: day, close: day, volume: 100 })),
})

test('不同覆盖日期的股票共用同一个末端、相同的截取区间，并保留缺失位置', () => {
  const days = Array.from({ length: 30 }, (_, i) => i + 1)
  const early = history(days.slice(0, -1))
  const late = history(days.slice(13))
  const dates = comparisonDates([late, early], 20)
  assert.deepEqual(dates, days.slice(10).map(date))
  const left = comparisonSeries(early.bars, dates)
  const right = comparisonSeries(late.bars, dates)
  assert.deepEqual(left.points.map(p => p.time), right.points.map(p => p.time))
  assert.deepEqual(left.points.at(-1), { time: date(30) })
  assert.deepEqual(right.points[0], { time: date(11) })
  assert.equal(left.change, null)
  assert.equal(right.change, null)
  assert.equal(left.missing, 1)
  assert.equal(right.missing, 3)
})

test('区间变动用共同首末交易日的收盘价，中间缺日不伪造日线', () => {
  const stock = history([10, 20])
  const dates = comparisonDates([stock, history([15])], 'all')
  const series = comparisonSeries(stock.bars, dates)
  assert.equal(series.change, 100)
  assert.equal(series.missing, 1)
  assert.deepEqual(series.points[1], { time: date(15) })
  assert.equal(comparisonSeries(stock.bars, [date(20)]).change, null)
  assert.equal(comparisonSeries(stock.bars, []).change, null)
})

test('恢复选择保留顺序和空列表，忽略非法代码、重复与损坏的设置', () => {
  const codes = ['600519', '300750', '601318', '600036', '002594']
  assert.deepEqual(restoreComparison(null, codes), { symbols: codes.slice(0, 2), range: 60 })
  assert.deepEqual(restoreComparison('{', codes), { symbols: codes.slice(0, 2), range: 60 })
  assert.deepEqual(restoreComparison('{"symbols":[],"range":"all"}', codes), { symbols: [], range: 'all' })
  const symbols = [codes[2], codes[2], 'unknown', ...codes]
  assert.deepEqual(restoreComparison(JSON.stringify({ symbols, range: 120 }), codes),
    { symbols: [codes[2], codes[0], codes[1], codes[3]], range: 120 })
  assert.deepEqual(restoreComparison('{"symbols":["gone"],"range":"invalid"}', codes),
    { symbols: codes.slice(0, 2), range: 60 })
})
