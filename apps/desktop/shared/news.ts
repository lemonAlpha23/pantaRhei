import type { JsonRequest } from './http'

export interface NewsItem {
  id: string
  sourceId: string
  title: string
  url: string
  publishedAt: string
}

export interface NewsSource {
  id: string
  name: string
  lastUpdatedAt: string | null
  error: string | null
}

export interface NewsDigest {
  items: NewsItem[]
  sources: NewsSource[]
}

export const createNewsApi = (request: JsonRequest, openUrl: (url: string) => Promise<void>) => ({
  getNews: () => request<NewsDigest>('/api/news'),
  refreshNews: () => request<NewsDigest>('/api/news/refresh', 'POST'),
  openArticle: async (id: string) => {
    if (typeof id !== 'string' || id.length !== 64 || /[^0-9a-f]/.test(id)) {
      throw new Error('无效的资讯编号')
    }
    const article = await request<{ url: string }>(`/api/news/${id}/link`)
    const url = new URL(article.url)
    if (url.protocol !== 'https:' || url.username || url.password || url.port) throw new Error('原文地址无效')
    await openUrl(url.href)
  },
})

export type NewsApi = ReturnType<typeof createNewsApi>
