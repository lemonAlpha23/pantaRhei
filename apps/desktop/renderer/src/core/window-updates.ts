import { onScopeDispose } from 'vue'

// Send invalidations only. Every window reads committed data via its own plugin API.
export const useWindowUpdates = (plugin: string, reload: (key: string) => Promise<void>) => {
  const channel = typeof window.BroadcastChannel === 'function' && window.workspaceWindows
    ? new window.BroadcastChannel('pantarhei:' + plugin) : undefined
  const pending = new Set<string>()
  let reading = false
  let closed = false
  const enqueue = async (key: string) => {
    pending.add(key)
    if (reading) return
    reading = true
    try {
      while (pending.size && !closed) {
        const [next] = pending
        pending.delete(next)
        // If the local service is temporarily unavailable, retain the last good snapshot.
        await reload(next).catch(() => {})
      }
    } finally {
      reading = false
    }
  }
  if (channel) channel.onmessage = ({ data }) => {
    if (typeof data === 'string') void enqueue(data)
  }
  onScopeDispose(() => {
    closed = true
    pending.clear()
    channel?.close()
  })
  return (key: string) => {
    if (!channel || closed) return
    channel.postMessage(key)
    void enqueue(key)
  }
}
