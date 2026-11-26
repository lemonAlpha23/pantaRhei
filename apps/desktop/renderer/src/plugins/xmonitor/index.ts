import { provide } from 'vue'
import type { WorkbenchPlugin } from '../../core/workbench'
import { orderMarkSourceKey } from '../market/order-marks'
import { xApi } from './api'
import XMonitorView from './XMonitorView.vue'
import XNoticeBanner from './XNoticeBanner.vue'

export const xMonitorPlugin = {
  id: 'x-monitor',
  setup: () => provide(orderMarkSourceKey, xApi.getOrderMarks),
  status: XNoticeBanner,
  pages: [{ id: 'x-monitor', label: 'X 动态', component: XMonitorView }],
} satisfies WorkbenchPlugin
