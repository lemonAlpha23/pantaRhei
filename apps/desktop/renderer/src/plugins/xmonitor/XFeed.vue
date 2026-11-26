<script setup lang="ts">
import { ref } from 'vue'
import { ArrowUpRight, MessageSquare } from 'lucide-vue-next'
import type { XInbox, XSnapshot } from '../../../../shared/xmonitor'
import { errorText } from '../../core/http'
import { xApi } from './api'
import { useXNoticeStore } from './notice-store'

type Post = XSnapshot['posts'][number] | XInbox['items'][number]
defineProps<{ posts: Post[]; emptyText: string }>()
const notices = useXNoticeStore()
const pending = ref('')
const failure = ref<{ id: string; text: string }>()
const expanded = ref(new Set<string>())
const deliveryLabel = { pending: '待转发', sent: '已转发', failed: '转发失败' }
const number = new Intl.NumberFormat('zh-CN', { maximumSignificantDigits: 15 })
const dateTime = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai', hourCycle: 'h23', year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit',
})
const formatTime = (iso: string) => {
  const time = Date.parse(iso)
  return Number.isFinite(time) ? dateTime.format(time) : '时间未知'
}
const act = async (post: Post, openOriginal: boolean) => {
  if (pending.value) return
  pending.value = post.id
  failure.value = undefined
  try {
    if (!openOriginal) await notices.markRead(post.id)
    else if ('read' in post) await notices.openOriginal(post)
    else await xApi.openPost(post.handle, post.id)
  }
  catch (error) { failure.value = { id: post.id, text: errorText(error, '操作未完成，请重试。') } }
  finally { pending.value = '' }
}
</script>

<template>
  <ul v-if="posts.length" class="timeline" aria-label="博主动态">
    <li v-for="post in posts" :key="post.id">
      <article>
        <header>
          <span v-if="'read' in post" class="read-state" :class="{ unread: !post.read }">{{ post.read ? '已读' : '未读' }}</span>
          <strong>@{{ post.handle }}</strong>
          <time :datetime="post.publishedAt" title="上海时间">{{ formatTime(post.publishedAt) }}</time>
          <button type="button" class="source" :aria-label="'查看 @' + post.handle + ' 的原帖'" :disabled="!!pending" @click="act(post, true)">
            原帖 <ArrowUpRight :size="14" aria-hidden="true" />
          </button>
        </header>
        <p class="body" :class="{ excerpt: post.text.length > 360 && !expanded.has(post.id) }">{{ post.text }}</p>
        <button v-if="post.text.length > 360" type="button" class="expand" :aria-expanded="expanded.has(post.id)"
          @click="expanded.has(post.id) ? expanded.delete(post.id) : expanded.add(post.id)">{{ expanded.has(post.id) ? '收起全文' : '展开全文' }}</button>
        <div v-if="post.signal" class="signal">
          <span class="signal-label">{{ post.signal.kind === 'order' ? '博主自述下单' : '博主自述' }}</span>
          <strong>{{ post.signal.action === 'buy' ? '买入' : '卖出' }} {{ post.signal.symbol }}</strong>
          <span v-if="post.signal.kind === 'order' && post.signal.orderType">{{ post.signal.orderType === 'limit' ? '限价委托' : '市价委托' }}</span>
          <span v-if="post.signal.price != null">{{ post.signal.kind === 'order' ? '委托价' : '价格' }} {{ number.format(post.signal.price) }}</span>
          <span v-if="post.signal.quantity != null">数量 {{ number.format(post.signal.quantity) }}</span>
          <span v-if="'delivery' in post && post.delivery" class="delivery" :class="{ failed: post.delivery === 'failed' }">{{ deliveryLabel[post.delivery] }}</span>
        </div>
        <button v-if="'read' in post && !post.read" type="button" class="read-button" :disabled="!!pending" @click="act(post, false)">标为已读</button>
        <p v-if="failure?.id === post.id" class="error" role="alert">{{ failure.text }}</p>
      </article>
    </li>
  </ul>
  <div v-else class="empty feed-empty"><MessageSquare :size="23" aria-hidden="true" /><strong>{{ emptyText }}</strong></div>
</template>

<style scoped lang="scss">
.timeline { list-style: none; margin: 0; padding: 0; }
li { padding: 19px 0 21px; border-bottom: 1px solid var(--line-soft); }
header { display: flex; align-items: baseline; flex-wrap: wrap; gap: 4px 12px;
  strong { font-size: 15px; font-weight: 600; overflow-wrap: anywhere; }
  time { color: var(--dim); font-size: 12px; font-variant-numeric: tabular-nums; }
}
.source { display: inline-flex; align-items: center; gap: 3px; padding: 2px; margin-left: auto; color: var(--muted); font-size: 12px;
  &:hover { color: var(--primary); } }
.read-state { color: var(--dim); font-size: 11px; }
.read-state.unread { display: inline-flex; align-items: center; gap: 4px; color: var(--primary);
  &::before { content: ''; width: 5px; height: 5px; border-radius: 50%; background: currentColor; } }
.read-button { padding: 2px 0; margin-top: 8px; color: var(--muted); font-size: 12px;
  &:hover { color: var(--primary); } }
.body { margin-top: 8px; line-height: 1.7; white-space: pre-wrap; overflow-wrap: anywhere; }
.excerpt { display: -webkit-box; -webkit-line-clamp: 5; -webkit-box-orient: vertical; overflow: hidden; }
.expand { padding: 0; margin-top: 5px; font-size: 13px; color: var(--primary); }
.signal { display: flex; flex-wrap: wrap; align-items: baseline; gap: 3px 14px; margin-top: 12px; padding-left: 10px;
  border-left: 2px solid #9bb8ff; font-size: 13px; color: var(--muted); font-variant-numeric: tabular-nums;
  strong { color: var(--text); font-weight: 600; overflow-wrap: anywhere; }
  .signal-label, .delivery { font-size: 12px; }
  .failed { color: var(--up); }
}
.error { margin-top: 8px; color: var(--up); font-size: 13px; }
.feed-empty { min-height: 220px; }
@media (max-width: 600px) {
  li { padding: 16px 0; }
  header { gap: 3px 8px; }
  .signal { gap: 4px 10px; }
  .feed-empty { min-height: 150px; }
}
</style>
