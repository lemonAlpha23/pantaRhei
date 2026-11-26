import { shell } from 'electron'
import type { JsonRequest } from '../shared/http'
import { createXApi, type XApi } from '../shared/xmonitor'
import { BindMapping } from './ipc/bind-mapping'

@BindMapping('xmonitor')
export class XMonitorController {
  readonly actions: XApi

  constructor(request: JsonRequest) {
    this.actions = createXApi(request, url => shell.openExternal(url))
  }
}
