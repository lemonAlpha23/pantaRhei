import { app, BrowserWindow, ipcMain, shell } from 'electron'
import path from 'node:path'
import { pathToFileURL } from 'node:url'
import { AlertsController } from './alerts-controller'
import { createBackend, createBackendRequest } from './backend'
import { registerController } from './ipc/bind-mapping'
import { MarketController } from './market-controller'
import { NewsController } from './news-controller'
import { WindowsController } from './windows-controller'
import { XMonitorController } from './xmonitor-controller'
import { createWorkspaceWindows } from './workspace-windows'

app.setName('Panta Rhei')
const background = process.env.PANTARHEI_BACKGROUND === '1'
const devUrl = !app.isPackaged && process.env.ELECTRON_RENDERER_URL
const entry = devUrl || pathToFileURL(path.resolve(__dirname, '../renderer/index.html')).href
let backend: ReturnType<typeof createBackend> | undefined

const windows = createWorkspaceWindows({
  entry, background,
  create: () => new BrowserWindow({
    width: 1420, height: 920, minWidth: 820, minHeight: 600,
    show: false,
    title: 'Panta Rhei', backgroundColor: '#ffffff', autoHideMenuBar: true,
    webPreferences: {
      preload: path.resolve(__dirname, '../preload/index.cjs'),
      sandbox: true, contextIsolation: true, nodeIntegration: false,
      backgroundThrottling: !background,
    },
  }),
  openAttribution: () => { void shell.openExternal('https://www.tradingview.com/') },
})

const activate = () => {
  void windows.activate().catch(error => console.error('工作台窗口加载失败', error))
}

if (!app.requestSingleInstanceLock()) {
  app.quit()
} else {
  app.whenReady().then(() => {
    backend = createBackend({
      resourcesPath: app.isPackaged ? process.resourcesPath : undefined,
      projectDir: path.resolve(app.getAppPath(), '../backend'),
      dataDir: path.join(app.getPath('userData'), 'data'),
    })
    const request = createBackendRequest(backend)
    registerController(ipcMain, new MarketController(request), windows.isTrusted)
    registerController(ipcMain, new AlertsController(request), windows.isTrusted)
    registerController(ipcMain, new NewsController(request), windows.isTrusted)
    registerController(ipcMain, new XMonitorController(request), windows.isTrusted)
    registerController(ipcMain, new WindowsController(windows.open), windows.isTrusted)
    app.on('activate', activate)
    app.on('second-instance', activate)
    activate()
  }).catch(error => {
    console.error('Panta Rhei 启动失败', error)
    app.quit()
  })
}
app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit() })
app.on('before-quit', () => {
  windows.beginQuit()
  backend?.stop()
})
