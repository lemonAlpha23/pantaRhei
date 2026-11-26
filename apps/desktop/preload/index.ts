import { contextBridge, ipcRenderer } from 'electron'
import type { AlertsApi } from '../shared/alerts'
import type { MarketApi } from '../shared/market'
import type { NewsApi } from '../shared/news'
import type { WindowsApi } from '../shared/windows'
import type { XApi } from '../shared/xmonitor'

const terminal: MarketApi = {
  getHealth: () => ipcRenderer.invoke('market:getHealth'),
  listInstruments: query => ipcRenderer.invoke('market:listInstruments', query),
  getHistory: symbol => ipcRenderer.invoke('market:getHistory', symbol),
  refreshHistory: symbol => ipcRenderer.invoke('market:refreshHistory', symbol),
  importInstrument: symbol => ipcRenderer.invoke('market:importInstrument', symbol),
  getWatchlist: () => ipcRenderer.invoke('market:getWatchlist'),
  getMonitor: () => ipcRenderer.invoke('market:getMonitor'),
  refreshMonitor: () => ipcRenderer.invoke('market:refreshMonitor'),
  setFavorite: (symbol, favorite) => ipcRenderer.invoke('market:setFavorite', symbol, favorite),
}

contextBridge.exposeInMainWorld('terminal', terminal)

const news: NewsApi = {
  getNews: () => ipcRenderer.invoke('news:getNews'),
  refreshNews: () => ipcRenderer.invoke('news:refreshNews'),
  openArticle: id => ipcRenderer.invoke('news:openArticle', id),
}
contextBridge.exposeInMainWorld('news', news)

const xMonitor: XApi = {
  getSettings: () => ipcRenderer.invoke('xmonitor:getSettings'),
  saveSettings: (patch, revision) => ipcRenderer.invoke('xmonitor:saveSettings', patch, revision),
  testConnection: which => ipcRenderer.invoke('xmonitor:testConnection', which),
  getDeliveries: (status, before) => ipcRenderer.invoke('xmonitor:getDeliveries', status, before),
  getDeliveryAttempts: id => ipcRenderer.invoke('xmonitor:getDeliveryAttempts', id),
  retryDelivery: (id, attempts) => ipcRenderer.invoke('xmonitor:retryDelivery', id, attempts),
  getMonitor: () => ipcRenderer.invoke('xmonitor:getMonitor'),
  getOrderMarks: (symbol, start, end) => ipcRenderer.invoke('xmonitor:getOrderMarks', symbol, start, end),
  addAccount: handle => ipcRenderer.invoke('xmonitor:addAccount', handle),
  setAccountEnabled: (handle, enabled) => ipcRenderer.invoke('xmonitor:setAccountEnabled', handle, enabled),
  setNoticeMode: (handle, mode) => ipcRenderer.invoke('xmonitor:setNoticeMode', handle, mode),
  getNotices: limit => ipcRenderer.invoke('xmonitor:getNotices', limit),
  markNoticeRead: id => ipcRenderer.invoke('xmonitor:markNoticeRead', id),
  markAllNoticesRead: () => ipcRenderer.invoke('xmonitor:markAllNoticesRead'),
  removeAccount: handle => ipcRenderer.invoke('xmonitor:removeAccount', handle),
  refresh: () => ipcRenderer.invoke('xmonitor:refresh'),
  openPost: (handle, id) => ipcRenderer.invoke('xmonitor:openPost', handle, id),
}
contextBridge.exposeInMainWorld('xMonitor', xMonitor)

const alerts: AlertsApi = {
  getAlerts: () => ipcRenderer.invoke('alerts:getAlerts'),
  createAlert: rule => ipcRenderer.invoke('alerts:createAlert', rule),
  setAlertEnabled: (id, enabled) => ipcRenderer.invoke('alerts:setAlertEnabled', id, enabled),
  deleteAlert: id => ipcRenderer.invoke('alerts:deleteAlert', id),
  checkAlerts: () => ipcRenderer.invoke('alerts:checkAlerts'),
}
contextBridge.exposeInMainWorld('alerts', alerts)

const workspaceWindows: WindowsApi = {
  openPage: target => ipcRenderer.invoke('windows:openPage', target),
}
contextBridge.exposeInMainWorld('workspaceWindows', workspaceWindows)
