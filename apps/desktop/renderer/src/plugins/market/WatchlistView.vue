<script setup lang="ts">
import { ref } from 'vue'
import { Plus } from 'lucide-vue-next'
import { usePageWindowState } from '../../core/page-window'
import { useWorkspace } from './store'
import { useMarketNavigation } from './navigation'
import Watchlist from './components/Watchlist.vue'

const store = useWorkspace()
const { search, openStock } = useMarketNavigation()
const sort = ref<'default' | 'desc' | 'asc'>('default')
const initial = usePageWindowState(() => ({ sort: sort.value }))
if (initial.sort === 'desc' || initial.sort === 'asc') sort.value = initial.sort
</script>

<template>
  <section class="watchlist-view">
    <header class="page-title"><div><h1>自选股</h1><span>{{ store.favorites.length }} 只股票</span></div>
      <button class="action primary" @click="search(true)"><Plus :size="17" />管理自选</button>
    </header>
    <Watchlist full v-model:sort="sort" @select="openStock" @search="search(true)" />
  </section>
</template>

<style scoped lang="scss">
.watchlist-view { min-width: 0; }
.page-title {
  display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 24px;
  > div { display: flex; align-items: baseline; gap: 12px; }
  span { color: var(--muted); font-size: 14px; }
  h1 { font-size: clamp(30px, 3vw, 44px); font-weight: 550; letter-spacing: -.05em; }
}
</style>
