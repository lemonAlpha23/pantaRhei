import type { JsonRequest } from './http'

export type AlertDirection = 'above' | 'below'

export interface AlertInput {
  symbol: string
  direction: AlertDirection
  target: number
}

export interface AlertRule extends AlertInput {
  id: number
  enabled: boolean
}

export interface AlertEvent extends AlertInput {
  id: number
  ruleId: number | null
  price: number
  quotedAt: string
}

export interface AlertSnapshot {
  rules: AlertRule[]
  events: AlertEvent[]
}

export interface AlertCheck {
  rules: number
  evaluated: number
}

const rulePath = (id: number) => {
  if (!Number.isSafeInteger(id) || id < 1) throw new Error('价格提醒编号无效')
  return `/api/alerts/${id}`
}

export const createAlertsApi = (request: JsonRequest) => ({
  getAlerts: () => request<AlertSnapshot>('/api/alerts'),
  createAlert: async (rule: AlertInput) => {
    if (typeof rule?.symbol !== 'string' || !/^\d{6}$/.test(rule.symbol)) throw new Error('请输入六位数字股票代码')
    const { symbol, direction, target } = rule
    if (direction !== 'above' && direction !== 'below') throw new Error('请选择提醒方向')
    if (!Number.isFinite(target) || target <= 0 || target > 999999.99 || Number(target.toFixed(2)) !== target) {
      throw new Error('目标价须为 0.01 至 999999.99 元，最多两位小数')
    }
    return request<AlertSnapshot>('/api/alerts', 'POST', { symbol, direction, target })
  },
  setAlertEnabled: async (id: number, enabled: boolean) => {
    if (typeof enabled !== 'boolean') throw new Error('价格提醒状态无效')
    return request<AlertSnapshot>(rulePath(id), 'PATCH', { enabled })
  },
  deleteAlert: async (id: number) => request<AlertSnapshot>(rulePath(id), 'DELETE'),
  checkAlerts: () => request<AlertSnapshot & { check: AlertCheck }>('/api/alerts/check', 'POST'),
})

export type AlertsApi = ReturnType<typeof createAlertsApi>
