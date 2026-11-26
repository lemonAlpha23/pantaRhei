import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { IpcMain, IpcMainInvokeEvent } from 'electron'
import { BindMapping, registerController } from '../main/ipc/bind-mapping.ts'

test('仅注册标注控制器的公开操作，并在调用前验证窗口', () => {
  class Example {
    readonly actions = { getHistory: (symbol: string) => symbol }
    readonly internal = () => 'private'
  }
  const handlers = new Map<string, Parameters<IpcMain['handle']>[1]>()
  const ipc = { handle: (channel: string, listener: Parameters<IpcMain['handle']>[1]) => {
    handlers.set(channel, listener)
  } }
  const trusted = {} as IpcMainInvokeEvent
  const controller = new Example()
  const register = () => registerController(ipc, controller, event => event === trusted)

  assert.throws(register, /BindMapping/)
  BindMapping('market')(Example)
  register()
  assert.deepEqual([...handlers.keys()], ['market:getHistory'])
  const handler = handlers.get('market:getHistory')!
  assert.throws(() => handler({} as IpcMainInvokeEvent, '600519'), /请求来源/)
  assert.equal(handler(trusted, '600519'), '600519')
})
