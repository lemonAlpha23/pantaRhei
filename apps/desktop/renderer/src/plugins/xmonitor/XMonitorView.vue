<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { ArrowLeft, Pause, Play, Plus, RefreshCw, Settings2, Trash2 } from 'lucide-vue-next'
import type { XDeliveryStatus, XSnapshot } from '../../../../shared/xmonitor'
import { errorText } from '../../core/http'
import { usePageWindowState } from '../../core/page-window'
import { useWindowUpdates } from '../../core/window-updates'
import { xApi } from './api'
import { useXNoticeStore } from './notice-store'
import XFeed from './XFeed.vue'
import XConnectionSettings from './XConnectionSettings.vue'
import XDeliveryLog from './XDeliveryLog.vue'

const snapshot = shallowRef<XSnapshot>()
const selected = ref('')
const notices = useXNoticeStore()
const tab = ref<'all' | 'signals' | 'inbox'>('all')
const section = ref<'feed' | 'settings' | 'deliveries'>('feed')
const status = ref<'all' | XDeliveryStatus>('all')
const initial = usePageWindowState(
  () => {
    const state: Record<string, string> = { handle: selected.value, signals: tab.value === 'signals' ? '1' : '0' }
    if (tab.value === 'inbox') state.tab = 'inbox'
    if (section.value !== 'feed') state.section = section.value
    if (section.value === 'deliveries' && status.value !== 'all') state.status = status.value
    return state
  },
  () => section.value === 'settings' ? 'X 连接配置' : section.value === 'deliveries' ? 'Webhook 投递记录'
    : tab.value === 'inbox' ? 'X 提醒记录' : selected.value ? '@' + selected.value + ' · X 动态' : 'X 动态',
)
selected.value = initial.handle || ''
tab.value = initial.tab === 'inbox' ? 'inbox' : initial.signals === '1' ? 'signals' : 'all'
if (initial.section === 'settings' || initial.section === 'deliveries') section.value = initial.section
if (initial.status === 'failed' || initial.status === 'pending' || initial.status === 'sent') status.value = initial.status
watch(() => notices.inboxRequested, show => {
  if (show) {
    section.value = 'feed'
    tab.value = 'inbox'
    notices.inboxRequested = false
  }
}, { immediate: true })
const inboxError = ref('')
const readInbox = async () => {
  inboxError.value = ''
  try { await notices.getInbox() }
  catch (error) { inboxError.value = errorText(error, '无法读取提醒记录，请重试。') }
}
watch([tab, section], ([currentTab, currentSection]) => {
  notices.viewingInbox = currentSection === 'feed' && currentTab === 'inbox'
  if (notices.viewingInbox) void readInbox()
}, { immediate: true })
const markingAll = ref(false)
const readAll = async () => {
  if (markingAll.value) return
  markingAll.value = true
  inboxError.value = ''
  try { await notices.markAllRead() }
  catch (error) { inboxError.value = errorText(error, '已读状态未能保存，请重试。') }
  finally { markingAll.value = false }
}

const handles = computed(() => [...new Set([
  ...(snapshot.value?.accounts.map(account => account.handle) ?? []),
  ...(snapshot.value?.posts.map(post => post.handle) ?? []),
])].sort())
const posts = computed(() => snapshot.value?.posts.filter(post =>
  (!selected.value || post.handle === selected.value) && (tab.value !== 'signals' || post.signal)) ?? [])
