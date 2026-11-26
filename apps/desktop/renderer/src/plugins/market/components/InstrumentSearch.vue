<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { NButton } from 'naive-ui'
import StockAvatar from './StockAvatar.vue'
import { CornerDownLeft, Search, Star, X } from 'lucide-vue-next'
import { useWorkspace } from '../store'
import { direction, exchangeTag, percent } from '../format'
import { errorText } from '../api'

const props = defineProps<{ show: boolean; manageFavorites: boolean }>()
const emit = defineEmits<{ close: []; select: [symbol: string] }>()
const store = useWorkspace()
const query = ref('')
const active = ref(0)
const input = ref<HTMLInputElement>()
const dialog = ref<HTMLDialogElement>()
const results = ref<HTMLDivElement>()
const importing = ref(false)
const importError = ref('')
let searchVersion = 0
const filtered = computed(() => {
  const term = query.value.trim().toLowerCase()
  return store.instruments.filter(item =>
    [item.symbol, item.name, item.sector].some(value => value?.toLowerCase().includes(term)),
  )
})

watch(() => props.show, async show => {
  searchVersion++
  if (show) {
    query.value = ''
    active.value = 0
    await nextTick()
    if (!props.show || !dialog.value) return
    if (!dialog.value.open) dialog.value.showModal()
    input.value?.focus()
  } else {
    dialog.value?.close()
  }
})
watch(query, () => { active.value = 0; importError.value = ''; searchVersion++ })

const navigate = (offset: number) => {
  if (!filtered.value.length) return
  active.value = (active.value + offset + filtered.value.length) % filtered.value.length
  nextTick(() => results.value?.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: 'nearest' }))
}

const dismissBackdrop = (event: MouseEvent) => {
  if (!dialog.value || event.target !== dialog.value) return
  const { left, right, top, bottom } = dialog.value.getBoundingClientRect()
  if (event.clientX < left || event.clientX > right || event.clientY < top || event.clientY > bottom) emit('close')
}

const importSymbol = async () => {
  if (importing.value) return
  const version = searchVersion
  importing.value = true
  importError.value = ''
  try {
    const item = await store.importInstrument(query.value.trim())
    if (version === searchVersion && props.show) emit('select', item.symbol)
  } catch (error) {
    if (version === searchVersion) importError.value = errorText(error, '联网查找失败，请检查股票代码或网络连接')
  } finally {
    importing.value = false
  }
}

const choose = (index: number) => {
  const result = filtered.value[index]
  if (!result) {
    if (/^\d{6}$/.test(query.value.trim())) void importSymbol()
    return
  }
  if (props.manageFavorites) void store.toggleFavorite(result.symbol)
  else emit('select', result.symbol)
}
</script>

<template>
  <dialog ref="dialog" class="search-dialog" aria-label="搜索股票" @cancel.prevent="emit('close')" @click="dismissBackdrop">
    <div class="dialog-input">
      <Search :size="21" aria-hidden="true" />
      <input ref="input" v-model="query" role="combobox" :aria-expanded="show" aria-controls="stock-results"
        aria-autocomplete="list" autocomplete="off" :aria-activedescendant="filtered[active] ? 'result-' + filtered[active].symbol : undefined"
        placeholder="搜索股票名称、代码或行业" aria-label="搜索股票名称、代码或行业"
        @keydown.down.prevent="navigate(1)" @keydown.up.prevent="navigate(-1)" @keydown.enter.prevent="!$event.isComposing && choose(active)" />
      <button class="close-button" aria-label="关闭搜索" @click="emit('close')"><X :size="17" /></button>
    </div>

    <div class="dialog-caption">
      <span>{{ manageFavorites ? '管理自选股' : query.trim() ? '搜索结果' : '本地股票库' }}</span>
      <span>{{ filtered.length }} 只</span>
    </div>
    <div id="stock-results" ref="results" class="dialog-results" role="listbox" aria-label="匹配的股票">
      <button v-for="(item, i) in filtered" :id="'result-' + item.symbol" :key="item.symbol" role="option" tabindex="-1"
        :aria-selected="active === i" @mousemove="active = i" @click="choose(i)">
        <StockAvatar :name="item.name" :symbol="item.symbol" :sector="item.sector" :size="36" />
        <span class="result-name">
          <strong>{{ item.name }}</strong>
          <small>{{ exchangeTag(item.exchange) }} · {{ item.symbol }}</small>
        </span>
        <span class="result-sector">{{ item.sector }}</span>
        <span class="result-change" :class="direction(item.changePercent)" title="相邻交易日收盘价变化，不复权数据受除权除息影响">
          {{ percent(item.changePercent) }}
        </span>
        <span v-if="manageFavorites" class="favorite-mark">
          <Star :size="16" :class="{ 'result-star': store.watchlist.includes(item.symbol) }" aria-hidden="true" />
          <span class="sr-only">{{ store.watchlist.includes(item.symbol) ? '已自选' : '未加入自选' }}</span>
        </span>
        <span v-else class="favorite-mark">
          <Star v-if="store.watchlist.includes(item.symbol)" :size="13" class="result-star" role="img" aria-label="已自选" />
        </span>
      </button>
    </div>

    <div v-if="!filtered.length" class="search-empty">
      <Search :size="23" aria-hidden="true" />
      <strong>本地股票库中无匹配结果</strong>
      <NButton v-if="/^\d{6}$/.test(query.trim())" class="import-button" type="primary" round
        :loading="importing" :disabled="importing" @click="importSymbol">
        {{ importing ? '正在联网查找…' : '联网查找 ' + query.trim() }}
      </NButton>
      <span v-else>输入沪深 A 股六位代码可联网查找</span>
      <span v-if="importError" class="import-error" role="alert">{{ importError }}</span>
    </div>

    <footer class="search-footer">
      <span><kbd>↑</kbd><kbd>↓</kbd>切换</span>
      <span><CornerDownLeft :size="13" />{{ manageFavorites ? '加入或移出自选' : '查看行情' }}</span>
      <span><kbd>Esc</kbd>关闭</span>
    </footer>
  </dialog>
