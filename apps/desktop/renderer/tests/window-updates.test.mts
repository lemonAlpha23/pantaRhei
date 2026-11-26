import assert from 'node:assert/strict'
import { test } from 'node:test'
import { effectScope } from 'vue'
import { useWindowUpdates } from '../src/core/window-updates.ts'

test('同一插件的并发更新会在另一窗口读完后再读一次，重复通知合并', { timeout: 5000 }, async () => {
  const scope = effectScope()
  const peer = new BroadcastChannel('pantarhei:updates-test')
  const started = Promise.withResolvers<void>()
  const resume = Promise.withResolvers<void>()
  const synced = Promise.withResolvers<void>()
  const calls: string[] = []
  Object.defineProperty(globalThis, 'window', { configurable: true, value: { BroadcastChannel, workspaceWindows: {} } })
  try {
    const publish = scope.run(() => useWindowUpdates('updates-test', async key => {
      calls.push(key)
      if (calls.length === 1) { started.resolve(); await resume.promise }
      else if (key === 'watchlist') synced.resolve()
    }))!
    peer.postMessage('catalog')
    await started.promise
    publish('watchlist')
    publish('watchlist')
    resume.resolve()
    await synced.promise
    assert.deepEqual(calls, ['catalog', 'watchlist'])
  } finally {
    resume.resolve()
    peer.close()
    scope.stop()
    Reflect.deleteProperty(globalThis, 'window')
  }
})
