import assert from 'node:assert/strict'
import { setImmediate } from 'node:timers/promises'
import { test } from 'node:test'
import { createMonitorPolling } from '../src/plugins/market/monitor/polling.ts'

test('先读缓存；刷新完成后再等待 30 秒，暂停或离开页面即停止调度', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const calls: string[] = []
  let visible = true, automatic = true
  const first = Promise.withResolvers<void>()
  const loop = createMonitorPolling({
    visible: () => visible, automatic: () => automatic,
    read: async () => { calls.push('cache') },
    refresh: async () => { calls.push('refresh'); await first.promise },
  })
  try {
    const pending = loop.sync()
    await setImmediate()
    t.mock.timers.tick(60_000)
    assert.deepEqual(calls, ['cache', 'refresh'])
    first.resolve()
    await pending
    t.mock.timers.tick(29_999)
    assert.equal(calls.length, 2)
    t.mock.timers.tick(1)
    await setImmediate()
    assert.deepEqual(calls, ['cache', 'refresh', 'refresh'])
    automatic = false
    await loop.sync()
    t.mock.timers.tick(90_000)
    assert.equal(calls.at(-1), 'cache')
    await loop.refreshNow()
    automatic = true
    visible = false
    await loop.sync()
    const count = calls.length
    t.mock.timers.tick(90_000)
    assert.equal(calls.length, count)
    visible = true
    await loop.sync()
    assert.deepEqual(calls.slice(-2), ['cache', 'refresh'])
    loop.stop()
    t.mock.timers.tick(90_000)
    assert.equal(calls.length, count + 2)
  } finally { loop.stop() }
})

test('暂停时可仅重读跨窗缓存；切换股票池时慢请求完成后才执行下一次', async () => {
  let automatic = false
  const calls: string[] = []
  const first = Promise.withResolvers<void>()
  const loop = createMonitorPolling({
    visible: () => true, automatic: () => automatic,
    read: async () => { calls.push('cache') },
    refresh: async () => { calls.push('refresh'); await first.promise },
  })
  try {
    await loop.sync()
    await loop.readCached()
    assert.deepEqual(calls, ['cache', 'cache'])
    const pending = loop.refreshNow()
    automatic = true
    void loop.sync()
    assert.deepEqual(calls, ['cache', 'cache', 'refresh'])
    first.resolve()
    await pending
    assert.deepEqual(calls, ['cache', 'cache', 'refresh', 'cache', 'refresh'])
  } finally { loop.stop() }
})
