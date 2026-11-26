import type { JsonRequest } from './http'

export type { JsonRequest } from './http'

export interface Instrument {
  symbol: string
  name: string
  exchange: string
  currency: string
  timezone: string
  sector: string
  close: number
  change: number | null
  changePercent: number | null
  asOf: string
}

export interface Bar {
  time: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface History {
  bars: Bar[]
  source: string
  adjustment: string
  asOf: string
}

export interface MonitorQuote {
  symbol: string
  price: number
  previousClose: number | null
  quotedAt: string
}

export interface MonitorSnapshot {
  quotes: MonitorQuote[]
  failed: string[]
  checkedAt: string | null
}

const stockCode = (symbol: string) => {
  if (typeof symbol !== 'string' || symbol.length !== 6 || /[^0-9]/.test(symbol)) {
    throw new Error('请输入六位数字股票代码')
  }
  return symbol
}

export const createMarketApi = (request: JsonRequest) => ({
  getHealth: () => request<{ status: 'ok' }>('/api/health'),
  listInstruments: async (query = '') => {
    if (typeof query !== 'string' || query.length > 200) {
      throw new Error('搜索关键字必须为不超过 200 个字符的文本')
    }
    const suffix = query ? '?' + new URLSearchParams({ q: query }) : ''
    return request<Instrument[]>('/api/instruments' + suffix)
  },
  getHistory: async (symbol: string) => request<History>(`/api/history/${stockCode(symbol)}`),
  refreshHistory: async (symbol: string) => request<History>(`/api/history/${stockCode(symbol)}/refresh`, 'POST'),
  importInstrument: async (symbol: string) => request<Instrument>(`/api/instruments/${stockCode(symbol)}/import`, 'POST'),
  getWatchlist: () => request<string[]>('/api/watchlist'),
  getMonitor: () => request<MonitorSnapshot>('/api/monitor'),
  refreshMonitor: () => request<MonitorSnapshot>('/api/monitor/refresh', 'POST'),
  setFavorite: async (symbol: string, favorite: boolean) => {
    if (typeof favorite !== 'boolean') throw new Error('自选状态必须为布尔值')
    return request<string[]>(`/api/watchlist/${stockCode(symbol)}`, favorite ? 'PUT' : 'DELETE')
  },
})

export type MarketApi = ReturnType<typeof createMarketApi>
