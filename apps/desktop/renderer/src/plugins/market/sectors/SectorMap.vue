<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { percent } from '../format'
import { layoutSectors } from './layout'
import type { SectorMetric } from './metrics'

const props = defineProps<{ groups: SectorMetric[]; selected: string }>()
const emit = defineEmits<{ select: [sector: string] }>()
const surface = ref<HTMLDivElement>()
const size = ref({ width: 0, height: 0 })
let observer: ResizeObserver | undefined

const color = (change: number | null) => {
  if (change === null) return 'var(--soft)'
  if (change === 0) return '#e7eaed'
  const strength = Math.min(1, Math.abs(change) / 3)
  return change > 0 ? `hsl(4 76% ${92 - 23 * strength}%)` : `hsl(158 44% ${88 - 27 * strength}%)`
}

const tiles = computed(() => {
  const byId = new Map(props.groups.map(group => [group.id, group]))
  return layoutSectors(props.groups, size.value.width, size.value.height).map(rect => {
    const group = byId.get(rect.id)!
    return { rect, group, style: {
      left: `${rect.x}px`, top: `${rect.y}px`, width: `${rect.width}px`, height: `${rect.height}px`,
      '--tile-color': color(group.changePercent),
    } }
  })
})
const label = (group: SectorMetric) => `${group.id}，${group.changePercent === null ? '涨跌幅暂无数据' : percent(group.changePercent)}，${group.count} 只股票`

onMounted(() => {
  if (!surface.value) return
  observer = new ResizeObserver(([entry]) => {
    size.value = { width: entry.contentRect.width, height: entry.contentRect.height }
  })
  observer.observe(surface.value)
})
onBeforeUnmount(() => observer?.disconnect())
</script>

<template>
  <div ref="surface" class="map" role="group" aria-label="板块热力图">
    <button v-for="{ rect, group, style } in tiles" :key="group.id" type="button" class="tile" :style="style"
      :class="{ compact: rect.width < 100 || rect.height < 78, tiny: rect.width < 48 || rect.height < 37, missing: group.changePercent === null }"
      :aria-label="label(group)" :aria-pressed="selected === group.id" :title="label(group)" @click="emit('select', group.id)">
      <span class="tile-face">
        <strong>{{ group.id }}</strong>
        <span class="change">{{ percent(group.changePercent) }}</span>
      </span>
    </button>
  </div>
</template>

<style scoped lang="scss">
.map { position: relative; width: 100%; height: clamp(325px, 31vw, 453px); min-width: 0; overflow: clip; }
.tile {
  position: absolute; padding: 2px; min-width: 0;
  &:hover .tile-face { box-shadow: inset 0 0 0 1px #303943; }
  &[aria-pressed='true'] .tile-face { box-shadow: inset 0 0 0 2px #303943; }
  &:focus-visible { outline-offset: -3px; z-index: 1; }
}
.tile-face {
  height: 100%; width: 100%; display: flex; flex-direction: column; justify-content: center;
  align-items: flex-start; gap: 4px; padding: clamp(9px, 1.4vw, 20px); border-radius: 9px;
  color: #17211e; overflow: hidden; background: var(--tile-color);
  strong, .change { display: block; width: 100%; overflow: hidden; text-align: left; white-space: nowrap; text-overflow: ellipsis; }
  strong { font-size: clamp(15px, 1.55vw, 23px); font-weight: 600; letter-spacing: -.035em; }
  .change { font-size: clamp(12px, 1.05vw, 16px); font-weight: 530; font-variant-numeric: tabular-nums; }
}
.compact .tile-face { padding: 5px 2px; gap: 0; align-items: center; strong { text-align: center; font-size: 14px; } .change { text-align: center; font-size: 11px; } }
.tiny .tile-face { padding: 2px; .change { display: none; } }
.missing .tile-face { background: repeating-linear-gradient(135deg,#f6f7f9,#f6f7f9 5px,#e9ecf0 5px,#e9ecf0 6px); }
@media (max-width: 540px) {
  .map { height: 342px; }
  .tile-face { padding: 8px 7px; }
}
</style>
