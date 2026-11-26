import { createMarketApi, type MarketApi } from '../../../../shared/market'
import { fetchTransport } from '../../core/http'

export type { Bar, History, Instrument, MonitorQuote, MonitorSnapshot } from '../../../../shared/market'
export { errorText } from '../../core/http'

declare global {
  interface Window {
    terminal?: MarketApi
  }
}

const browserApi = createMarketApi(fetchTransport)
export const getMarketApi = (): MarketApi => window.terminal ?? browserApi

