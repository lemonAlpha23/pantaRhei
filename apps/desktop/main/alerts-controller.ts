import { createAlertsApi, type AlertsApi } from '../shared/alerts'
import type { JsonRequest } from '../shared/http'
import { BindMapping } from './ipc/bind-mapping'

@BindMapping('alerts')
export class AlertsController {
  readonly actions: AlertsApi

  constructor(request: JsonRequest) {
    this.actions = createAlertsApi(request)
  }
}
