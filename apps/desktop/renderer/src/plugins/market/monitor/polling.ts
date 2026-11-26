interface MonitorTasks {
  visible: () => boolean
  automatic: () => boolean
  read: () => Promise<void>
  refresh: () => Promise<void>
}

export const createMonitorPolling = (tasks: MonitorTasks) => {
  let timer: ReturnType<typeof setTimeout> | undefined
  let running = false
  let stopped = false
  let needsCache = false
  let nextRefresh: 'manual' | 'auto' | undefined

  const drain = async () => {
    clearTimeout(timer)
    if (running || stopped || !tasks.visible()) return
    running = true
    try {
      while (!stopped && tasks.visible()) {
        if (needsCache) {
          needsCache = false
          await tasks.read()
          continue
        }
        const kind = nextRefresh
        nextRefresh = undefined
        if (!kind || (kind === 'auto' && !tasks.automatic())) break
        await tasks.refresh()
      }
    } finally {
      running = false
      if (!stopped && tasks.visible() && tasks.automatic()) {
        timer = setTimeout(() => { nextRefresh = 'auto'; void drain() }, 30_000)
      }
    }
  }

  const sync = () => {
    needsCache = tasks.visible()
    nextRefresh = tasks.automatic() ? 'auto' : undefined
    return drain()
  }
  const readCached = () => { needsCache = true; return drain() }
  const refreshNow = () => { nextRefresh = 'manual'; return drain() }
  const stop = () => { stopped = true; clearTimeout(timer) }
  return { sync, readCached, refreshNow, stop }
}
