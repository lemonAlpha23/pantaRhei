import type { WorkbenchPlugin } from '../../core/workbench'
import NewsView from './NewsView.vue'

export const newsPlugin: WorkbenchPlugin = {
  id: 'news',
  pages: [{ id: 'news', label: '资讯', component: NewsView, keepAlive: true }],
}
