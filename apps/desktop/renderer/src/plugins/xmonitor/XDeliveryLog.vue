<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { ChevronDown, ChevronRight, Inbox, RefreshCw } from 'lucide-vue-next'
import type { XDelivery, XDeliveryAttempt, XDeliveryStatus } from '../../../../shared/xmonitor'
import { errorText } from '../../core/http'
import { useWindowUpdates } from '../../core/window-updates'
import { xApi } from './api'

const status = defineModel<XDeliveryStatus | 'all'>('status', { required: true })
const labels = { all: '全部', pending: '待投递', sent: '已送达', failed: '失败', sending: '投递中', unknown: '结果未知' }
const filters = ['all', 'failed', 'pending', 'sent'] as const
const stamp = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
})
const time = (value: string | null) => {
  const parsed = Date.parse(value ?? '')
  return Number.isFinite(parsed) ? stamp.format(parsed) : '—'
}
const outcome = (code: number | null, error: string | null) => {
  if (!code) return error ?? ''
  const http = 'HTTP ' + code
  return !error ? http : error.includes(http) ? error : http + ' · ' + error
}
const rows = shallowRef<XDelivery[]>([])
const cursor = ref<number | null>(null)
const expanded = ref('')
const attempts = shallowRef<XDeliveryAttempt[] | null>(null)
const loading = ref(false)
const retrying = ref('')
const olderPage = ref(false)
const loadError = ref('')
const detailError = ref('')
const result = ref<{ ok: boolean; message: string }>()
let listVersion = 0
let detailVersion = 0

const loadAttempts = async (id: string) => {
  const ticket = ++detailVersion
  detailError.value = ''
  try {
    const data = await xApi.getDeliveryAttempts(id)
    if (ticket === detailVersion && id === expanded.value) attempts.value = data.items
  } catch (error) {
    if (ticket === detailVersion && id === expanded.value) detailError.value = errorText(error, '投递详情读取失败。')
  }
}
const details = (id: string) => {
  expanded.value = expanded.value === id ? '' : id
  attempts.value = null
  if (expanded.value) void loadAttempts(id)
}
const load = async (more = false) => {
  const before = more ? cursor.value : undefined
  if (before === null || (more && loading.value)) return
  const ticket = ++listVersion
  loading.value = true
  loadError.value = ''
  try {
    const page = await xApi.getDeliveries(status.value, before)
    if (ticket !== listVersion) return
    if (more) {
      const ids = new Set(rows.value.map(row => row.id))
      rows.value = [...rows.value, ...page.items.filter(row => !ids.has(row.id))]
    } else rows.value = page.items
    cursor.value = page.nextCursor
    olderPage.value = more
    if (!rows.value.some(row => row.id === expanded.value)) expanded.value = ''
    if (expanded.value && !more) await loadAttempts(expanded.value)
  } catch (error) {
    if (ticket === listVersion) loadError.value = errorText(error, '投递记录读取失败。')
  } finally {
    if (ticket === listVersion) loading.value = false
  }
}
const publish = useWindowUpdates('x-deliveries', () => load())
const retry = async (row: XDelivery) => {
  if (retrying.value || !row.retryable) return
  retrying.value = row.id
  result.value = undefined
  try { result.value = await xApi.retryDelivery(row.id, row.attempts) }
  catch (error) { result.value = { ok: false, message: errorText(error, '重试请求失败。') } }
  finally {
    await load()
    publish('deliveries')
    retrying.value = ''
  }
}
watch(status, () => {
  expanded.value = ''
  rows.value = []
  cursor.value = null
  result.value = undefined
  void load()
}, { immediate: true })
let timer: ReturnType<typeof setInterval> | undefined
const refreshVisible = () => {
  if (!document.hidden && !loading.value && !retrying.value && !olderPage.value) void load()
}
onMounted(() => {
  timer = setInterval(refreshVisible, 15_000)
  document.addEventListener('visibilitychange', refreshVisible)
})
onBeforeUnmount(() => {
  clearInterval(timer)
  document.removeEventListener('visibilitychange', refreshVisible)
})
</script>

