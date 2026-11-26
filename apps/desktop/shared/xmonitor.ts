import type { JsonRequest } from './http'
import type { XConnection, XDeliveryAttempt, XDeliveryPage, XDeliveryStatus, XSettings, XSettingsPatch, XTestResult } from './x-connections'
export type { XConnection, XDelivery, XDeliveryAttempt, XDeliveryPage, XDeliveryStatus, XSettings, XSettingsPatch, XTestResult } from './x-connections'

export interface XSignal {
  kind: 'order' | 'trade'
  orderType: 'limit' | 'market' | null
  action: 'buy' | 'sell'
  symbol: string
  price: number | null
  quantity: number | null
}

export interface XOrderMark extends Pick<XSignal, 'action' | 'orderType' | 'price' | 'quantity'> {
  id: string
  handle: string
  publishedAt: string
  priceInYuan?: boolean
}

export type XNoticeMode = 'off' | 'orders' | 'all'

export interface XNotice {
  id: string
  handle: string
  text: string
  publishedAt: string
  signal: XSignal
  read: boolean
}

export interface XInbox {
  unread: number
  items: XNotice[]
}

export interface XSnapshot {
  configured: boolean
  deliveryConfigured: boolean
  syncing: boolean
  accounts: { handle: string; enabled: boolean; noticeMode: XNoticeMode; lastCheckedAt: string | null; error: string | null }[]
  posts: {
    id: string
    handle: string
    text: string
    publishedAt: string
    signal: XSignal | null
    delivery: 'pending' | 'sent' | 'failed' | null
  }[]
}

const cleanHandle = (raw: string) => {
  const handle = typeof raw === 'string' ? raw.trim().replace(/^@/, '').toLowerCase() : ''
  if (!/^[a-z0-9_]{1,15}$/.test(handle)) throw new Error('请输入有效的 X 用户名')
  return handle
}

const postId = (id: string) => {
  if (typeof id !== 'string' || !/^[1-9][0-9]{0,18}$/.test(id)) throw new Error('原帖编号无效')
  return id
}

const dateStamp = (day: string) => {
  if (typeof day !== 'string' || !/^(?!0000)\d{4}-\d{2}-\d{2}$/.test(day)) throw new Error('标记日期无效')
  const utc = Date.parse(day + 'T00:00:00Z')
  if (!Number.isFinite(utc) || new Date(utc).toISOString().slice(0, 10) !== day) throw new Error('标记日期无效')
  return utc
}

