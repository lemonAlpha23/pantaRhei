import type { WorkbenchPlugin } from '../../core/workbench'
import CompareView from './compare/CompareView.vue'
import MarketReady from './MarketReady.vue'
import MarketTools from './MarketTools.vue'
import MarketView from './MarketView.vue'
import WatchlistView from './WatchlistView.vue'
import SectorView from './sectors/SectorView.vue'
import MonitorView from './monitor/MonitorView.vue'

export const marketPlugin: WorkbenchPlugin = {
  id: 'market',
  layout: MarketReady,
  toolbar: MarketTools,
  pages: [
    { id: 'market', label: '行情', component: MarketView },
    { id: 'watchlist', label: '自选', component: WatchlistView },
    { id: 'compare', label: '对比', component: CompareView },
    { id: 'sectors', label: '板块', component: SectorView },
    { id: 'monitor', label: '监控', component: MonitorView },
  ],
}