<template>
  <section aria-label="Webhook 投递记录">
    <div class="toolbar">
      <label>投递状态
        <select v-model="status" aria-label="投递状态"><option v-for="filter in filters" :key="filter" :value="filter">{{ labels[filter] }}</option></select>
      </label>
      <button type="button" class="action" :disabled="loading || !!retrying" @click="load()"><RefreshCw :size="14" />刷新记录</button>
    </div>
    <p v-if="result" class="feedback" :class="{ bad: !result.ok }" role="status">{{ result.message }}</p>
    <p v-if="loadError" class="feedback bad" role="alert">{{ loadError }} <button type="button" @click="load()">重新读取</button></p>
    <div v-if="!rows.length && !loadError" class="empty" role="status">
      <Inbox :size="23" /><strong>{{ loading ? '正在读取投递记录' : status === 'all' ? '暂无投递记录' : '暂无符合条件的记录' }}</strong>
    </div>
    <div v-if="rows.length" class="ledger">
      <div class="columns labels" aria-hidden="true"><span>来源帖子</span><span>状态</span><span>最近尝试 · 上海时间</span><span>操作</span></div>
      <article v-for="row in rows" :key="row.id" :aria-label="'@' + row.handle + ' 帖子 ' + row.id">
        <div class="columns row">
          <div class="source"><strong>@{{ row.handle }}</strong><small>{{ row.id }}</small></div>
          <div><span class="state" :class="row.status"><i></i>{{ labels[row.status] }}</span><small>尝试 {{ row.attempts }} 次</small></div>
          <div class="timing"><time :datetime="row.lastAttemptAt ?? undefined">{{ time(row.lastAttemptAt) }}</time>
            <small v-if="row.httpStatus || row.error">{{ outcome(row.httpStatus, row.error) }}</small>
          </div>
          <div class="actions">
            <button v-if="row.status === 'failed'" type="button" class="retry" :disabled="!row.retryable || !!retrying"
              :title="row.retryBlockedReason || undefined" @click="retry(row)">{{ retrying === row.id ? '重试中' : '重试' }}</button>
            <button type="button" class="detail-button" :aria-expanded="expanded === row.id" :aria-label="'投递详情 ' + row.id" @click="details(row.id)">
              详情 <component :is="expanded === row.id ? ChevronDown : ChevronRight" :size="13" />
            </button>
          </div>
          <p v-if="row.retryBlockedReason && row.status === 'failed'" class="blocked">{{ row.retryBlockedReason }}</p>
        </div>
        <div v-if="expanded === row.id" class="detail">
          <div class="detail-title"><h3>投递尝试</h3>
            <span v-if="row.createdAt">入队 {{ time(row.createdAt) }}</span>
            <span v-if="row.nextAttemptAt">下次可重试 {{ time(row.nextAttemptAt) }}</span>
          </div>
          <p v-if="detailError" class="feedback bad" role="alert">{{ detailError }} <button type="button" @click="loadAttempts(row.id)">重读详情</button></p>
          <ol v-else-if="attempts?.length" aria-label="投递尝试列表">
            <li v-for="attempt in attempts" :key="attempt.number"><strong>第 {{ attempt.number }} 次</strong>
              <span>{{ labels[attempt.status] }}</span><time>{{ time(attempt.at) }}</time>
              <span v-if="attempt.httpStatus || attempt.error">{{ outcome(attempt.httpStatus, attempt.error) }}</span>
            </li>
          </ol>
          <p v-else>{{ attempts === null ? '正在读取尝试记录' : '暂无逐次尝试记录' }}</p>
        </div>
      </article>
    </div>
    <div v-if="cursor !== null" class="more"><button class="action" type="button" :disabled="loading" @click="load(true)">加载更多</button></div>
  </section>
</template>

<style scoped lang="scss">
.toolbar, .actions, .detail-title, .toolbar label, .detail-button { display: flex; align-items: center; gap: 8px; }
.toolbar { justify-content: space-between; flex-wrap: wrap; margin-bottom: 20px; }
.toolbar label { color: var(--muted); font-size: 13px; }
select { border-radius: 8px; padding: 6px 9px; border: 1px solid var(--line); background: var(--surface); color: var(--text); font: inherit; }
.columns { display: grid; grid-template-columns: minmax(155px, 1.2fr) minmax(80px, .55fr) minmax(210px, 1.5fr) minmax(84px, auto); align-items: center; gap: 10px; }
.labels { padding-bottom: 10px; color: var(--muted); font-size: 12px; border-bottom: 1px solid var(--line); > :last-child { text-align: right; } }
article { border-bottom: 1px solid var(--line-soft); }
.row { padding: 14px 0; font-size: 14px; }
.source, .timing { overflow-wrap: anywhere; }
.source strong { font-weight: 600; }
small, time { font-variant-numeric: tabular-nums; }
small { display: block; color: var(--muted); font-size: 12px; margin-top: 2px; }
.state { display: inline-flex; align-items: center; gap: 6px; i { width: 6px; height: 6px; border-radius: 50%; background: currentColor; } }
.state.sent { color: var(--down); } .state.failed, .bad { color: var(--up); } .state.pending { color: var(--muted); }
.actions { justify-content: flex-end; gap: 12px; }
.actions button, .feedback button { padding: 4px 0; color: var(--primary); font-size: 13px; }
.actions .detail-button { color: var(--muted); gap: 2px; }
.blocked { grid-column: 1 / -1; color: var(--muted); font-size: 12px; }
.detail { padding: 14px 16px; margin-bottom: 12px; background: var(--soft); border-radius: 10px; color: var(--muted); font-size: 12px; }
.detail-title { flex-wrap: wrap; gap: 4px 14px; margin-bottom: 5px; h3 { font-size: 13px; color: var(--text); } }
ol { padding: 0; margin: 0; list-style: none;
  li { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 12px; padding: 6px 0; }
  strong { font-weight: 550; color: var(--text); }
}
.feedback { margin: 10px 0; font-size: 13px; }
.more { margin-top: 15px; text-align: center; }
@media (max-width: 760px) {
  .labels { display: none; }
  .ledger { border-top: 1px solid var(--line); }
  .row { grid-template-columns: minmax(0, 1fr) minmax(0, auto); gap: 8px; }
  .row > :nth-child(2) { text-align: right; }
  .timing { font-size: 12px; color: var(--muted); }
}
</style>
