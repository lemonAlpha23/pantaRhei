import assert from 'node:assert/strict'
import { test } from 'node:test'
import { layoutSectors } from '../src/plugins/market/sectors/layout.ts'

test('在横向和纵向画布上，板块面积与样本数量成正比，矩形互不重叠', () => {
  const items = [2, 1, 4, 1, 3].map((count, i) => ({ count, id: String(i) }))
  for (const [width, height] of [[863, 380], [320, 550]]) {
    const tiles = layoutSectors(items, width, height)
    assert.equal(tiles.length, items.length)
    for (const [i, tile] of tiles.entries()) {
      const share = tile.width * tile.height / (width * height)
      assert.ok(Math.abs(share - items[Number(tile.id)].count / 11) < 1e-10)
      assert.ok(tile.x >= 0 && tile.y >= 0 && tile.x + tile.width <= width + 1e-9 && tile.y + tile.height <= height + 1e-9)
      for (const other of tiles.slice(i + 1)) {
        const w = Math.min(tile.x + tile.width, other.x + other.width) - Math.max(tile.x, other.x)
        const h = Math.min(tile.y + tile.height, other.y + other.height) - Math.max(tile.y, other.y)
        assert.ok(w < 1e-9 || h < 1e-9)
      }
    }
  }
})

test('未测量的画布和空板块无需布局', () => {
  assert.deepEqual(layoutSectors([{ id: 'A', count: 1 }], 0, 300), [])
  assert.deepEqual(layoutSectors([{ id: 'A', count: 0 }], 500, 300), [])
})
