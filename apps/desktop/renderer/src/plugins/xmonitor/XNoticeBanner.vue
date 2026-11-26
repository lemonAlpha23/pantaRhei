<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ArrowUpRight, Bell, X } from 'lucide-vue-next'
import { useWorkbench } from '../../core/workbench'
import { errorText } from '../../core/http'
import { useXNoticeStore } from './notice-store'

const notices = useXNoticeStore()
const { navigate } = useWorkbench()
const dismissedThrough = ref(0n)
const latest = computed(() => {
  const item = notices.latest
  return item && !notices.viewingInbox && BigInt(item.id) > dismissedThrough.value ? item : undefined
})
const opening = ref(false)
const error = ref('')
watch(() => latest.value?.id, () => { error.value = '' })
const openPost = async () => {
  const item = latest.value
  if (!item || opening.value) return
  opening.value = true
  error.value = ''
  try { await notices.openOriginal(item) }
  catch (cause) { error.value = errorText(cause, '原帖打开失败，请重试。') }
  finally { opening.value = false }
}
const openInbox = () => {
  notices.inboxRequested = true
  navigate('x-monitor')
}
const dismiss = () => {
  if (latest.value) dismissedThrough.value = BigInt(latest.value.id)
}
let timer: ReturnType<typeof setInterval> | undefined
const read = () => { void notices.poll().catch(() => {}) }
const followVisibility = () => {
  clearInterval(timer)
  if (document.hidden) return
  read()
  timer = setInterval(read, 10_000)
}
onMounted(() => {
  document.addEventListener('visibilitychange', followVisibility)
  followVisibility()
})
onBeforeUnmount(() => {
  clearInterval(timer)
  document.removeEventListener('visibilitychange', followVisibility)
})
</script>

<template>
  <aside v-if="latest" class="x-notice" aria-label="X 交易线索提醒">
    <Bell :size="17" class="bell" aria-hidden="true" />
    <div class="message" role="status">
      <strong>{{ notices.unread }} 条 X 交易线索未读</strong>
      <span>@{{ latest.handle }} {{ latest.signal.kind === 'order' ? '自述下单' : '自述交易' }} ·
        {{ latest.signal.action === 'buy' ? '买入' : '卖出' }} {{ latest.signal.symbol }}</span>
    </div>
    <div class="actions">
      <button type="button" class="original" :disabled="opening" @click="openPost">查看原帖 <ArrowUpRight :size="13" /></button>
      <button type="button" @click="openInbox">提醒记录</button>
      <button type="button" class="dismiss" aria-label="收起 X 交易线索提醒" @click="dismiss"><X :size="15" /></button>
    </div>
    <span v-if="error" class="error" role="alert">{{ error }}</span>
  </aside>
</template>

<style scoped lang="scss">
.x-notice {
  display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center;
  gap: 8px 12px; padding: 11px 14px; margin-bottom: 20px; border: 1px solid var(--line);
  border-radius: 12px; background: var(--surface); color: var(--text); font-size: 13px;
}
.bell, .original { color: var(--primary); }
.message { display: flex; flex-wrap: wrap; align-items: baseline; gap: 2px 12px; overflow-wrap: anywhere; }
.message strong { font-weight: 620; }
.message span, .dismiss { color: var(--muted); }
.actions { display: flex; align-items: center; gap: 12px; white-space: nowrap; }
button { display: inline-flex; align-items: center; gap: 3px; padding: 4px 0; }
button:hover { color: var(--primary); }
.dismiss { padding: 5px; }
.error { grid-column: 2 / -1; color: var(--muted); }
@media (max-width: 600px) {
  .x-notice { grid-template-columns: auto minmax(0, 1fr); align-items: start; gap: 3px 9px; }
  .bell { margin-top: 2px; }
  .actions { grid-column: 2; }
}
</style>
