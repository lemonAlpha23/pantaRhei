import type { IpcMain, IpcMainInvokeEvent } from 'electron'

const namespaces = new WeakMap<object, string>()

export const BindMapping = (namespace: string) => (controller: object) => {
  namespaces.set(controller, namespace)
}

export const registerController = (
  ipc: Pick<IpcMain, 'handle'>,
  controller: { readonly actions: object },
  isTrusted: (event: IpcMainInvokeEvent) => boolean,
) => {
  const namespace = namespaces.get(controller.constructor)
  if (!namespace) throw new Error('IPC 控制器缺少 @BindMapping')

  const actions: [string, unknown][] = Object.entries(controller.actions)
  for (const [name, action] of actions) {
    if (typeof action !== 'function') throw new Error(`无效的 IPC 操作：${name}`)
    ipc.handle(`${namespace}:${name}`, (event, ...args: unknown[]) => {
      if (!isTrusted(event)) throw new Error('无效的请求来源')
      return action(...args)
    })
  }
}
