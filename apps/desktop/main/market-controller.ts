import type { JsonRequest } from '../shared/http'
import { createMarketApi, type MarketApi } from '../shared/market'
import { BindMapping } from './ipc/bind-mapping'

@BindMapping('market')
export class MarketController {
  readonly actions: MarketApi

  constructor(request: JsonRequest) {
    this.actions = createMarketApi(request)
  }
}