</template>

<style scoped lang="scss">
.search-dialog {
  width: min(540px, calc(100vw - 28px));
  max-width: 100vw;
  max-height: 86vh;
  margin: min(12vh, 112px) auto auto;
  padding: 0;
  overflow: auto;
  color: var(--text);
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 20px;
  box-shadow: 0 18px 70px rgb(10 11 13 / 12%);

  &::backdrop { background: rgb(20 28 43 / 28%); }
}

.dialog-input {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 72px;
  padding: 12px 20px;
  color: var(--primary);
  border-bottom: 1px solid var(--line-soft);

  input {
    flex: 1;
    min-width: 0;
    padding: 6px 0;
    border: 0;
    outline: none;
    background: transparent;
    color: var(--text);
    font-size: 16px;

    &::placeholder { color: var(--muted); }
  }
}

.close-button {
  display: inline-grid;
  place-items: center;
  width: 30px;
  height: 30px;
  padding: 0;
  border-radius: 50%;
  color: var(--muted);
  background: var(--soft);
  &:hover { color: var(--primary); background: var(--primary-soft); }
}

.dialog-caption, .search-footer {
  display: flex;
  align-items: center;
  color: var(--muted);
  font-size: 12px;
}

.dialog-caption {
  justify-content: space-between;
  padding: 14px 20px 8px;
  font-weight: 500;
}

.dialog-results {
  max-height: min(49vh, 420px);
  overflow: auto;
  padding: 0 8px;

  &:not(:empty) { padding-bottom: 8px; }

  > button {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto 74px 18px;
    align-items: center;
    gap: 12px;
    width: 100%;
    padding: 10px 12px;
    border-radius: 10px;
    text-align: left;

    &[aria-selected=true] { background: var(--primary-soft); }
  }
}

.result-name {
  display: grid;
  min-width: 0;
  gap: 2px;
  line-height: 1.35;

  strong {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--text);
    font-size: 14px;
    font-weight: 600;
  }

  small { color: var(--muted); font-size: 11px; }
}

.result-sector { color: var(--muted); font-size: 12px; }
.result-change { text-align: right; font-size: 14px; font-variant-numeric: tabular-nums; }
.favorite-mark { display: inline-grid; place-items: center; color: var(--dim); }
.result-star { color: var(--primary); fill: currentColor; }

.search-empty {
  display: grid;
  justify-items: center;
  gap: 10px;
  padding: 32px 20px;
  text-align: center;
  color: var(--muted);
  font-size: 13px;

  strong { color: var(--text); font-size: 15px; font-weight: 550; }
}

.import-button {
  margin-top: 3px;
  font-weight: 600;
}

.import-error { color: var(--up); }
.search-footer {
  gap: 16px;
  padding: 12px 20px;
  background: var(--soft);
  border-top: 1px solid var(--line-soft);

  > span { display: inline-flex; align-items: center; gap: 5px; }
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
}

@media (max-width: 480px) {
  .search-dialog { margin-top: 6vh; }
  .dialog-input { min-height: 60px; gap: 8px; padding-inline: 14px; }
  .dialog-results > button { grid-template-columns: auto minmax(0, 1fr) auto 16px; gap: 8px; }
  .result-sector { display: none; }
  .search-footer { gap: 10px; padding-inline: 14px; font-size: 11px; }
}
</style>
