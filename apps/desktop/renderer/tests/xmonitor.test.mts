import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createXApi } from '../../shared/xmonitor.ts'
import type { JsonRequest } from '../../shared/http.ts'

test('下单标记以股票代码和上海自然日区间读取，拒绝无效日期', async () => {
  const operations: unknown[][] = []
  const result = { items: [{ id: '12', handle: 'demo', publishedAt: '2024-02-28T16:15:00Z',
    action: 'sell', price: 18.8, quantity: null, orderType: 'limit' }] }
  const request: JsonRequest = async <T,>(...args: Parameters<JsonRequest>) => {
    operations.push(args)
    return result as T
  }
  const api = createXApi(request, async () => { assert.fail('读取标记不应打开原帖') })
  assert.equal(await api.getOrderMarks('000001', '2024-02-29', '2024-02-29'), result)
  for (const [start, end] of [['2025-02-29', '2025-03-01'], ['2024-02-29', '2024-02-28'],
    ['0000-01-01', '0001-01-01'], ['2024-1-1', '2024-02-29'], ['2000-01-01', '2024-02-29']]) {
    await assert.rejects(api.getOrderMarks('000001', start, end), /日期/)
  }
  await assert.rejects(api.getOrderMarks('600519&start=x', '2024-02-29', '2024-02-29'), /股票代码/)
  assert.deepEqual(operations, [['/api/x-monitor/order-markers?symbol=000001&start=2024-02-29&end=2024-02-29']])
})

test('连接操作只发送显式修改的字段，重试携带当前尝试次数', async () => {
  const calls: unknown[][] = []
  const request: JsonRequest = async (...args) => { calls.push(args); return undefined as never }
  const api = createXApi(request, async () => {})
  await api.getSettings()
  await api.saveSettings({ webhookUrl: ' https://receiver.example/events ', webhookToken: null }, 2)
  await api.testConnection('webhook')
  await api.getDeliveries('failed', 42)
  await api.getDeliveryAttempts('100')
  await api.retryDelivery('100', 3)
  assert.deepEqual(calls, [
    ['/api/x-monitor/settings'],
    ['/api/x-monitor/settings', 'PATCH', { webhookUrl: 'https://receiver.example/events', webhookToken: null, expectedRevision: 2 }],
    ['/api/x-monitor/settings/test/webhook', 'POST'], ['/api/x-monitor/deliveries?status=failed&before=42'],
    ['/api/x-monitor/deliveries/100/attempts'], ['/api/x-monitor/deliveries/100/retry', 'POST', { attempts: 3 }],
  ])
})

test('无效的连接配置和投递操作在 IPC 请求前被拒绝，错误不回显密钥', async () => {
  const api = createXApi(async () => { assert.fail('不应调用接口') }, async () => {})
  for (const patch of [{}, { bad: 'secret-test' }, { xToken: 'a\nsecret-test' }, { webhookToken: 7 },
    { webhookUrl: 'http://receiver.example/secret-test' }, { webhookUrl: 'https://secret-test@receiver.example/' },
    { webhookUrl: 'https://receiver.example/#secret-test' }]) {
    await assert.rejects(Reflect.apply(api.saveSettings, undefined, [patch, 0]),
      error => error instanceof Error && error.name !== 'AssertionError' && !error.message.includes('secret-test'))
  }
  await assert.rejects(api.saveSettings({ xToken: null }, -1), /重新读取/)
  await assert.rejects(Reflect.apply(api.testConnection, undefined, ['unknown']), /连接类型/)
  await assert.rejects(Reflect.apply(api.getDeliveries, undefined, ['unknown']), /筛选/)
  await assert.rejects(api.getDeliveries('all', -1), /分页/)
  await assert.rejects(api.getDeliveryAttempts('3/retry'), /编号/)
  await assert.rejects(api.retryDelivery('4', -1), /次数/)
})

test('X 动态契约规范化账号，并仅使用 X 原帖链接', async () => {
  const operations: unknown[][] = []
  const request: JsonRequest = async (...args) => { operations.push(args); return undefined as never }
  const opened: string[] = []
  const api = createXApi(request, async url => { opened.push(url) })
  await api.addAccount(' @Demo ')
  await api.setAccountEnabled('@DEMO', false)
  await api.removeAccount('demo')
  await api.refresh()
  await api.getMonitor()
  await api.openPost('DeMo', '123')
  assert.deepEqual(operations, [
    ['/api/x-monitor/accounts', 'POST', { handle: 'demo' }], ['/api/x-monitor/accounts/demo', 'PATCH', { enabled: false }],
    ['/api/x-monitor/accounts/demo', 'DELETE'], ['/api/x-monitor/refresh', 'POST'], ['/api/x-monitor'],
  ])
  await assert.rejects(api.openPost('../admin', '42'), /用户名/)
  await assert.rejects(api.openPost('demo', '42?target=next'), /编号/)
  await assert.rejects(api.addAccount('https://x.com/demo'), /用户名/)
  assert.deepEqual(opened, ['https://x.com/demo/status/123'])
})

test('X 提醒桥支持概览与收件箱，模式及帖子编号在传输前验证', async () => {
  const operations: unknown[][] = []
  const response = { unread: 0, items: [] }
  const request: JsonRequest = async <T,>(...args: Parameters<JsonRequest>) => {
    operations.push(args)
    return response as T
  }
  const api = createXApi(request, async () => { assert.fail('标记已读不应打开原帖') })
  await api.setNoticeMode('@Demo', 'orders')
  await api.getNotices(1)
  assert.equal(await api.getNotices(), response)
  await api.markNoticeRead('1844674407370955101')
  await api.markAllNoticesRead()
  for (const limit of [null, -1, 0, 1.5, 101, '1']) {
    await assert.rejects(Reflect.apply(api.getNotices, undefined, [limit]), /条数/)
  }
  await assert.rejects(Reflect.apply(api.setNoticeMode, undefined, ['demo', 'everything']), /提醒方式/)
  await assert.rejects(api.setNoticeMode('demo/../evil', 'off'), /用户名/)
  await assert.rejects(api.markNoticeRead('../read-all'), /编号/)
  assert.deepEqual(operations, [
    ['/api/x-monitor/accounts/demo', 'PATCH', { noticeMode: 'orders' }],
    ['/api/x-monitor/notices?limit=1'], ['/api/x-monitor/notices'],
    ['/api/x-monitor/notices/1844674407370955101/read', 'POST'], ['/api/x-monitor/notices/read-all', 'POST'],
  ])
})
