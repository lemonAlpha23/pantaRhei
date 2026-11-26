import { createApp } from 'vue'
import { createPinia } from 'pinia'
import Workbench from './core/Workbench.vue'
import { plugins } from './plugins'
import './theme.scss'

createApp(Workbench, { plugins }).use(createPinia()).mount('#app')
