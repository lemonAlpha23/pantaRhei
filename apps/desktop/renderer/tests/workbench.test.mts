import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createWorkbench, type WorkbenchPlugin } from '../src/core/workbench.ts'

const list = { name: 'NotesList' }
const detail = { name: 'NoteDetail' }
const layout = { name: 'NotebookLayout' }
const notes: WorkbenchPlugin = {
  id: 'notes', layout,
  pages: [
    { id: 'notes-list', label: '笔记', component: list },
    { id: 'note-detail', label: '详情', component: detail, keepAlive: true },
  ],
}
const calendar: WorkbenchPlugin = {
  id: 'calendar',
  pages: [{ id: 'agenda', label: '日历', component: { name: 'Calendar' } }],
}

test('由启用清单决定导航顺序、默认页、布局及缓存策略', () => {
  const { pages, current, navigate } = createWorkbench([calendar, notes])
  assert.deepEqual(pages.map(page => page.id), ['agenda', 'notes-list', 'note-detail'])
  assert.equal(current.value?.id, 'agenda')
  navigate('note-detail')
  assert.equal(current.value?.component, detail)
  assert.equal(current.value?.layout, layout)
  assert.equal(current.value?.keepAlive, true)

  const standalone = createWorkbench([notes])
  standalone.navigate('agenda')
  assert.equal(standalone.current.value?.id, 'notes-list')
  assert.equal(createWorkbench([]).current.value, undefined)
})

test('在挂载前指出重复的插件或页面编号', () => {
  assert.throws(() => createWorkbench([notes, notes]), /重复的工作台插件：notes/)
  assert.throws(() => createWorkbench([notes, { ...calendar, pages: notes.pages }]), /重复的工作台页面：notes-list/)
})
