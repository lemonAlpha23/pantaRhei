import assert from 'node:assert/strict'
import { test } from 'node:test'
import { effectScope } from 'vue'
import { encodeWindowTarget, readWindowTarget, type WindowTarget } from '../../shared/windows.ts'
import { createWindowContext } from '../src/core/page-window.ts'

test('窗口片段只携带页号及有界的文本状态', () => {
  const target = { page: 'research', state: { query: '贵州茅台 & A/#1', range: '60' } }
  const hash = encodeWindowTarget(target)
  assert.deepEqual(readWindowTarget(hash), target)
  assert.equal(readWindowTarget(''), undefined)
  assert.equal(readWindowTarget('#window=%E0%A4'), undefined)
  for (const invalid of [
    { page: 'https://example.com' }, { page: '../market' }, { page: 'a/b' },
    { page: 'market', state: [] }, { page: 'news', state: { source: 12 } },
    { page: 'market', state: { symbol: 'a'.repeat(257) } },
    { page: 'market', state: JSON.parse('{"__proto__":"x"}') },
  ]) {
    assert.throws(() => encodeWindowTarget(invalid as WindowTarget))
    assert.equal(readWindowTarget('#window=' + encodeURIComponent(JSON.stringify(invalid))), undefined)
  }
})

test('窗口初始状态只由目标页领取一次，各窗口的实时状态与标题相互独立', () => {
  const source = createWindowContext({ page: 'market', state: { symbol: '600519' } })
  const peer = createWindowContext()
  const scope = effectScope()
  let symbol = '600519'
  scope.run(() => {
    assert.deepEqual(source.register('news', { capture: () => ({}) }), {})
    assert.deepEqual(source.register('market', { capture: () => ({ symbol }), title: () => symbol }), { symbol })
    peer.register('market', { capture: () => ({ symbol: '601318' }) })
  })
  symbol = '300750'
  assert.equal(source.title('market'), symbol)
  assert.equal(source.target('market').state?.symbol, symbol)
  assert.equal(peer.target('market').state?.symbol, '601318')
  scope.stop()
  assert.equal(source.target('market').state, undefined)
  const remount = effectScope()
  remount.run(() => assert.deepEqual(source.register('market', { capture: () => ({}) }), {}))
  remount.stop()
})
