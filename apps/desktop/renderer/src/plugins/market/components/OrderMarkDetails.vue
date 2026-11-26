<script setup lang="ts">
import { computed } from 'vue'
import { ArrowDown, ArrowUp } from 'lucide-vue-next'
import type { OrderDay } from '../order-marker-series'

const props = defineProps<{ days: OrderDay[]; selected: string; adjustment?: string; showPrices: boolean }>()
const emit = defineEmits<{ select: [date: string] }>()
const dates = computed(() => props.days.slice().reverse())
const day = computed(() => props.days.find(item => item.date === props.selected))
const priceHint = computed(() => {
  if (!day.value?.orders.some(order => order.price != null)) return ''
  if (props.showPrices) return '圆点 · 披露委托价（元）'
  if (props.adjustment === '不复权') return '人民币委托价可标在价格轴上'
  return (props.adjustment || '复权口径未知') + '行情，原始委托价见明细'
})
const time = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai', hourCycle: 'h23', hour: '2-digit', minute: '2-digit', second: '2-digit',
})
const number = new Intl.NumberFormat('zh-CN', { maximumSignificantDigits: 15 })
const selectDate = (event: Event) => emit('select', (event.target as HTMLSelectElement).value)
</script>

<template>
  <section class="marks" aria-label="博主下单标记详情">
    <div class="legend">
      <span class="buy"><ArrowUp :size="13" aria-hidden="true" />买单</span>
      <span class="sell"><ArrowDown :size="13" aria-hidden="true" />卖单</span>
      <span class="basis">按上海发帖日期标记</span>
      <span v-if="showPrices" class="price-key">{{ priceHint }}</span>
      <select :value="selected" aria-label="选择标记日期查看委托" @change="selectDate">
        <option value="">选择标记日期</option>
        <option v-for="item in dates" :key="item.date" :value="item.date">{{ item.date }} · {{ item.orders.length }} 条</option>
      </select>
    </div>
    <p v-if="priceHint && !showPrices" class="price-note">{{ priceHint }}</p>
    <ul v-if="day" class="orders" :aria-label="day.date + ' 的博主委托'">
      <li v-for="order in day.orders" :key="order.id">
        <strong :class="order.action">{{ order.action === 'buy' ? '买单' : '卖单' }}</strong>
        <b>@{{ order.handle }}</b>
        <time :datetime="order.publishedAt">{{ time.format(Date.parse(order.publishedAt)) }} 发帖</time>
        <span v-if="order.orderType">{{ order.orderType === 'limit' ? '限价委托' : '市价委托' }}</span>
        <span>{{ order.price == null ? '委托价未披露' : '委托价 ' + number.format(order.price) + (order.priceInYuan ? ' 元' : '') }}</span>
        <span v-if="order.quantity != null">数量 {{ number.format(order.quantity) }}</span>
      </li>
    </ul>
  </section>
</template>

<style scoped lang="scss">
.marks { padding: 9px 0 2px; border-top: 1px solid var(--line-soft); color: var(--muted); font-size: 12px; }
.legend { display: flex; align-items: center; flex-wrap: wrap; gap: 6px 12px; }
.legend > span { display: inline-flex; align-items: center; gap: 3px; }
.buy { color: var(--up); }
.sell { color: var(--down); }
.price-note { margin: 5px 0 0; }
select { max-width: 100%; margin-left: auto; padding: 4px 7px; border: 1px solid var(--line); border-radius: 5px; background: var(--surface); color: var(--text); font: inherit; }
.orders { max-height: 10rem; overflow-y: auto; list-style: none; margin: 6px 0 0; padding: 0; font-variant-numeric: tabular-nums; }
li { display: flex; align-items: baseline; flex-wrap: wrap; gap: 3px 12px; padding: 7px 0; }
li + li { border-top: 1px solid var(--line-soft); }
b { color: var(--text); overflow-wrap: anywhere; }
b, strong { font-weight: 600; }
@container (max-width: 400px) {
  .legend { gap: 5px 8px; }
  select { margin-left: 0; }
}
</style>
