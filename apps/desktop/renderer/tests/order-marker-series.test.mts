import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { XOrderMark } from '../../shared/xmonitor.ts'
import { groupOrderMarks, orderPriceMarkers, orderSeriesMarkers } from '../src/plugins/market/order-marker-series.ts'

const order = (id: string, publishedAt: string, action: 'buy' | 'sell' = 'buy'): XOrderMark => ({
  id, handle: 'trader' + id, publishedAt, action, price: 100, quantity: 300, orderType: 'limit',
})

test('按上海发帖日期匹配已有日 K，缺日不挪到相邻交易日', () => {
  const orders = [
    order('1', '2026-11-22T16:00:00Z'),
    order('2', '2026-11-21T03:00:00Z'),
    order('3', '2026-11-20T15:59:59Z'),
    order('4', 'invalid'),
  ]
  const days = groupOrderMarks(orders, [{ time: '2026-11-20' }, { time: '2026-11-23' }])
  assert.deepEqual(days.map(day => [day.date, day.orders[0].id]), [['2026-11-20', '3'], ['2026-11-23', '1']])
  assert.deepEqual(groupOrderMarks(orders, []), [])
})

test('同日保留多位作者的委托，分别聚合买卖方向，箭头纵向按 K 线定位', () => {
  const orders = [
    order('1', '2026-11-24T09:00:00+08:00'),
    order('2', '2026-11-24T02:00:00Z', 'sell'),
    order('3', '2026-11-24T09:30:00+08:00'),
  ]
  const days = groupOrderMarks(orders, [{ time: '2026-11-24' }])
  assert.deepEqual(days[0].orders.map(item => item.handle), ['trader2', 'trader3', 'trader1'])
  assert.deepEqual(orderSeriesMarkers(days, 'red', 'green'), [
    { time: '2026-11-24', position: 'belowBar', shape: 'arrowUp', color: 'red', text: '2' },
    { time: '2026-11-24', position: 'aboveBar', shape: 'arrowDown', color: 'green', text: undefined },
  ])
  assert.deepEqual(orderSeriesMarkers([], 'red', 'green'), [])
})

test('选中日的不复权 K 线以价格圆点展示人民币委托，同向同价合并，两侧同价分别可见', () => {
  const buy = { ...order('1', '2026-11-24T02:00:00Z'), priceInYuan: true }
  const day = { date: '2026-11-24', orders: [
    buy, { ...buy, id: '2' }, { ...buy, id: '3', action: 'sell' as const }, { ...buy, id: '4', price: 101.25 },
    { ...buy, id: '5', priceInYuan: false, price: 12.3 }, { ...buy, id: '6', priceInYuan: undefined, price: 13 },
    { ...buy, id: '7', price: null },
  ] }
  const markers = orderPriceMarkers(day, '不复权', 'red', 'green')
  assert.deepEqual(markers.map(item => [item.time, item.position, item.shape, item.price, item.color]), [
    ['2026-11-24', 'atPriceMiddle', 'circle', 100, 'red'],
    ['2026-11-24', 'atPriceMiddle', 'circle', 101.25, 'red'],
    ['2026-11-24', 'atPriceMiddle', 'circle', 100, 'green'],
  ])
  assert.ok(markers[0].size! > markers[2].size!)
  assert.deepEqual(orderPriceMarkers(undefined, '不复权', 'red', 'green'), [])
  assert.deepEqual(orderPriceMarkers(day, '前复权', 'red', 'green'), [])
  assert.deepEqual(orderPriceMarkers(day, undefined, 'red', 'green'), [])
})
