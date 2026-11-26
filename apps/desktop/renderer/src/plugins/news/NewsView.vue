<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import { ArrowUpRight, CircleAlert, Newspaper, RefreshCw } from 'lucide-vue-next'
import { errorText } from '../../core/http'
import { usePageWindowState } from '../../core/page-window'
import { useWindowUpdates } from '../../core/window-updates'
import { getNewsApi, type NewsDigest, type NewsItem } from './api'

const news = getNewsApi()
const digest = shallowRef<NewsDigest>({ items: [], sources: [] })
const reading = ref(true)
const refreshing = ref(false)
const online = ref(navigator.onLine)
const requestError = ref('')
const articleError = ref<{ id: string; message: string } | null>(null)
const openingId = ref<string | null>(null)
const selectedSource = ref<string | null>(null)
const initial = usePageWindowState((): Record<string, string> =>
  selectedSource.value ? { source: selectedSource.value } : {})
selectedSource.value = initial.source || null

const zone = 'Asia/Shanghai'
const dayFormat = new Intl.DateTimeFormat('zh-CN', { timeZone: zone, month: 'long', day: 'numeric' })
const yearFormat = new Intl.DateTimeFormat('zh-CN', { timeZone: zone, year: 'numeric' })
const weekFormat = new Intl.DateTimeFormat('zh-CN', { timeZone: zone, weekday: 'long' })
const clockFormat = new Intl.DateTimeFormat('zh-CN', {
  timeZone: zone, hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
})
const sourceNames = computed(() => new Map(digest.value.sources.map(source => [source.id, source.name])))
const latestUpdate = computed(() => {
  const times = digest.value.sources.map(source => Date.parse(source.lastUpdatedAt ?? '')).filter(Number.isFinite)
  if (!times.length) return ''
  const latest = Math.max(...times)
  return yearFormat.format(latest) + dayFormat.format(latest) + ' ' + clockFormat.format(latest)
})

type DayGroup = { day: string; yearWeek: string; entries: { item: NewsItem; time: string }[] }
const groups = computed(() => {
  const days = new Map<string, DayGroup>()
  const entries = digest.value.items
    .filter(item => selectedSource.value === null || item.sourceId === selectedSource.value)
    .map(item => ({ item, timestamp: Date.parse(item.publishedAt) }))
    .sort((a, b) => (Number.isFinite(b.timestamp) ? b.timestamp : -Infinity) -
      (Number.isFinite(a.timestamp) ? a.timestamp : -Infinity))
  for (const { item, timestamp } of entries) {
    const dated = Number.isFinite(timestamp)
    const day = dated ? dayFormat.format(timestamp) : '日期未知'
    const year = dated ? yearFormat.format(timestamp) : ''
    const key = year + day
    let group = days.get(key)
    if (!group) {
      group = { day, yearWeek: dated ? year + ' · ' + weekFormat.format(timestamp) : '', entries: [] }
      days.set(key, group)
    }
    group.entries.push({ item, time: dated ? clockFormat.format(timestamp) : '—' })
  }
  return [...days.values()]
})

const status = computed(() => {
  const cached = digest.value.items.length > 0
  if (!online.value) return cached ? '当前离线，显示已缓存的资讯。' : '当前离线，尚无本地资讯。'
  if (requestError.value) return requestError.value + (cached ? '，已保留本地资讯。' : '')
  const failed = digest.value.sources.filter(source => source.error)
  if (!failed.length) return ''
  const allFailed = failed.length === digest.value.sources.length
  const names = allFailed ? '全部来源' : failed.map(source => source.name).join('、')
  const hasFailedCache = digest.value.items.some(item => failed.some(source => source.id === item.sourceId))
  return names + '更新失败' + (hasFailedCache ? '，保留了上次获取的标题。' : '。')
})

const setDigest = (next: NewsDigest) => {
  digest.value = next
  if (next.sources.length && !next.sources.some(source => source.id === selectedSource.value)) selectedSource.value = null
}

let nextRead = 0
let lastApplied = 0
const readCache = async () => {
  const version = ++nextRead
  const next = await news.getNews()
  if (version < lastApplied) return
  lastApplied = version
  setDigest(next)
  requestError.value = ''
}
const publish = useWindowUpdates('news', async key => {
  if (key === 'headlines') await readCache()
})

const refresh = async () => {
  if (reading.value || refreshing.value) return
  refreshing.value = true
  requestError.value = ''
  try {
    const next = await news.refreshNews()
    lastApplied = ++nextRead
    setDigest(next)
    publish('headlines')
  } catch (error) {
    requestError.value = errorText(error, '资讯更新失败，请稍后重试')
  } finally {
    refreshing.value = false
  }
}

const initialize = async () => {
  try {
    await readCache()
  } catch (error) {
    requestError.value = errorText(error, '本地资讯读取失败')
    return
  } finally {
    reading.value = false
  }
  if (!digest.value.items.length && !latestUpdate.value) await refresh()
}

const open = async (item: NewsItem) => {
  if (openingId.value === item.id) return
  openingId.value = item.id
  articleError.value = null
  try {
    await news.openArticle(item.id)
  } catch (error) {
    if (openingId.value === item.id) articleError.value = { id: item.id, message: errorText(error, '原文打开失败，请重试') }
  } finally {
    if (openingId.value === item.id) openingId.value = null
  }
}

const updateConnection = () => { online.value = navigator.onLine }
onMounted(() => {
  window.addEventListener('online', updateConnection)
  window.addEventListener('offline', updateConnection)
  void initialize()
})
onBeforeUnmount(() => {
  window.removeEventListener('online', updateConnection)
  window.removeEventListener('offline', updateConnection)
})
</script>

