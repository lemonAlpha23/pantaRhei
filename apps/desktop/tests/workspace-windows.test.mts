import assert from 'node:assert/strict'
import { EventEmitter } from 'node:events'
import { test } from 'node:test'
import type { BrowserWindow, IpcMainInvokeEvent, WindowOpenHandlerResponse } from 'electron'
import { createWorkspaceWindows } from '../main/workspace-windows.ts'

const entry = 'file:///workspace/renderer/index.html'

class FakeWindow extends EventEmitter {
  shown = 0
  focused = 0
  minimized = false
  destroyed = false
  failLoad = false
  openLink?: (details: { url: string }) => WindowOpenHandlerResponse
  webContents = Object.assign(new EventEmitter(), {
    mainFrame: { url: '' },
    isDestroyed: () => this.destroyed,
    setWindowOpenHandler: (handler: FakeWindow['openLink']) => { this.openLink = handler },
  })

  async loadURL(url: string) {
    if (this.failLoad) throw new Error('load failed')
    this.webContents.mainFrame.url = url
  }
  show() { this.shown++ }
  focus() { this.focused++; this.emit('focus') }
  restore() { this.minimized = false }
  isDestroyed() { return this.destroyed }
  isMinimized() { return this.minimized }
  destroy() { this.destroyed = true; this.emit('closed') }
  event(frame: object | null = this.webContents.mainFrame) {
    return { sender: this.webContents, senderFrame: frame } as unknown as IpcMainInvokeEvent
  }
}

const fixture = (background = false) => {
  const created: FakeWindow[] = []
  const options = { failLoad: false, attributions: 0 }
  const windows = createWorkspaceWindows({
    entry, background,
    create: () => {
      const win = new FakeWindow()
      win.failLoad = options.failLoad
      created.push(win)
      return win as unknown as BrowserWindow
    },
    openAttribution: () => { options.attributions++ },
  })
  return { created, options, windows }
}

test('同页不同标的独立打开；激活时恢复最近活动窗口，关闭主窗不影响其余窗口', async () => {
  const { windows, created } = fixture()
  await windows.activate()
  await Promise.all([windows.open('#one'), windows.open('#two')])
  const [home, one, two] = created
  assert.deepEqual(created.map(w => w.webContents.mainFrame.url), [entry, entry + '#one', entry + '#two'])
  assert.deepEqual(created.map(w => w.shown), [1, 1, 1])
  one.focus()
  home.destroy()
  assert.equal(windows.isTrusted(home.event()), false)
  assert.ok(windows.isTrusted(one.event()) && windows.isTrusted(two.event()))
  one.minimized = true
  await windows.activate()
  assert.equal(one.minimized, false)
  assert.equal(one.focused, 2)
  two.destroy()
  one.destroy()
  await windows.activate()
  assert.equal(created.length, 4)
  assert.equal(created[3].webContents.mainFrame.url, entry)
})

test('只接受已登记窗口的应用主文档顶层 IPC，并阻止外部和子框架导航', async () => {
  const { windows, created, options } = fixture()
  await windows.activate()
  await windows.open('#other')
  const [home, other] = created
  assert.ok(windows.isTrusted(other.event()))
  assert.equal(windows.isTrusted(other.event(null)), false)
  assert.equal(windows.isTrusted(other.event(home.webContents.mainFrame)), false)
  assert.equal(windows.isTrusted(other.event({ url: entry })), false)
  assert.equal(windows.isTrusted(new FakeWindow().event()), false)
  for (const url of ['about:blank', entry + '/other', entry + '?override', 'https://example.com/#one']) {
    other.webContents.mainFrame.url = url
    assert.equal(windows.isTrusted(other.event()), false)
  }
  other.webContents.mainFrame.url = entry + '#new-state'
  assert.ok(windows.isTrusted(other.event()))
  for (const name of ['will-frame-navigate', 'will-redirect']) {
    for (const [url, isMainFrame, denied] of [[entry + '#state', true, false],
      [entry, false, true], ['https://example.com', true, true]] as const) {
      let blocked = false
      other.webContents.emit(name, { url, isMainFrame, preventDefault: () => { blocked = true } })
      assert.equal(blocked, denied)
    }
  }
  assert.deepEqual(other.openLink!({ url: 'https://example.com' }), { action: 'deny' })
  assert.equal(options.attributions, 0)
  assert.deepEqual(other.openLink!({ url: 'https://www.tradingview.com/?utm_source=test' }), { action: 'deny' })
  assert.equal(options.attributions, 1)
  assert.equal(created.length, 2)
})

test('后台不显示或聚焦；加载失败仅回收失败窗口；退出后不会重开', async () => {
  const { windows, created, options } = fixture(true)
  await windows.activate()
  await windows.open('#other')
  created[1].minimized = true
  await windows.activate()
  assert.equal(created[1].minimized, true)
  assert.ok(created.every(w => w.shown === 0 && w.focused === 0))
  options.failLoad = true
  await assert.rejects(windows.open('#failed'), /load failed/)
  assert.equal(created[2].destroyed, true)
  assert.equal(windows.isTrusted(created[2].event()), false)
  assert.ok(windows.isTrusted(created[0].event()))
  windows.beginQuit()
  assert.equal(windows.isTrusted(created[0].event()), false)
  await assert.rejects(windows.open(), /正在退出/)
  created[0].destroy()
  created[1].destroy()
  await windows.activate()
  assert.equal(created.length, 3)
})
