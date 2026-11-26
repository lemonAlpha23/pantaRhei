import { encodeWindowTarget, type WindowsApi } from '../shared/windows'
import { BindMapping } from './ipc/bind-mapping'

@BindMapping('windows')
export class WindowsController {
  readonly actions: WindowsApi

  constructor(open: (hash: string) => Promise<void>) {
    this.actions = { openPage: target => open(encodeWindowTarget(target)) }
  }
}
