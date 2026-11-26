<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ChevronLeft, ChevronRight } from 'lucide-vue-next'
import type { Bar } from '../api'
import { direction, number, signed, volume } from '../format'

const props = defineProps<{ bars: Bar[] }>()
const page = ref(0)
const perPage = 5
const ordered = computed(() => props.bars.map((bar, i, all) => ({
  ...bar, change: i > 0 && all[i - 1].close ? (bar.close / all[i - 1].close - 1) * 100 : undefined,
})).reverse())
const pages = computed(() => Math.ceil(ordered.value.length / perPage))
const rows = computed(() => ordered.value.slice(page.value * perPage, (page.value + 1) * perPage))
watch(() => props.bars, () => { page.value = 0 })
</script>

<template>
  <section class="history-table">
    <header class="history-heading">
      <h2>历史行情</h2><span class="history-total">{{ bars.length }} 个交易日</span>
      <div class="pagination">
        <button :disabled="page === 0" aria-label="上一页行情" @click="page--"><ChevronLeft :size="15" /></button>
        <span>{{ page + 1 }} / {{ pages }}</span>
        <button :disabled="page + 1 >= pages" aria-label="下一页行情" @click="page++"><ChevronRight :size="15" /></button>
      </div>
    </header>
    <div class="scroll-table">
      <table aria-label="每日历史行情"><thead><tr><th scope="col">交易日期</th><th scope="col">开盘</th><th scope="col">最高</th><th scope="col">最低</th><th scope="col">收盘</th><th scope="col" title="相邻交易日收盘价变化，不复权数据受除权除息影响">收盘变动</th><th scope="col">成交量</th></tr></thead>
        <tbody><tr v-for="bar in rows" :key="bar.time"><td>{{ bar.time }}</td><td>{{ number(bar.open) }}</td><td>{{ number(bar.high) }}</td>
          <td>{{ number(bar.low) }}</td><td>{{ number(bar.close) }}</td><td :class="direction(bar.change)">{{ bar.change !== undefined ? signed(bar.change) + '%' : '—' }}</td><td>{{ volume(bar.volume) }}</td></tr></tbody>
      </table>
    </div>
  </section>
</template>

<style scoped lang="scss">
.history-table {
  min-width: 0;
  border-top: 1px solid var(--line);
  padding-top: 20px;
  background: var(--surface, #fff);
  font-variant-numeric: tabular-nums;
}

.history-heading {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 13px;

  h2 {
    margin: 0;
    color: var(--text);
    font-size: 18px;
    font-weight: 600;
    letter-spacing: -.025em;
  }
}

.history-total {
  color: var(--muted);
  font-size: 12px;
}

.pagination {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
  color: var(--muted);
  font-size: 12px;

  button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    padding: 0;
    border-radius: 50%;
    color: var(--text);
    background: var(--soft);

    &:disabled {
      color: var(--dim);
      opacity: .45;
      cursor: default;
    }
    &:hover:not(:disabled) { background: var(--line-soft); }
  }
}

.scroll-table { overflow-x: auto; }

table {
  width: 100%;
  border-collapse: collapse;
  white-space: nowrap;
}

td, th {
  padding: 11px 9px;
  border-bottom: 1px solid var(--line-soft);
  text-align: right;
  vertical-align: middle;

  &:first-child { text-align: left; padding-left: 0; }
  &:last-child { padding-right: 0; }
}

th {
  padding-block: 7px 10px;
  color: var(--muted);
  font-size: 12px;
  font-weight: 450;
}

td {
  color: var(--text);
  font-size: 13px;
  &:nth-child(5) { font-weight: 550; }
}

tbody tr:last-child td { border-bottom: 0; }

@media (max-width: 600px) {
  .history-table { padding-top: 15px; }
  .history-heading { gap: 6px; }
  .history-heading h2 { font-size: 17px; }
  .pagination { gap: 5px; }
  th, td { padding-inline: 8px; }
  td { font-size: 12px; }
}
</style>