const settingsPatch = (patch: XSettingsPatch) => {
  if (!patch || typeof patch !== 'object' || Array.isArray(patch) || !Object.keys(patch).length) {
    throw new Error('请选择要更新的连接配置')
  }
  const body: XSettingsPatch = {}
  for (const [key, value] of Object.entries(patch)) {
    if (key !== 'xToken' && key !== 'webhookUrl' && key !== 'webhookToken') throw new Error('连接配置字段无效')
    if (value === null) {
      body[key] = null
      continue
    }
    const input = typeof value === 'string' ? value.trim() : ''
    if (!input || input.length > 8192) throw new Error('连接配置为空或过长')
    if (key === 'webhookUrl') {
      let url: URL
      try { url = new URL(input) } catch { throw new Error('请输入完整的 HTTPS 地址') }
      if (url.protocol !== 'https:' || !/^https:\/\/[^/@?#]+(?:[/?]|$)/i.test(input) ||
          !url.hostname || url.port === '0' || !/^[!-~]+$/.test(input) || /[\\#]/.test(input)) {
        throw new Error('请输入有效的 HTTPS 接收地址')
      }
    } else if (!/^[!-~]+$/.test(input)) throw new Error('令牌中含有无效字符')
    body[key] = input
  }
  return body
}

export const createXApi = (request: JsonRequest, open: (url: string) => Promise<void>) => ({
  getSettings: () => request<XSettings>('/api/x-monitor/settings'),
  saveSettings: async (patch: XSettingsPatch, expectedRevision: number) => {
    if (!Number.isSafeInteger(expectedRevision) || expectedRevision < 0) throw new Error('请重新读取连接配置')
    return request<XSettings>('/api/x-monitor/settings', 'PATCH', { ...settingsPatch(patch), expectedRevision })
  },
  testConnection: async (which: XConnection) => {
    if (which !== 'x' && which !== 'webhook') throw new Error('连接类型无效')
    return request<XTestResult>('/api/x-monitor/settings/test/' + which, 'POST')
  },
  getDeliveries: async (status: XDeliveryStatus | 'all' = 'all', before?: number) => {
    if (!['all', 'failed', 'pending', 'sent'].includes(status)) throw new Error('投递筛选条件无效')
    const params = new URLSearchParams({ status })
    if (before !== undefined) {
      if (!Number.isSafeInteger(before) || before <= 0) throw new Error('分页位置无效')
      params.set('before', String(before))
    }
    return request<XDeliveryPage>('/api/x-monitor/deliveries?' + params)
  },
  getDeliveryAttempts: async (id: string) => request<{ items: XDeliveryAttempt[] }>(`/api/x-monitor/deliveries/${postId(id)}/attempts`),
  retryDelivery: async (id: string, attempts: number) => {
    if (!Number.isSafeInteger(attempts) || attempts < 0) throw new Error('投递次数无效')
    return request<{ ok: boolean; message: string }>(`/api/x-monitor/deliveries/${postId(id)}/retry`, 'POST', { attempts })
  },
  getMonitor: () => request<XSnapshot>('/api/x-monitor'),
  getOrderMarks: async (symbol: string, start: string, end: string) => {
    if (typeof symbol !== 'string' || !/^[0-9]{6}$/.test(symbol)) throw new Error('请输入六位数字股票代码')
    const span = dateStamp(end) - dateStamp(start)
    if (span < 0 || span > 3660 * 86_400_000) throw new Error('标记日期范围无效')
    return request<{ items: XOrderMark[] }>('/api/x-monitor/order-markers?' + new URLSearchParams({ symbol, start, end }))
  },
  addAccount: async (handle: string) => request<XSnapshot>('/api/x-monitor/accounts', 'POST', { handle: cleanHandle(handle) }),
  setAccountEnabled: async (handle: string, enabled: boolean) => {
    if (typeof enabled !== 'boolean') throw new Error('订阅状态无效')
    return request<XSnapshot>('/api/x-monitor/accounts/' + cleanHandle(handle), 'PATCH', { enabled })
  },
  setNoticeMode: async (handle: string, noticeMode: XNoticeMode) => {
    if (!['off', 'orders', 'all'].includes(noticeMode)) throw new Error('提醒方式无效')
    return request<XSnapshot>('/api/x-monitor/accounts/' + cleanHandle(handle), 'PATCH', { noticeMode })
  },
  getNotices: async (limit?: number) => {
    if (limit !== undefined && (!Number.isInteger(limit) || limit < 1 || limit > 100)) throw new Error('提醒条数无效')
    return request<XInbox>('/api/x-monitor/notices' + (limit === undefined ? '' : '?limit=' + limit))
  },
  markNoticeRead: async (id: string) => request<XInbox>(`/api/x-monitor/notices/${postId(id)}/read`, 'POST'),
  markAllNoticesRead: () => request<XInbox>('/api/x-monitor/notices/read-all', 'POST'),
  removeAccount: async (handle: string) => request<XSnapshot>('/api/x-monitor/accounts/' + cleanHandle(handle), 'DELETE'),
  refresh: () => request<XSnapshot>('/api/x-monitor/refresh', 'POST'),
  openPost: async (handle: string, id: string) => {
    await open(`https://x.com/${cleanHandle(handle)}/status/${postId(id)}`)
  },
})

export type XApi = ReturnType<typeof createXApi>
