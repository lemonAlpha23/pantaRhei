import { inject, onScopeDispose, shallowReactive, type InjectionKey } from 'vue'
import type { WindowsApi, WindowTarget } from '../../../shared/windows'

declare global {
  interface Window {
    workspaceWindows?: WindowsApi
  }
}

interface PageState {
  capture: () => Record<string, string>
  title?: () => string
}

export const createWindowContext = (initial?: WindowTarget) => {
  const mounted = shallowReactive(new Map<string, PageState>())
  let pending = initial
  const register = (id: string, provider: PageState) => {
    mounted.set(id, provider)
    onScopeDispose(() => {
      if (mounted.get(id) === provider) mounted.delete(id)
    })
    const state = pending?.page === id ? pending.state : undefined
    if (pending?.page === id) pending = undefined
    return state ?? {}
  }
  const target = (page: string): WindowTarget => ({
    page, state: mounted.get(page)?.capture() ?? (pending?.page === page ? pending.state : undefined),
  })
  const title = (page: string) => mounted.get(page)?.title?.()
  return { detached: Boolean(initial), register, target, title }
}

export const windowContextKey: InjectionKey<ReturnType<typeof createWindowContext>> = Symbol('workbench-window')
export const pageIdKey: InjectionKey<string> = Symbol('workbench-page')

export const useWindowContext = () => ({ detached: inject(windowContextKey, undefined)?.detached ?? false })

export const usePageWindowState = (capture: PageState['capture'], title?: PageState['title']): Readonly<Record<string, string>> => {
  const context = inject(windowContextKey, undefined)
  const id = inject(pageIdKey, undefined)
  return context && id ? context.register(id, { capture, title }) : {}
}
