<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from 'vue'
import { Search, X } from 'lucide-vue-next'
import InstrumentSearch from './components/InstrumentSearch.vue'
import { useMarketNavigation } from './navigation'
import { useWorkspace } from './store'

const store = useWorkspace()
const { search, openStock } = useMarketNavigation()
const ready = computed(() => !store.starting && !store.startupError)
const commandKey = /Mac/i.test(navigator.platform) ? '⌘' : 'Ctrl'

const onShortcut = (event: KeyboardEvent) => {
  if (((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') ||
    (event.key === '/' && !(event.target instanceof HTMLInputElement))) {
    event.preventDefault()
    if (ready.value) search()
  }
}

onMounted(() => {
  void store.initialize()
  window.addEventListener('keydown', onShortcut)
})
onBeforeUnmount(() => window.removeEventListener('keydown', onShortcut))
</script>

<template>
  <button class="search-trigger" :disabled="!ready" aria-label="搜索股票名称或代码" @click="search()">
    <Search :size="17" /><span>搜索股票名称或代码</span><kbd>{{ commandKey }} K</kbd>
  </button>
  <div class="local-status" :title="ready ? '本地行情服务已连接' : '本地行情服务状态'">
    <i :class="{ connected: ready }"></i><span>{{ store.starting ? '正在连接' : store.startupError ? '服务离线' : '本地已连接' }}</span>
  </div>
  <InstrumentSearch :show="store.searchMode !== null" :manage-favorites="store.searchMode === 'favorites'" @close="store.searchMode = null" @select="openStock" />
  <Transition name="toast">
    <div v-if="store.notice" class="notice" role="status">
      <span>{{ store.notice }}</span><button aria-label="关闭提示" @click="store.notice = ''"><X :size="15" /></button>
    </div>
  </Transition>
</template>

<style scoped lang="scss">
.search-trigger {
  display: flex; align-items: center; gap: 9px; min-height: 40px; width: clamp(200px, 21vw, 290px);
  padding: 0 15px; border-radius: 100px; background: var(--soft); color: var(--muted); font-size: 13px;
  &:hover:not(:disabled) { background: var(--line-soft); }
  kbd { margin-left: auto; line-height: 1.5; }
}
.local-status {
  display: inline-flex; align-items: center; gap: 8px; font-size: 12px; color: var(--muted); white-space: nowrap;
  i { width: 7px; height: 7px; border-radius: 50%; background: var(--dim); }
  i.connected { background: #09865d; }
}
.notice {
  display: flex; align-items: center; gap: 16px; max-width: min(420px, calc(100vw - 32px));
  position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%); z-index: 20;
  padding: 11px 12px 11px 19px; border-radius: 16px; color: #fff; background: #191c21; font-size: 14px;
  button { display: grid; place-items: center; padding: 5px; border-radius: 50%; color: #fff; }
}
.toast-enter-active, .toast-leave-active { transition: opacity .15s; }
.toast-enter-from, .toast-leave-to { opacity: 0; }
@media (max-width: 680px) {
  .local-status span { display: none; }
  .local-status { width: 12px; }
  .search-trigger { width: 35px; min-height: 35px; justify-content: center; padding: 0; }
  .search-trigger span, .search-trigger kbd { display: none; }
}
</style>
