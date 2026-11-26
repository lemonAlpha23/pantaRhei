<script setup lang="ts">
import { computed, type Component } from 'vue'
import { Amphora, BatteryCharging, CarFront, ChartNoAxesCombined, Fan, Landmark, Mountain, Pill, ShieldCheck, Zap } from 'lucide-vue-next'

const props = withDefaults(defineProps<{ name: string; symbol: string; sector: string; size?: number }>(), { size: 36 })

const sectors: Record<string, { icon: Component; ink: string; tint: string }> = {
  白酒: { icon: Amphora, ink: '#aa4336', tint: '#fdece6' },
  电池: { icon: BatteryCharging, ink: '#177b62', tint: '#e3f5ed' },
  保险: { icon: ShieldCheck, ink: '#bf5a27', tint: '#fff0df' },
  银行: { icon: Landmark, ink: '#355bb2', tint: '#e8efff' },
  汽车整车: { icon: CarFront, ink: '#754ba0', tint: '#f0eaf8' },
  家用电器: { icon: Fan, ink: '#2d7396', tint: '#e5f3fa' },
  医药: { icon: Pill, ink: '#a54170', tint: '#faeaf0' },
  电力: { icon: Zap, ink: '#8a6812', tint: '#faf2d8' },
  有色金属: { icon: Mountain, ink: '#866447', tint: '#f5ede3' },
  证券: { icon: ChartNoAxesCombined, ink: '#286c87', tint: '#e4f2f5' },
}

const identity = computed(() => sectors[props.sector])
const initial = computed(() => Array.from(props.name.trim())[0] || props.symbol.slice(-1))
</script>

<template>
  <span class="stock-avatar" aria-hidden="true" :style="{
    '--size': size + 'px', color: identity?.ink, backgroundColor: identity?.tint,
  }">
    <component v-if="identity" :is="identity.icon" :size="Math.round(size * 0.53)" :stroke-width="1.8" />
    <span v-else>{{ initial }}</span>
  </span>
</template>

<style scoped lang="scss">
.stock-avatar {
  width: var(--size);
  height: var(--size);
  flex: 0 0 var(--size);
  display: inline-grid;
  place-items: center;
  border-radius: 50%;
  background: var(--primary-soft);
  color: var(--primary);
  font-size: calc(var(--size) * .44);
  font-weight: 600;
  line-height: 1;
}
</style>