<template>
  <section class="news-view" aria-labelledby="news-title">
    <header class="news-header">
      <div>
        <h1 id="news-title">财经资讯</h1>
        <p v-if="latestUpdate" class="updated">最近更新 {{ latestUpdate }} · 上海时间</p>
      </div>
      <button class="action refresh" :disabled="reading || refreshing" @click="refresh">
        <RefreshCw :size="16" :class="{ spinning: refreshing }" />{{ refreshing ? '刷新中' : '刷新' }}
      </button>
    </header>

    <div v-if="digest.sources.length" class="filters" role="group" aria-label="资讯来源">
      <button :aria-pressed="selectedSource === null" @click="selectedSource = null">全部来源</button>
      <button v-for="source in digest.sources" :key="source.id" :aria-pressed="source.id === selectedSource"
        @click="selectedSource = source.id">{{ source.name }}</button>
    </div>

    <div v-if="status && !reading" role="status" class="feedback"><CircleAlert :size="16" /><span>{{ status }}</span></div>

    <div v-if="reading || (refreshing && !digest.items.length)" class="empty news-empty" role="status">
      <RefreshCw class="spinning" :size="22" /><strong>{{ reading ? '正在读取本地资讯' : '正在获取资讯' }}</strong>
    </div>
    <div v-else-if="!groups.length" class="empty news-empty">
      <Newspaper :size="25" /><strong>{{ selectedSource ? '该来源暂无资讯' : '暂无资讯' }}</strong>
    </div>
    <section v-for="group in groups" v-else :key="group.yearWeek + group.day" class="day-group">
      <div class="dateline">
        <h2>{{ group.day }}</h2><span v-if="group.yearWeek">{{ group.yearWeek }}</span>
      </div>
      <ul>
        <li v-for="{ item, time } in group.entries" :key="item.id">
          <button class="story" :aria-label="'打开原文：' + item.title" :aria-busy="openingId === item.id" @click="open(item)">
            <time :datetime="item.publishedAt">{{ time }}</time>
            <span class="story-copy"><span class="source">{{ sourceNames.get(item.sourceId) ?? item.sourceId }}</span><span class="headline">{{ item.title }}</span></span>
            <ArrowUpRight class="outbound" :size="17" aria-hidden="true" />
          </button>
          <p v-if="articleError && articleError.id === item.id" class="article-error" role="alert">{{ articleError.message }}</p>
        </li>
      </ul>
    </section>
  </section>
</template>

<style scoped lang="scss">
.news-view { min-width: 0; }
.news-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  margin-bottom: 24px;

  h1 {
    color: var(--text);
    font-size: clamp(30px, 3vw, 44px);
    font-weight: 550;
    letter-spacing: -.05em;
  }
}
.updated { margin-top: 4px; color: var(--muted); font-size: 13px; }
.refresh { flex-shrink: 0; }
.filters {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-bottom: 20px;

  button {
    min-height: 33px;
    padding: 0 14px;
    border-radius: 100px;
    color: var(--muted);
    font-size: 13px;
    font-weight: 550;
    &:hover { color: var(--text); background: var(--soft); }
    &[aria-pressed='true'] { color: var(--primary); background: var(--primary-soft); }
  }
}
.feedback {
  display: flex;
  align-items: baseline;
  gap: 9px;
  margin: 0 0 15px;
  padding: 11px 14px;
  border-radius: 10px;
  color: var(--muted);
  background: var(--soft);
  font-size: 13px;
  overflow-wrap: anywhere;
  svg { align-self: center; }
}
.news-empty { min-height: 270px; border-top: 1px solid var(--line); }
.day-group {
  display: grid;
  grid-template-columns: clamp(130px, 17vw, 230px) minmax(0, 1fr);
  column-gap: clamp(20px, 3vw, 48px);
  padding: 12px 0 16px;
  border-top: 1px solid var(--line);
}
.dateline {
  padding: 14px 0;
  h2 { font-size: 22px; font-weight: 550; line-height: 1.4; }
  > span { display: inline-block; margin-top: 3px; font-size: 12px; color: var(--muted); }
}
ul { margin: 0; padding: 0; list-style: none; min-width: 0; }
li + li { border-top: 1px solid var(--line-soft); }
.story {
  width: 100%;
  display: grid;
  grid-template-columns: 50px minmax(0, 1fr) 20px;
  align-items: baseline;
  gap: 12px;
  padding: 14px 5px;
  text-align: left;
  border-radius: 5px;

  time { font-size: 13px; color: var(--dim); font-variant-numeric: tabular-nums; }
  &:hover .headline, &:focus-visible .headline, &:hover .outbound { color: var(--primary); }
}
.story-copy { display: grid; gap: 3px; min-width: 0; }
.source { color: var(--muted); font-size: 12px; }
.headline { color: var(--text); font-size: 16px; line-height: 1.55; font-weight: 520; overflow-wrap: anywhere; }
.outbound { align-self: center; justify-self: end; color: var(--dim); }
.article-error { margin: 0 0 9px 66px; color: var(--up); font-size: 12px; overflow-wrap: anywhere; }
.spinning { animation: news-spin 1s linear infinite; }
@keyframes news-spin { to { transform: rotate(360deg); } }

@media (max-width: 700px) {
  .news-header { margin-bottom: 16px; }
  .updated { font-size: 12px; }
  .filters { margin-bottom: 14px; gap: 2px; button { padding-inline: 10px; } }
  .day-group { display: block; padding: 10px 0; }
  .dateline {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: 8px;
    padding: 6px 0 3px;
    h2 { font-size: 18px; }
  }
  .story { grid-template-columns: 39px minmax(0, 1fr) 17px; padding: 12px 1px; gap: 8px; }
  .headline { font-size: 15px; }
  .article-error { margin-left: 48px; }
}
</style>
