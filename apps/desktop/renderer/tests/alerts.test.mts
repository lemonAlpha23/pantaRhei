import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createAlertsApi } from '../../shared/alerts.ts'
import { jsonOptions, type JsonRequest } from '../../shared/http.ts'

test('价格提醒 IPC 和网页预览使用相同的 JSON 请求契约', async () => {
  const calls: unknown[][] = []
  const request: JsonRequest = async (path, method = 'GET', body) => {
    calls.push([path, method, body])
    return undefined as never
  }
  const api = createAlertsApi(request)
  const rule = { symbol: '000001', direction: 'above', target: 10.25 } as const
  await api.getAlerts()
  await api.createAlert(rule)
  await api.setAlertEnabled(7, false)
  await api.deleteAlert(7)
  await api.checkAlerts()
  assert.deepEqual(calls, [
    ['/api/alerts', 'GET', undefined], ['/api/alerts', 'POST', rule],
    ['/api/alerts/7', 'PATCH', { enabled: false }], ['/api/alerts/7', 'DELETE', undefined],
    ['/api/alerts/check', 'POST', undefined],
  ])
  assert.deepEqual(jsonOptions('PATCH', { enabled: false }, { Authorization: 'Bearer test' }), {
    method: 'PATCH', headers: { Authorization: 'Bearer test', 'Content-Type': 'application/json' }, body: '{"enabled":false}',
  })
  assert.equal(jsonOptions('GET').body, undefined)
})

test('无效的提醒、编号或启用状态在传输前被拒绝', async () => {
  const api = createAlertsApi(async () => { assert.fail('不应发起请求') })
  const rule = { symbol: '000001', target: 12, direction: 'below' } as const
  for (const symbol of ['00000', '000001\n', '０００００１', null]) {
    await assert.rejects(Reflect.apply(api.createAlert, undefined, [{ ...rule, symbol }]), /股票代码/)
  }
  for (const target of [0, -1, NaN, Infinity, 0.009, 10.125, 1000000, true, '12.80']) {
    await assert.rejects(Reflect.apply(api.createAlert, undefined, [{ ...rule, target }]), /目标价/)
  }
  await assert.rejects(Reflect.apply(api.createAlert, undefined, [{ ...rule, direction: 'down' }]), /方向/)
  for (const id of [0, -1, 3.5, '1/2', Number.MAX_SAFE_INTEGER + 1]) {
    await assert.rejects(Reflect.apply(api.deleteAlert, undefined, [id]), /编号/)
  }
  await assert.rejects(Reflect.apply(api.setAlertEnabled, undefined, [1, 1]), /状态/)
})