const emptyText = computed(() => {
  if (tab.value === 'signals') return '暂无符合条件的交易线索'
  if (selected.value) return '@' + selected.value + ' 暂无已同步的动态'
  return snapshot.value?.accounts.length ? '暂无已同步的动态' : '添加博主后，在这里查看公开动态'
})
const stamp = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
})
const formatCheck = (iso: string | null) => {
  const value = Date.parse(iso ?? '')
  return Number.isFinite(value) ? '检查于 ' + stamp.format(value) : '待首次检查'
}
const busy = ref('')
const managing = ref(false)
const draft = ref('')
const formError = ref('')
const readError = ref('')
const operationError = ref('')
let requested = 0
let applied = 0
const apply = (next: XSnapshot, version: number) => {
  if (version < applied) return
  applied = version
  snapshot.value = next
  readError.value = ''
  if (selected.value && !handles.value.includes(selected.value)) selected.value = ''
}
const read = async () => {
  const version = ++requested
  try { apply(await xApi.getMonitor(), version) }
  catch (error) {
    if (version >= applied) readError.value = errorText(error, '无法读取本地动态，请重试。')
  }
}
const publish = useWindowUpdates('x-monitor', read)
const settingsChanged = () => {
  void read()
  publish('settings')
}
const change = async (key: string, action: () => Promise<XSnapshot>) => {
  if (busy.value) return false
  busy.value = key
  operationError.value = ''
  try {
    const next = await action()
    apply(next, ++requested)
    publish('snapshot')
    notices.invalidate()
    return true
  } catch (error) {
    operationError.value = errorText(error, '操作失败，请重试。')
    return false
  } finally { busy.value = '' }
}
const add = async () => {
  const handle = draft.value.trim().replace(/^@/, '').toLowerCase()
  if (!/^[a-z0-9_]{1,15}$/.test(handle)) {
    formError.value = '请输入 1 至 15 位字母、数字或下划线，可带 @。'
    return
  }
  if (snapshot.value?.accounts.some(account => account.handle.toLowerCase() === handle)) {
    formError.value = '已在监控列表中。'
    return
  }
  formError.value = ''
  if (await change('add', () => xApi.addAccount(handle))) draft.value = ''
}
const toggle = (handle: string, enabled: boolean) => change(handle, () => xApi.setAccountEnabled(handle, enabled))
const changeMode = async (handle: string, event: Event) => {
  const select = event.currentTarget as HTMLSelectElement
  const mode = select.value
  if (mode !== 'off' && mode !== 'orders' && mode !== 'all') return
  if (!await change(handle, () => xApi.setNoticeMode(handle, mode))) {
    select.value = snapshot.value?.accounts.find(account => account.handle === handle)?.noticeMode ?? 'off'
  }
}
const remove = (handle: string) => change(handle, () => xApi.removeAccount(handle))
const sync = () => change('refresh', () => xApi.refresh())
const syncing = computed(() => busy.value === 'refresh' || snapshot.value?.syncing)
const canSync = computed(() => snapshot.value?.configured && snapshot.value.accounts.some(account => account.enabled))
let timer: ReturnType<typeof setInterval> | undefined
const followVisibility = () => {
  clearInterval(timer)
  if (document.hidden) return
  if (section.value !== 'feed') return
  void read()
  timer = setInterval(() => { if (!busy.value) void read() }, 10_000)
}
watch(section, followVisibility)
onMounted(() => {
  document.addEventListener('visibilitychange', followVisibility)
  followVisibility()
})
onBeforeUnmount(() => {
  notices.viewingInbox = false
  clearInterval(timer)
  document.removeEventListener('visibilitychange', followVisibility)
})
</script>

