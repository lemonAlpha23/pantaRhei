import { inject, shallowRef, type Component, type InjectionKey } from 'vue'

export interface WorkbenchPage {
  id: string
  label: string
  component: Component
  keepAlive?: boolean
}

export interface WorkbenchPlugin {
  id: string
  pages: readonly WorkbenchPage[]
  setup?: () => void
  layout?: Component
  toolbar?: Component
  status?: Component
}

export interface RegisteredPage extends WorkbenchPage {
  layout?: Component
}

export const createWorkbench = (plugins: readonly WorkbenchPlugin[]) => {
  const pluginIds = new Set<string>()
  const byId = new Map<string, RegisteredPage>()
  for (const plugin of plugins) {
    if (pluginIds.has(plugin.id)) throw new Error(`重复的工作台插件：${plugin.id}`)
    pluginIds.add(plugin.id)
    for (const page of plugin.pages) {
      if (byId.has(page.id)) throw new Error(`重复的工作台页面：${page.id}`)
      byId.set(page.id, { ...page, layout: plugin.layout })
    }
  }
  const pages = [...byId.values()]
  const current = shallowRef<RegisteredPage | undefined>(pages[0])
  const navigate = (id: string) => {
    const page = byId.get(id)
    if (page) current.value = page
  }
  return { pages, current, navigate }
}

export const workbenchKey: InjectionKey<{ navigate: (id: string) => void }> = Symbol('workbench')

export const useWorkbench = () => {
  const workbench = inject(workbenchKey)
  if (!workbench) throw new Error('此组件需要在工作台内使用')
  return workbench
}
