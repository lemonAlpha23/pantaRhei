import assert from 'node:assert/strict'
import { test } from 'node:test'
import { chartSnapshot, restoreChartSettings } from '../src/plugins/market/chart-settings.ts'
import { restoreComparison, restoreComparisonWindow, type ComparisonPreferences } from '../src/plugins/market/compare/compare.ts'

test('行情图选项可随窗口还原，非法值回退到日 K 和默认区间', () => {
  const selected = { mode: 'line' as const, range: Infinity, ma5: false, ma20: true, volume: false }
  assert.deepEqual(restoreChartSettings(chartSnapshot(selected)), selected)
  assert.deepEqual(restoreChartSettings({ range: '-1', mode: 'invalid', volume: 'false' }),
    { mode: 'candle', range: 63, ma5: true, ma20: true, volume: true })
})

test('独立对比页快照覆盖本窗口偏好，并区分空列表与未指定列表', () => {
  const available = ['600519', '300750', '601318']
  const previous: ComparisonPreferences = { symbols: ['600519', '300750'], range: 20 }
  assert.deepEqual(restoreComparisonWindow({ symbols: '601318,600519,601318,000000', range: 'all' }, available, previous),
    { symbols: ['601318', '600519'], range: 'all' })
  assert.deepEqual(restoreComparisonWindow({ symbols: '', range: '250' }, available, previous), { symbols: [], range: 250 })
  assert.deepEqual(restoreComparisonWindow({ range: 'unknown' }, available, previous), previous)
  assert.deepEqual(restoreComparisonWindow({ symbols: 'expired' }, available, previous), previous)
  const target = restoreComparisonWindow({ symbols: '601318', range: '60' }, available, previous)
  assert.deepEqual(restoreComparison(null, available, target), target)
  assert.deepEqual(restoreComparison('broken', available, target), target)
  assert.deepEqual(restoreComparison('{"symbols":[],"range":"all"}', available, target), { symbols: [], range: 'all' })
})
