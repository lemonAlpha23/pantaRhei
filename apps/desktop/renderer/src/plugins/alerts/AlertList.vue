<script setup lang="ts">
import { computed } from 'vue'
import { Bell, History, Pause, Play, Trash2 } from 'lucide-vue-next'
import type { AlertDirection, AlertSnapshot } from '../../../../shared/alerts'
import { number } from '../market/format'
import { useMarketNavigation } from '../market/navigation'
import { useWorkspace } from '../market/store'

defineProps<{ snapshot: AlertSnapshot; tab: 'rules' | 'history'; busy: boolean }>()
const emit = defineEmits<{ toggle: [id: number, enabled: boolean]; remove: [id: number] }>()
const market = useWorkspace()
const { openStock } = useMarketNavigation()
const names = computed(() => new Map(market.instruments.map(stock => [stock.symbol, stock.name])))
const condition = (direction: AlertDirection) => direction === 'above' ? '达到或高于' : '达到或低于'
const format = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai', hourCycle: 'h23', year: 'numeric', month: '2-digit',
  day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit',
})
const time = (value: string) => {
  const stamp = Date.parse(value)
  return Number.isFinite(stamp) ? format.format(stamp) : '—'
}
</script>

<template>
  <template v-if="tab === 'rules'">
    <ul v-if="snapshot.rules.length" class="rules" aria-label="提醒规则列表">
      <li v-for="rule in snapshot.rules" :key="rule.id">
        <div class="rule-name">
          <button class="stock" type="button" :aria-label="'查看 ' + rule.symbol + ' 行情'" @click="openStock(rule.symbol)">
            {{ names.get(rule.symbol) || rule.symbol }}
          </button>
          <small v-if="names.has(rule.symbol)">{{ rule.symbol }}</small>
        </div>
        <div class="condition"><strong>{{ number(rule.target) }} <small>元</small></strong><small>{{ condition(rule.direction) }}</small></div>
        <span class="state" :class="{ enabled: rule.enabled }">{{ rule.enabled ? '已启用' : '已停用' }}</span>
        <div class="controls">
          <button type="button" class="toggle" :disabled="busy" @click="emit('toggle', rule.id, !rule.enabled)">
            <component :is="rule.enabled ? Pause : Play" :size="13" />{{ rule.enabled ? '暂停' : '启用' }}
          </button>
          <button type="button" class="icon-button remove" :disabled="busy" aria-label="删除" title="删除提醒" @click="emit('remove', rule.id)">
            <Trash2 :size="15" />
          </button>
        </div>
      </li>
    </ul>
    <div v-else class="empty empty-list"><Bell :size="24" /><strong>暂无提醒规则</strong></div>
  </template>

  <ul v-else-if="snapshot.events.length" class="history" aria-label="触发记录列表">
    <li v-for="event in snapshot.events" :key="event.id">
      <div class="event-stock">
        <button type="button" class="stock" :aria-label="'查看 ' + event.symbol + ' 行情'" @click="openStock(event.symbol)">
          {{ names.get(event.symbol) || event.symbol }}
        </button>
        <small>{{ event.symbol }} · {{ condition(event.direction) }} {{ number(event.target) }} 元</small>
      </div>
      <div class="event-price"><strong>{{ number(event.price) }} <small>元</small></strong><small>触发价</small></div>
      <div class="event-time"><time :datetime="event.quotedAt">{{ time(event.quotedAt) }}</time><small>报价时间 · 上海</small></div>
    </li>
  </ul>
  <div v-else class="empty empty-list"><History :size="24" /><strong>暂无触发记录</strong></div>
</template>

<style scoped lang="scss">
ul { list-style: none; margin: 0; padding: 0; }
li { display: grid; align-items: center; gap: 12px; padding: 16px 0; border-bottom: 1px solid var(--line-soft); font-variant-numeric: tabular-nums; }
.rules li { grid-template-columns: minmax(0, 1fr) minmax(85px, .9fr) minmax(64px, .55fr) auto; }
.stock { padding: 0; text-align: left; font-size: 16px; font-weight: 550; overflow-wrap: anywhere;
  &:hover { color: var(--primary); } }
small { display: block; color: var(--muted); font-size: 12px; font-weight: 400; }
strong { font-size: 16px; font-weight: 550; small { display: inline; } }
.state { display: flex; align-items: center; gap: 6px; white-space: nowrap; color: var(--muted); font-size: 12px;
  &::before { content: ''; width: 6px; height: 6px; border-radius: 50%; background: var(--dim); }
  &.enabled::before { background: #15825b; } }
.controls { display: flex; align-items: center; gap: 5px; }
.toggle { display: inline-flex; align-items: center; justify-content: center; gap: 4px;
  min-height: 32px; padding: 0 10px; border-radius: 18px; background: var(--soft); font-size: 12px;
  &:hover:not(:disabled) { background: var(--line-soft); } }
.remove { width: 32px; height: 32px; &:hover:not(:disabled) { color: var(--up); } }
.history li { grid-template-columns: minmax(0, 1.2fr) minmax(0, .8fr) auto; }
.event-time { text-align: right; time { font-size: 13px; } }
.empty-list { min-height: 215px; }
@media (max-width: 540px) {
  .rules li { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto; gap: 8px; }
  .state { grid-column: 1; grid-row: 2; }
  .controls { grid-column: 3; grid-row: 1 / 3; flex-wrap: wrap; }
  .history li { grid-template-columns: minmax(0, 1fr) auto; gap: 5px 10px; }
  .event-price { text-align: right; }
  .event-time { grid-column: 1 / -1; display: flex; align-items: baseline; gap: 5px; color: var(--muted); time, small { font-size: 11px; } }
  .empty-list { min-height: 150px; }
}
</style>