<template>
  <section v-if="section !== 'feed'" class="x-monitor" aria-labelledby="connections-title">
    <button class="back" type="button" @click="section = 'feed'"><ArrowLeft :size="15" />返回 X 动态</button>
    <header class="heading"><h1 id="connections-title">连接与投递</h1></header>
    <nav class="tabs section-tabs" aria-label="连接与投递">
      <button type="button" :aria-pressed="section === 'settings'" @click="section = 'settings'">连接配置</button>
      <button type="button" :aria-pressed="section === 'deliveries'" @click="section = 'deliveries'">投递记录</button>
    </nav>
    <XConnectionSettings v-if="section === 'settings'" @saved="settingsChanged" />
    <XDeliveryLog v-else v-model:status="status" />
  </section>
  <section v-else class="x-monitor" aria-labelledby="x-monitor-title">
    <header class="heading">
      <div><h1 id="x-monitor-title">X 博主动态</h1><p>每 5 分钟同步已启用博主的公开帖子。</p></div>
      <div class="heading-actions">
        <button type="button" class="action" @click="section = 'settings'"><Settings2 :size="15" />连接与投递</button>
        <button type="button" class="action" :disabled="!canSync || !!busy || syncing" @click="sync">
          <RefreshCw :size="15" :class="{ spin: syncing }" />{{ syncing ? '同步中' : '立即同步' }}
        </button>
      </div>
    </header>
    <div v-if="readError || operationError" class="feedback" role="alert">
      {{ operationError || readError }}
      <button v-if="readError" type="button" @click="read">重新读取</button>
    </div>
    <div v-if="!snapshot" class="empty" role="status">{{ readError ? '本地动态暂不可用' : '正在读取本地动态' }}</div>
    <div v-else class="columns">
      <aside class="accounts panel" aria-labelledby="accounts-title" :class="{ folded: snapshot.accounts.length && !managing }">
        <div class="account-heading">
          <h2 id="accounts-title">监控博主 <small>{{ snapshot.accounts.length }}</small></h2>
          <button v-if="snapshot.accounts.length" class="manage" type="button" :aria-expanded="managing" aria-controls="x-accounts"
            @click="managing = !managing">{{ managing ? '收起' : '管理' }}</button>
        </div>
        <p v-if="!snapshot.configured" class="connection-warning">公开动态同步需要配置 X API。</p>
        <p v-else-if="snapshot.accounts.some(account => account.error)" class="connection-warning">部分博主同步异常，请查看账号状态。</p>
        <div id="x-accounts" class="account-body">
        <form @submit.prevent="add">
          <input v-model="draft" type="text" aria-label="X 用户名" placeholder="@用户名" autocomplete="off" autocapitalize="none"
            spellcheck="false" :aria-invalid="!!formError" :aria-describedby="formError ? 'handle-error' : undefined" @input="formError = ''" />
          <button type="submit" class="action primary" :disabled="!!busy"><Plus :size="14" />添加</button>
        </form>
        <p v-if="formError" id="handle-error" role="alert" class="invalid">{{ formError }}</p>
        <ul v-if="snapshot.accounts.length" class="accounts-list" aria-label="监控账号列表">
          <li v-for="account in snapshot.accounts" :key="account.handle">
            <div class="account-name">
              <strong>@{{ account.handle }}</strong>
              <span :title="account.lastCheckedAt || undefined">{{ account.enabled ? formatCheck(account.lastCheckedAt) : '已暂停' }}</span>
            </div>
            <button type="button" class="icon-button" :aria-label="(account.enabled ? '暂停 @' : '启用 @') + account.handle"
              :title="account.enabled ? '暂停' : '启用'" :disabled="!!busy" @click="toggle(account.handle, !account.enabled)">
              <component :is="account.enabled ? Pause : Play" :size="15" />
            </button>
            <button type="button" class="icon-button" :aria-label="'移除 @' + account.handle" title="移除监控，保留历史帖子"
              :disabled="!!busy" @click="remove(account.handle)"><Trash2 :size="15" /></button>
            <label class="notice-mode">应用内提醒
              <select :aria-label="'@' + account.handle + ' 的应用内提醒'" :value="account.noticeMode ?? 'off'"
                :disabled="!!busy" @change="changeMode(account.handle, $event)">
                <option value="off">关闭</option><option value="orders">只提醒下单</option><option value="all">提醒所有买卖</option>
              </select>
            </label>
            <p v-if="account.error" class="account-error">{{ account.error }}</p>
          </li>
        </ul>
        <p class="connection"><span class="indicator" :class="{ ready: snapshot.configured }"></span>{{ snapshot.configured ? 'X API 已配置' : '等待配置 X API' }}</p>
        </div>
      </aside>
      <section class="feed" aria-label="博主动态与提醒">
        <div class="filters">
          <div class="tabs" role="group" aria-label="动态视图">
            <button type="button" :aria-pressed="tab === 'all'" @click="tab = 'all'">全部动态</button>
            <button type="button" :aria-pressed="tab === 'signals'" @click="tab = 'signals'">交易线索</button>
            <button type="button" :aria-pressed="tab === 'inbox'" @click="tab = 'inbox'">提醒记录
              <span v-if="notices.unread" class="count" :aria-label="notices.unread + ' 条未读'">{{ notices.unread }}</span>
            </button>
          </div>
          <select v-if="tab !== 'inbox'" v-model="selected" aria-label="按博主筛选">
            <option value="">全部博主</option><option v-for="handle in handles" :key="handle" :value="handle">@{{ handle }}</option>
          </select>
        </div>
        <template v-if="tab === 'inbox'">
          <div v-if="inboxError" class="feedback" role="alert">{{ inboxError }} <button type="button" @click="readInbox">重新读取</button></div>
          <div v-if="notices.inbox?.items.length" class="inbox-tools">
            <span>{{ notices.inbox.unread ? notices.inbox.unread + ' 条未读' : '全部已读' }}</span>
            <button v-if="notices.inbox.unread" type="button" :disabled="markingAll" @click="readAll">全部标为已读</button>
          </div>
          <XFeed v-if="notices.inbox" :posts="notices.inbox.items" empty-text="暂无提醒记录" />
          <div v-else-if="!inboxError" class="empty" role="status">正在读取提醒记录</div>
        </template>
        <XFeed v-else :posts="posts" :empty-text="emptyText" />
      </section>
    </div>
  </section>
