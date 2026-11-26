import { createNewsApi, type NewsApi } from '../../../../shared/news'
import { fetchTransport } from '../../core/http'

export type { NewsDigest, NewsItem } from '../../../../shared/news'

declare global {
  interface Window {
    news?: NewsApi
  }
}

const browserApi = createNewsApi(fetchTransport, async url => window.location.assign(url))
export const getNewsApi = (): NewsApi => window.news ?? browserApi
