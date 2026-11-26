import { shell } from 'electron'
import type { JsonRequest } from '../shared/http'
import { createNewsApi, type NewsApi } from '../shared/news'
import { BindMapping } from './ipc/bind-mapping'

@BindMapping('news')
export class NewsController {
  readonly actions: NewsApi

  constructor(request: JsonRequest) {
    this.actions = createNewsApi(request, url => shell.openExternal(url))
  }
}
