<script setup lang="ts">
import { computed } from 'vue'
import { ArrowDownRight, ArrowUpRight, Minus, RefreshCw, Star } from 'lucide-vue-next'
import { direction, exchangeTag, number, percent, signed } from '../format'
import { useWorkspace } from '../store'
import StockAvatar from './StockAvatar.vue'

const store = useWorkspace()
const isFavorite = computed(() => store.watchlist.includes(store.selected))
const directionIcon = computed(() => {
  const change = store.current?.change ?? 0
  return change > 0 ? ArrowUpRight : change < 0 ? ArrowDownRight : Minus
})
</script>

<template>
  <section v-if="store.current" class="quote" aria-label="股票收盘行情">
    <div class="identity-row">
      <div class="identity">
        <StockAvatar :name="store.current.name" :symbol="store.current.symbol" :sector="store.current.sector" :size="52" />
        <div>
          <h1>{{ store.current.name }}</h1>
          <div class="asset-meta">
            <span>{{ exchangeTag(store.current.exchange) }} {{ store.current.symbol }}</span>
            <span>{{ store.current.sector }}</span>
          </div>
        </div>
      </div>
      <div class="quote-actions">
        <button class="action favorite" :aria-pressed="isFavorite" :disabled="store.saving"
          :title="isFavorite ? '移出自选' : '加入自选'" @click="store.toggleFavorite(store.selected)">
          <Star :size="16" :fill="isFavorite ? 'currentColor' : 'none'" />
          <span>{{ isFavorite ? '已自选' : '加自选' }}</span>
        </button>
        <button class="action primary refresh" aria-label="联网更新日线" title="联网更新日线"
          :disabled="store.refreshing || store.loading" @click="store.refresh">
          <RefreshCw :size="15" :class="{ spinning: store.refreshing }" />
          <span>{{ store.refreshing ? '更新中' : '更新行情' }}</span>
        </button>
      </div>
    </div>
    <div class="price-row">
      <strong>{{ number(store.current.close) }}</strong>
      <span>{{ store.current.currency }}</span>
    </div>
    <div class="quote-caption">
      <span class="delta" :class="direction(store.current.change)" title="相邻交易日收盘价变化，不复权数据受除权除息影响">
        <component :is="directionIcon" :size="17" />{{ signed(store.current.change) }}
        <span v-if="store.current.changePercent != null">({{ percent(store.current.changePercent) }})</span>
      </span>
      <span class="as-of"><time :datetime="store.current.asOf">{{ store.current.asOf }}</time> 收盘</span>
    </div>
  </section>
</template>

<style scoped lang="scss">
.quote { min-width: 0; }
.identity-row, .identity, .quote-actions, .asset-meta, .price-row, .quote-caption, .delta {
  display: flex;
  align-items: center;
}
.identity-row { justify-content: space-between; gap: 16px; }
.identity { min-width: 0; gap: 13px; }
h1 { font-size: clamp(25px, 2.2vw, 34px); font-weight: 600; letter-spacing: -.045em; line-height: 1.2; }
.asset-meta {
  gap: 9px; margin-top: 5px; color: var(--muted); font-size: 13px;
  span + span::before { content: '·'; margin-right: 9px; color: var(--dim); }
}
.quote-actions { gap: 8px; flex-shrink: 0; }
.favorite { background: white; border: 1px solid var(--line); }
.favorite[aria-pressed="true"] svg { color: var(--primary); }
.price-row {
  align-items: baseline; gap: 10px; margin-top: 20px; font-variant-numeric: tabular-nums;
  strong { font-size: clamp(44px, 4.3vw, 66px); font-weight: 500; line-height: 1.1; letter-spacing: -.065em; }
  > span { color: var(--muted); font-size: 17px; font-weight: 500; }
}
.quote-caption { flex-wrap: wrap; gap: 13px; margin-top: 8px; font-variant-numeric: tabular-nums; }
.delta { gap: 4px; font-size: 15px; font-weight: 600; }
.as-of { border-left: 1px solid var(--line); padding-left: 13px; font-size: 13px; color: var(--muted); }
.spinning { animation: rotate 1s linear infinite; }
@keyframes rotate { to { transform: rotate(360deg); } }
@media (max-width: 620px) {
  .identity { gap: 9px; }
  .quote-actions { gap: 4px; }
  .favorite, .refresh { min-height: 35px; padding-inline: 10px; font-size: 12px; }
  .favorite span { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }
  .price-row { margin-top: 18px; }
}
</style>
