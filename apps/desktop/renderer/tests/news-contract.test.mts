import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { JsonRequest } from '../../shared/http.ts'
import { createNewsApi } from '../../shared/news.ts'

const id = '9a'.repeat(32)
const url = 'https://www.eeo.com.cn/2026/1101/100000.shtml'

test('读取与更新资讯只访问本地 API，打开原文时先按编号查询链接', async () => {
  const requests: [string, string][] = []
  const opened: string[] = []
  const digest = { items: [], sources: [] }
  const request: JsonRequest = async <T,>(path: string, method = 'GET') => {
    requests.push([method, path])
    return (path.endsWith('/link') ? { url } : digest) as T
  }
  const api = createNewsApi(request, async link => { opened.push(link) })
  assert.equal(await api.getNews(), digest)
  assert.equal(await api.refreshNews(), digest)
  assert.deepEqual(opened, [])
  await api.openArticle(id)
  assert.deepEqual(requests, [['GET', '/api/news'], ['POST', '/api/news/refresh'], ['GET', `/api/news/${id}/link`]])
  assert.deepEqual(opened, [url])
})

test('原文入口拒绝任意网址、无效编号和非 HTTPS 链接', async () => {
  const unexpected = async (): Promise<never> => assert.fail('不应打开原文或发起请求')
  const api = createNewsApi(unexpected, unexpected)
  for (const value of [url, '', id + '\n', 'x'.repeat(64), null]) {
    await assert.rejects(Reflect.apply(api.openArticle, undefined, [value]), /资讯编号/)
  }
  for (const raw of ['file:///example', 'http://example.com', 'https://user@www.eeo.com.cn', 'https://www.eeo.com.cn:8443']) {
    const request: JsonRequest = async <T,>() => ({ url: raw }) as T
    await assert.rejects(createNewsApi(request, unexpected).openArticle(id), /原文地址/)
  }
})
