import { ref, shallowRef } from 'vue'
import { defineStore } from 'pinia'
import type { XInbox, XNotice } from '../../../../shared/xmonitor'
import { useWindowUpdates } from '../../core/window-updates'
import { xApi } from './api'

export const useXNoticeStore = defineStore('x-notices', () => {
  const inbox = shallowRef<XInbox | null>(null)
  const latest = shallowRef<XNotice>()
  const unread = ref(0)
  const viewingInbox = ref(false)
  const inboxRequested = ref(false)
  let queue = Promise.resolve()
  const pending = new Map<boolean, Promise<void>>()

  // Apply reads and acknowledgements in order so an older poll cannot restore an unread badge.
  const update = (action: () => Promise<XInbox>, full: boolean) => {
    const result = queue.then(async () => {
      const snapshot = await action()
      if (full) inbox.value = snapshot
      unread.value = snapshot.unread
      latest.value = snapshot.items.find(item => !item.read)
    })
    queue = result.catch(() => {})
    return result
  }
  const load = (full: boolean) => update(() => xApi.getNotices(full ? undefined : 1), full)
  const read = (full: boolean) => {
    const previous = pending.get(full)
    if (previous) return previous
    const result = load(full).finally(() => pending.delete(full))
    pending.set(full, result)
    return result
  }
  const getInbox = () => read(true)
  const poll = () => read(viewingInbox.value)
  const publish = useWindowUpdates('x-notices', () => load(viewingInbox.value))
  const invalidate = () => {
    if (window.workspaceWindows && typeof window.BroadcastChannel === 'function') publish('inbox')
    else void load(viewingInbox.value).catch(() => {})
  }
  const acknowledge = async (action: () => Promise<XInbox>) => {
    await update(action, true)
    publish('inbox')
  }
  const markRead = (id: string) => acknowledge(() => xApi.markNoticeRead(id))
  const markAllRead = () => acknowledge(xApi.markAllNoticesRead)
  const openOriginal = async (item: XNotice) => {
    await xApi.openPost(item.handle, item.id)
    if (!item.read) {
      try { await markRead(item.id) }
      catch { throw new Error('原帖已打开，已读状态保存失败。') }
    }
  }
  return { inbox, latest, unread, viewingInbox, inboxRequested, poll, getInbox, invalidate, markRead, markAllRead, openOriginal }
})
