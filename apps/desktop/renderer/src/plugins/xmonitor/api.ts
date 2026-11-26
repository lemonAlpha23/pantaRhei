import { createXApi, type XApi } from '../../../../shared/xmonitor'
import { fetchTransport } from '../../core/http'

declare global {
  interface Window {
    xMonitor?: XApi
  }
}

export const xApi = window.xMonitor ?? createXApi(fetchTransport, async url => {
  const article = window.open('about:blank', '_blank')
  if (!article) throw new Error('浏览器未能打开原帖')
  article.opener = null
  article.location.replace(url)
})
