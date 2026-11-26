<script setup lang="ts">
import { CircleAlert, RefreshCw } from 'lucide-vue-next'
import { useWorkspace } from './store'

const store = useWorkspace()
</script>

<template>
  <div v-if="store.starting" class="empty page-state" role="status">
    <RefreshCw class="spin" :size="24" /><strong>正在读取本地行情</strong>
  </div>
  <div v-else-if="store.startupError" class="empty page-state" role="alert">
    <CircleAlert :size="25" /><strong>{{ store.startupError }}</strong>
    <button class="action primary" @click="store.initialize">重新连接</button>
  </div>
  <slot v-else />
</template>

<style scoped lang="scss">
.page-state { min-height: 55vh; }
.spin { animation: rotate 1s linear infinite; }
@keyframes rotate { to { transform: rotate(360deg); } }
</style>
