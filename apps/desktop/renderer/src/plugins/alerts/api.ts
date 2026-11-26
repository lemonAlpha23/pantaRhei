import { createAlertsApi, type AlertsApi } from '../../../../shared/alerts'
import { fetchTransport } from '../../core/http'

declare global {
  interface Window {
    alerts?: AlertsApi
  }
}

export const alertsApi: AlertsApi = window.alerts ?? createAlertsApi(fetchTransport)
