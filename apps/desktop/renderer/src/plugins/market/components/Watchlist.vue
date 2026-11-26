<script setup lang="ts">
import { computed } from 'vue'
import { ArrowDownUp, ListPlus, Plus, Trash2 } from 'lucide-vue-next'
import { direction, exchangeTag, number, percent } from '../format'
import { useWorkspace } from '../store'
import StockAvatar from './StockAvatar.vue'

const props = defineProps<{ full?: boolean }>()
const emit = defineEmits<{ select: [symbol: string]; search: [] }>()
const store = useWorkspace()
const sort = defineModel<'default' | 'desc' | 'asc'>('sort', { default: 'default' })
const rows = computed(() => {
  if (!props.full || sort.value === 'default') return store.favorites
  return [...store.favorites].sort((a, b) => {
    if (a.changePercent == null) return b.changePercent == null ? 0 : 1
    if (b.changePercent == null) return -1
    return (a.changePercent - b.changePercent) * (sort.value === 'asc' ? 1 : -1)
  })
})
const changeHint = '相邻交易日收盘价变化，不复权数据受除权除息影响'
</script>

<template>
  <section class="panel watch-panel" :class="{ 'full-watch': full, compact: !full }">
    <header v-if="!full" class="watch-heading">
      <h2>我的自选</h2>
      <span class="count">{{ rows.length }} 只</span>
      <button class="add-button" title="搜索并添加股票" aria-label="搜索并添加股票" @click="emit('search')">
        <Plus :size="17" />
      </button>
    </header>

    <div v-if="rows.length" class="watch-table-wrap">
      <table class="watch-table" :aria-label="full ? '全部自选行情' : '我的自选行情'">
        <thead :class="{ 'sr-only': !full }">
          <tr>
            <th scope="col">股票名称</th>
            <th v-if="full" scope="col" class="secondary-col">行业</th>
            <th scope="col">{{ full ? '收盘价' : '收盘价及涨跌幅' }}</th>
            <th v-if="full" scope="col" :aria-sort="sort === 'desc' ? 'descending' : sort === 'asc' ? 'ascending' : 'none'" :title="changeHint">
              <button class="sort-button" @click="sort = sort === 'desc' ? 'asc' : 'desc'">收盘变动 <ArrowDownUp :size="12" /></button>
            </th>
            <th v-if="full" scope="col" class="secondary-col">数据日期</th>
            <th v-if="full" scope="col" class="row-action"><span class="sr-only">操作</span></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in rows" :key="item.symbol" :class="{ selected: !full && item.symbol === store.selected }"
            @click="emit('select', item.symbol)">
            <td class="identity-cell">
              <button class="asset" :aria-label="'查看' + item.name + '行情'"
                :aria-current="!full && item.symbol === store.selected ? 'true' : undefined" @click.stop="emit('select', item.symbol)">
                <StockAvatar :symbol="item.symbol" :name="item.name" :sector="item.sector" :size="full ? 38 : 34" />
                <span class="asset-copy">
                  <strong>{{ item.name }}</strong>
                  <small>{{ exchangeTag(item.exchange) }} · {{ item.symbol }}</small>
                </span>
              </button>
            </td>
            <td v-if="full" class="secondary-col">{{ item.sector }}</td>
            <td class="price-cell">
              <span class="price">{{ number(item.close) }}</span>
              <span v-if="!full" class="change" :class="direction(item.changePercent)" :title="changeHint">{{ percent(item.changePercent) }}</span>
            </td>
            <td v-if="full" :title="changeHint"><span class="change" :class="direction(item.changePercent)">{{ percent(item.changePercent) }}</span></td>
            <td v-if="full" class="date secondary-col">{{ item.asOf }}</td>
            <td v-if="full" class="row-action">
              <button class="remove" :aria-label="'移出自选：' + item.name" :disabled="store.saving" title="移出自选"
                @click.stop="store.toggleFavorite(item.symbol)"><Trash2 :size="16" /></button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-else class="empty watch-empty">
      <ListPlus :size="25" /><strong>自选列表为空</strong>
      <button class="text-action" @click="emit('search')">搜索股票</button>
    </div>
  </section>
</template>

<style scoped lang="scss">
.watch-panel {
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
}

.full-watch .watch-table th { border-top: 0; }

.watch-heading {
  display: flex;
  align-items: center;
  gap: 9px;
  min-height: 62px;
  padding: 0 20px;

  h2 {
    font-size: 17px;
    font-weight: 600;
    letter-spacing: -.025em;
  }
}

.count {
  color: var(--dim);
  font-size: 12px;
}

.add-button,
.remove {
  display: inline-grid;
  place-items: center;
  padding: 0;
  border-radius: 50%;
}

.add-button {
  width: 30px;
  height: 30px;
  margin-inline-start: auto;
  color: var(--text);
  background: var(--soft);

  &:hover { color: var(--primary); background: var(--primary-soft); }
}

.watch-table-wrap {
  min-width: 0;
  max-width: 100%;
  overflow-x: auto;
}

.watch-table {
  width: 100%;
  border-collapse: collapse;
  text-align: right;
  font-size: 14px;

  th, td {
    padding: 13px 12px;
    white-space: nowrap;
  }

  th:first-child, td:first-child {
    padding-left: 20px;
    text-align: left;
  }

  th:last-child, td:last-child { padding-right: 20px; }
  th {
    color: var(--muted);
    font-size: 12px;
    font-weight: 500;
    border-block: 1px solid var(--line-soft);
  }

  tbody tr {
    cursor: pointer;
    &:hover { background: var(--soft); }
    &.selected { background: var(--primary-soft); }
  }

  tbody tr + tr td { border-top: 1px solid var(--line-soft); }
}

.asset {
  display: inline-flex;
  align-items: center;
  gap: 11px;
  max-width: 100%;
  padding: 0;
  text-align: left;
  vertical-align: middle;
}

.asset-copy {
  display: grid;
  min-width: 0;
  gap: 3px;
  line-height: 1.3;

  strong {
    overflow: hidden;
    text-overflow: ellipsis;
    font-size: 14px;
    font-weight: 600;
    color: var(--text);
  }

  small {
    font-size: 11px;
    color: var(--muted);
    font-variant-numeric: tabular-nums;
  }
}

.price, .change, .date { font-variant-numeric: tabular-nums; }
.price { color: var(--text); font-weight: 600; }
.change { font-weight: 500; }
.date, .secondary-col { color: var(--muted); }

.compact {
  .watch-table { table-layout: fixed; }
  .identity-cell { width: 64%; }
  .price-cell { width: 36%; }
  .change { display: block; margin-top: 2px; font-size: 12px; }
  td { padding-block: 11px; }
}

.sort-button {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 0;
  color: var(--muted);
  &:hover { color: var(--primary); }
}

.row-action { width: 1%; }
.remove {
  width: 30px;
  height: 30px;
  color: var(--dim);

  &:hover:not(:disabled) { color: var(--up); background: var(--soft); }
}

.watch-empty { min-height: 160px; }
.text-action { color: var(--primary); font-weight: 600; }

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  overflow: hidden;
  clip-path: inset(50%);
}

@media (max-width: 720px) {
  .full-watch {
    .secondary-col { display: none; }
    th, td { padding-inline: 7px; }
    th:first-child, td:first-child { padding-left: 12px; }
    th:last-child, td:last-child { padding-right: 10px; }
    .asset { gap: 7px; }
    .change, .price { font-size: 13px; }
  }
}

@media (max-width: 400px) {
  .full-watch {
    .asset :deep(.stock-avatar) { display: none; }
    th, td { padding-inline: 5px; }
  }
}
</style>
