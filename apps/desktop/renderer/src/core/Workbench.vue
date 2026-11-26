<script setup lang="ts">
import { onBeforeUnmount, onMounted, provide, ref, watch, watchEffect } from 'vue'
import { NConfigProvider } from 'naive-ui'
import { AppWindow, ExternalLink } from 'lucide-vue-next'
import { encodeWindowTarget, readWindowTarget } from '../../../shared/windows'
import { createWorkbench, workbenchKey, type WorkbenchPlugin } from './workbench'
import { createWindowContext, windowContextKey } from './page-window'
import WorkbenchPageHost from './WorkbenchPageHost.vue'

const props = defineProps<{ plugins: readonly WorkbenchPlugin[] }>()
const { pages, current, navigate } = createWorkbench(props.plugins)
const initial = readWindowTarget(window.location.hash)
const windowContext = createWindowContext(initial && pages.some(page => page.id === initial.page) ? initial : undefined)
if (initial) navigate(initial.page)
provide(windowContextKey, windowContext)
provide(workbenchKey, { navigate })
for (const plugin of props.plugins) plugin.setup?.()
const windowApi = window.workspaceWindows
const opening = ref(false)
const openError = ref('')
const navigation = ref<HTMLElement>()
const revealCurrentTab = () => {
  const bar = navigation.value
  const active = bar?.querySelector<HTMLElement>('[aria-current="page"]')
  if (!bar || !active) return
  const tab = active.getBoundingClientRect()
  const bounds = bar.getBoundingClientRect()
  if (tab.right > bounds.right) bar.scrollLeft += Math.ceil(tab.right - bounds.right)
  else if (tab.left < bounds.left) bar.scrollLeft -= Math.ceil(bounds.left - tab.left)
}
let navigationSize: ResizeObserver | undefined
onMounted(() => {
  if (!navigation.value) return
  navigationSize = new ResizeObserver(revealCurrentTab)
  navigationSize.observe(navigation.value)
  revealCurrentTab()
})
onBeforeUnmount(() => navigationSize?.disconnect())
watch(current, revealCurrentTab, { flush: 'post' })
const openPage = async () => {
  if (!windowApi || !current.value || opening.value) return
  opening.value = true
  openError.value = ''
  try {
    await windowApi.openPage(windowContext.target(current.value.id))
  } catch {
    openError.value = '窗口未能打开，请重试。'
  } finally {
    opening.value = false
  }
}
watch(current, () => { openError.value = '' })
watchEffect(() => {
  const page = current.value
  document.title = page && windowContext.detached
    ? (windowContext.title(page.id) || page.label) + ' · Panta Rhei'
    : 'Panta Rhei'
  if (page && windowContext.detached) {
    const hash = encodeWindowTarget(windowContext.target(page.id))
    if (hash !== window.location.hash) window.history.replaceState(window.history.state, '', hash)
  }
}, { flush: 'post' })
const toolbars = props.plugins.filter(plugin => plugin.toolbar)
const statuses = props.plugins.filter(plugin => plugin.status)
const theme = { common: {
  primaryColor: '#0052ff', primaryColorHover: '#0046dd', primaryColorPressed: '#003ecc', borderRadius: '12px',
} }
</script>

<template>
  <NConfigProvider :theme-overrides="theme">
    <header class="topbar">
      <div class="topbar-inner">
        <button class="brand" :aria-label="pages.length ? 'Panta Rhei ' + pages[0].label + '首页' : 'Panta Rhei'" @click="pages.length && navigate(pages[0].id)">
          <img src="/mark.svg" width="34" height="34" alt="" /><span>Panta Rhei</span>
        </button>
        <nav ref="navigation" aria-label="工作区导航">
          <button v-for="page in pages" :key="page.id" :aria-current="current?.id === page.id ? 'page' : undefined" @click="navigate(page.id)">
            {{ page.label }}
          </button>
        </nav>
        <div v-if="toolbars.length || windowApi" class="topbar-tools">
          <component :is="plugin.toolbar" v-for="plugin in toolbars" :key="plugin.id" />
          <button v-if="windowApi && current" type="button" class="open-window" aria-label="在新窗口打开" title="在新窗口打开当前页面" :disabled="opening" @click="openPage">
            <ExternalLink :size="17" />
          </button>
        </div>
      </div>
    </header>
    <main class="workspace">
      <component :is="plugin.status" v-for="plugin in statuses" :key="plugin.id" />
      <p v-if="openError" role="alert" class="window-error"><AppWindow :size="16" />{{ openError }}</p>
      <KeepAlive>
        <WorkbenchPageHost v-if="current?.keepAlive" :key="current.id" :page="current" />
      </KeepAlive>
      <WorkbenchPageHost v-if="current && !current.keepAlive" :key="current.id" :page="current" />
      <div v-if="!current" class="empty empty-workspace" role="status">暂无已启用的页面</div>
    </main>
  </NConfigProvider>
</template>

<style scoped lang="scss">
.topbar { border-bottom: 1px solid var(--line-soft); background: var(--surface); }
.topbar-inner, .workspace { max-width: 1480px; margin: 0 auto; padding-inline: clamp(24px, 4.6vw, 72px); }
.topbar-inner { min-height: 73px; display: flex; align-items: center; gap: clamp(28px, 4vw, 64px); }
.brand {
  display: inline-flex; align-items: center; gap: 10px; padding: 0;
  color: var(--text); white-space: nowrap; font-size: 24px; font-weight: 650; letter-spacing: -.065em;
}
nav {
  display: flex; align-self: stretch; align-items: stretch; gap: 24px; min-width: 0; overflow-x: auto;
  button {
    flex: 0 0 auto; border-bottom: 2px solid transparent; padding: 2px 4px 0;
    font-size: 15px; font-weight: 550; color: var(--muted);
    &:hover { color: var(--text); }
    &[aria-current="page"] { border-color: var(--primary); color: var(--text); }
  }
}
.topbar-tools { display: flex; align-items: center; gap: 24px; margin-left: auto; }
.open-window { display: inline-grid; place-items: center; flex: 0 0 auto; width: 36px; height: 36px; border-radius: 50%; color: var(--muted); }
.open-window:hover { background: var(--soft); color: var(--primary); }
.window-error { display: flex; align-items: center; gap: 8px; margin-bottom: 16px; color: var(--muted); }
.workspace { padding-block: clamp(28px, 3vw, 46px) 64px; }
.empty-workspace { min-height: 55vh; }
@media (max-width: 680px) {
  .topbar-inner, .workspace { padding-inline: 18px; }
  .topbar-inner { flex-wrap: wrap; gap: 0; min-height: 60px; padding-top: 14px; }
  .brand { gap: 8px; font-size: 22px; }
  .brand img { width: 29px; height: 29px; }
  .topbar-tools { gap: 12px; }
  nav { order: 1; width: 100%; gap: 22px; height: 41px; }
  .workspace { padding-block: 24px 36px; }
}
</style>
