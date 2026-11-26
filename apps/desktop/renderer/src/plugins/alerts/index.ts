import type { WorkbenchPlugin } from '../../core/workbench'
import AlertNotice from './AlertNotice.vue'
import AlertsView from './AlertsView.vue'

export const alertsPlugin = {
  id: 'alerts',
  status: AlertNotice,
  pages: [{ id: 'alerts', label: '提醒', component: AlertsView }],
} satisfies WorkbenchPlugin