</template>

<style scoped lang="scss">
.x-monitor { min-width: 0; }
.heading-actions, .back { display: flex; align-items: center; gap: 8px; }
.back { margin: 0 0 15px; padding: 0; color: var(--muted); font-size: 13px; &:hover { color: var(--primary); } }
.section-tabs { border-bottom: 1px solid var(--line); margin-bottom: 24px; }
.heading { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; margin-bottom: 28px;
  h1 { font-size: clamp(30px, 3vw, 44px); font-weight: 550; letter-spacing: -.05em; }
  p { margin-top: 3px; color: var(--muted); font-size: 14px; } }
.columns { display: grid; grid-template-columns: minmax(0, 1fr) minmax(260px, 320px); gap: clamp(20px, 3.4vw, 52px); align-items: start; }
.feed { grid-column: 1; grid-row: 1; min-width: 0; }
.accounts { grid-column: 2; grid-row: 1; padding: 21px;
  form { display: flex; gap: 7px; margin-top: 15px; }
  input { width: 100%; min-width: 0; height: 37px; padding: 0 10px; border: 1px solid var(--line); border-radius: 9px; color: var(--text); font-size: 14px; }
  .primary { flex-shrink: 0; min-height: 37px; padding: 0 12px; }
}
.account-heading { display: flex; align-items: center; justify-content: space-between;
  small { margin-left: 3px; color: var(--dim); font-size: 13px; font-weight: 500; }
  .manage { display: none; color: var(--primary); font-size: 13px; }
}
.connection-warning { margin-top: 6px; font-size: 12px; color: var(--muted); }
.filters { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px;
  border-bottom: 1px solid var(--line);
  select { font: inherit; font-size: 13px; background: var(--surface); color: var(--muted); border-radius: 6px; max-width: 100%;
    border: 1px solid var(--line); padding: 4px 6px; margin-bottom: 7px; }
}
.tabs { display: flex; gap: 22px;
  button { margin-bottom: -1px; padding: 8px 0 14px; border-bottom: 2px solid transparent; font-weight: 550; color: var(--muted); }
  [aria-pressed=true] { color: var(--text); border-color: var(--primary); }
  .count { margin-left: 2px; padding: 1px 6px; border-radius: 12px; background: #edf3ff; color: var(--primary); font-size: 11px; }
}
.inbox-tools { display: flex; align-items: center; justify-content: space-between; margin-top: 12px; color: var(--muted); font-size: 12px;
  button { padding: 4px 0; color: var(--primary); } }
.accounts-list { list-style: none; padding: 0; margin: 14px 0 0;
  li { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; align-items: center; gap: 2px; padding: 10px 0; border-top: 1px solid var(--line-soft); }
  .icon-button { width: 30px; height: 32px; }
}
.account-name { display: grid; min-width: 0; gap: 2px; strong { font-size: 14px; font-weight: 550; overflow-wrap: anywhere; }
  span { color: var(--dim); font-size: 12px; }
}
.notice-mode { grid-column: 1 / -1; display: flex; align-items: center; gap: 8px; margin-top: 6px; color: var(--muted); font-size: 12px;
  select { padding: 3px 5px; border: 1px solid var(--line); border-radius: 6px; background: var(--surface); color: var(--text); font: inherit; } }
.account-error, .invalid { margin: 5px 0; font-size: 12px; color: var(--up); overflow-wrap: anywhere; }
.account-error { grid-column: 1 / -1; }
.connection { margin-top: 14px; padding-top: 12px; border-top: 1px solid var(--line-soft); font-size: 12px; color: var(--muted); }
.indicator { display: inline-block; width: 6px; height: 6px; margin: 0 5px 1px 1px; border-radius: 50%; background: var(--dim); }
.indicator.ready { background: #15825b; }
.feedback { margin-bottom: 15px; padding: 10px 12px; background: var(--soft); border-radius: 9px; color: var(--muted); font-size: 13px;
  button { color: var(--primary); } }
.spin { animation: rotate 1s linear infinite; } @keyframes rotate { to { transform: rotate(360deg); } }
@media (max-width: 760px) {
  .columns { display: flex; flex-direction: column; }
  .accounts, .feed { width: 100%; } .accounts { padding: 16px; }
  .account-heading .manage { display: block; }
  .accounts.folded .account-body { display: none; }
  .heading { margin-bottom: 18px; p { font-size: 13px; } }
}
</style>
