import type { BrowserWindow, IpcMainInvokeEvent, WebContents } from 'electron'

interface WorkspaceOptions {
  entry: string
  background: boolean
  create: () => BrowserWindow
  openAttribution: () => void
}

export const createWorkspaceWindows = ({ entry, background, create, openAttribution }: WorkspaceOptions) => {
  const documentUrl = new URL(entry)
  documentUrl.hash = ''
  const ownsDocument = (url: string) => url.split('#', 1)[0] === documentUrl.href
  // Insertion order tracks the last focused live window, including detached pages.
  const owned = new Map<WebContents, BrowserWindow>()
  let quitting = false

  const isTrusted = ({ sender, senderFrame }: IpcMainInvokeEvent) =>
    !quitting && owned.has(sender) && !sender.isDestroyed() && senderFrame !== null &&
    senderFrame === sender.mainFrame && ownsDocument(senderFrame.url)

  const open = async (hash = '') => {
    if (quitting) throw new Error('应用正在退出')
    const url = new URL(documentUrl)
    url.hash = hash
    const window = create()
    const contents = window.webContents
    owned.set(contents, window)
    window.once('closed', () => owned.delete(contents))
    window.on('focus', () => {
      if (owned.delete(contents)) owned.set(contents, window)
    })
    const guardNavigation = (event: { url: string; isMainFrame: boolean; preventDefault: () => void }) => {
      if (!event.isMainFrame || !ownsDocument(event.url)) event.preventDefault()
    }
    contents.on('will-frame-navigate', guardNavigation)
    contents.on('will-redirect', guardNavigation)
    contents.setWindowOpenHandler(({ url }) => {
      if (ownsDocument(contents.mainFrame.url) && url.startsWith('https://www.tradingview.com/?')) openAttribution()
      return { action: 'deny' }
    })
    try {
      await window.loadURL(url.href)
      if (!background && !quitting && !window.isDestroyed()) window.show()
    } catch (error) {
      if (!window.isDestroyed()) window.destroy()
      throw error
    }
  }

  const activate = async () => {
    if (quitting) return
    const window = [...owned.values()].at(-1)
    if (!window) return open()
    if (!background) {
      if (window.isMinimized()) window.restore()
      window.focus()
    }
  }

  return { open, activate, isTrusted, beginQuit: () => { quitting = true } }
}
