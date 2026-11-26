import type { WorkbenchPlugin } from '../core/workbench'
import { alertsPlugin } from './alerts'
import { marketPlugin } from './market'
import { newsPlugin } from './news'
import { xMonitorPlugin } from './xmonitor'

export const plugins: readonly WorkbenchPlugin[] = [marketPlugin, alertsPlugin, newsPlugin, xMonitorPlugin]
