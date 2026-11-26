<script setup lang="ts">
import { provide } from 'vue'
import type { RegisteredPage } from './workbench'
import { pageIdKey } from './page-window'

const props = defineProps<{ page: RegisteredPage }>()
provide(pageIdKey, props.page.id)
</script>

<template>
  <component :is="page.layout" v-if="page.layout">
    <component :is="page.component" />
  </component>
  <component :is="page.component" v-else />
</template>
