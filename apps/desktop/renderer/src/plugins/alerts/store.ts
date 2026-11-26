import { ref, shallowRef } from 'vue'
import { defineStore } from 'pinia'
import type { AlertInput, AlertSnapshot } from '../../../../shared/alerts'
import { useWindowUpdates } from '../../core/window-updates'
import { alertsApi } from './api'

export const useAlertsStore = defineStore('price-alerts', () => {
  const snapshot = shallowRef<AlertSnapshot | null>(null)
  const historyRequested = ref(false)
  let queue = Promise.resolve()
  let pendingRead: Promise<void> | undefined

  // A slow read must finish before a newer mutation publishes its snapshot.
  const update = <T extends AlertSnapshot>(action: () => Promise<T>) => {
    const result = queue.then(async () => {
      const data = await action()
      snapshot.value = data
      return data
    })
    queue = result.then(() => {}, () => {})
    return result
  }
  const read = async () => { await update(alertsApi.getAlerts) }
  const getAlerts = () => {
    pendingRead ??= read().finally(() => { pendingRead = undefined })
    return pendingRead
  }
  const publish = useWindowUpdates('price-alerts', read)
  const mutate = async <T extends AlertSnapshot>(action: () => Promise<T>) => {
    const result = await update(action)
    publish('rules')
    return result
  }
  const createAlert = (rule: AlertInput) => mutate(() => alertsApi.createAlert(rule))
  const setAlertEnabled = (id: number, enabled: boolean) => mutate(() => alertsApi.setAlertEnabled(id, enabled))
  const deleteAlert = (id: number) => mutate(() => alertsApi.deleteAlert(id))
  const checkAlerts = async () => (await mutate(alertsApi.checkAlerts)).check
  return { snapshot, historyRequested, getAlerts, createAlert, setAlertEnabled, deleteAlert, checkAlerts }
})
