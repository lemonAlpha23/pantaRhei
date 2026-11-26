interface WeightedSector {
  id: string
  count: number
}

interface Rect {
  x: number
  y: number
  width: number
  height: number
}

export const layoutSectors = (items: readonly WeightedSector[], width: number, height: number) => {
  const tiles: (Rect & { id: string })[] = []
  const sectors = items.filter(item => Number.isFinite(item.count) && item.count > 0)
    .sort((a, b) => b.count - a.count)
  if (!sectors.length || !Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) return tiles

  // Split along the longer side, keeping the two groups as close in weight as possible.
  const partition = (from: number, to: number, total: number, rect: Rect) => {
    if (to - from === 1) {
      tiles.push({ id: sectors[from].id, ...rect })
      return
    }
    let split = from + 1
    let weight = sectors[from].count
    while (split < to - 1 && Math.abs(total / 2 - weight - sectors[split].count) < Math.abs(total / 2 - weight)) {
      weight += sectors[split].count
      split++
    }
    if (rect.width >= rect.height) {
      const cut = rect.width * weight / total
      partition(from, split, weight, { ...rect, width: cut })
      partition(split, to, total - weight, { ...rect, x: rect.x + cut, width: rect.width - cut })
    } else {
      const cut = rect.height * weight / total
      partition(from, split, weight, { ...rect, height: cut })
      partition(split, to, total - weight, { ...rect, y: rect.y + cut, height: rect.height - cut })
    }
  }
  partition(0, sectors.length, sectors.reduce((sum, item) => sum + item.count, 0), { x: 0, y: 0, width, height })
  return tiles
}
