<script setup lang="ts">
import { onMounted, reactive, ref, shallowRef } from 'vue'
import { CheckCircle2, CircleAlert, KeyRound, Webhook } from 'lucide-vue-next'
import type { XConnection, XSettings, XSettingsPatch } from '../../../../shared/xmonitor'
import { errorText } from '../../core/http'
import { useWindowUpdates } from '../../core/window-updates'
import { xApi } from './api'

const emit = defineEmits<{ saved: [] }>()
type Field = keyof XSettingsPatch
const groups = [
  { id: 'x', name: 'X API', icon: KeyRound, description: '读取已订阅博主的公开动态。', fields: ['xToken'] },
  { id: 'webhook', name: 'Webhook', icon: Webhook, description: '将新交易线索发送到你的 HTTPS 接收端。', fields: ['webhookUrl', 'webhookToken'] },
] as const
const labels: Record<Field, string> = { xToken: 'X Bearer Token', webhookUrl: 'HTTPS 接收地址', webhookToken: 'Webhook Token' }
const sources = { saved: '本机已保存', environment: '环境变量', none: '未配置' }
const settings = shallowRef<XSettings>()
const drafts = reactive<XSettingsPatch>({})
const draftVersions: Partial<Record<XConnection, number>> = {}
const feedback = reactive<Partial<Record<XConnection, { ok: boolean; text: string }>>>({})
const loadError = ref('')
const working = ref('')
let version = 0

const load = async () => {
  const ticket = ++version
  try {
    const data = await xApi.getSettings()
    if (ticket === version) {
      if (settings.value && data.revision !== settings.value.revision) {
        delete feedback.x
        delete feedback.webhook
      }
      settings.value = data
      loadError.value = ''
    }
  } catch (error) {
    if (ticket === version) loadError.value = errorText(error, '连接配置读取失败。')
  }
}
const publish = useWindowUpdates('x-connection-settings', load)
onMounted(load)
const changed = (fields: readonly Field[]) => fields.some(field => drafts[field] !== undefined)
const canSave = (fields: readonly Field[]) => changed(fields) && !working.value &&
  (settings.value?.storageAvailable || fields.every(field => drafts[field] == null))
const stage = (id: XConnection, field: Field, value: string | null | undefined) => {
  if (!settings.value) return
  if (value === undefined) delete drafts[field]
  else {
    draftVersions[id] ??= settings.value.revision
    drafts[field] = value
  }
  const group = groups.find(item => item.id === id)!
  if (!changed(group.fields)) delete draftVersions[id]
  delete feedback[id]
}
const input = (id: XConnection, field: Field, event: Event) => {
  const value = (event.target as HTMLInputElement).value
  stage(id, field, value || undefined)
}
const toggleReset = (id: XConnection, field: Field) => {
  stage(id, field, drafts[field] === null ? undefined : null)
}
const placeholder = (field: Field) => {
  if (drafts[field] === null) return '保存后移除本机值'
  if (field === 'webhookUrl') return settings.value?.webhookUrl.configured ? '输入新接收地址' : 'https://'
  return settings.value?.[field].configured ? '••••••••' : '输入令牌'
}
const save = async (id: XConnection, fields: readonly Field[]) => {
  const expected = draftVersions[id]
  if (working.value || expected === undefined) return
  const clearDraft = () => {
    for (const field of fields) delete drafts[field]
    delete draftVersions[id]
  }
  const conflict = () => {
    if (!settings.value || settings.value.revision === expected) return false
    clearDraft()
    feedback[id] = { ok: false, text: '连接配置已更改，请核对当前配置后重新输入。' }
    return true
  }
  if (conflict()) return
  const patch: XSettingsPatch = {}
  for (const field of fields) {
    const value = drafts[field]
    if (value === undefined) continue
    if (typeof value === 'string' && !value.trim()) {
      feedback[id] = { ok: false, text: labels[field] + ' 不能为空白。' }
      return
    }
    patch[field] = value?.trim() ?? null
  }
  working.value = 'save-' + id
  delete feedback[id]
  try {
    const result = await xApi.saveSettings(patch, expected)
    ++version
    settings.value = result
    clearDraft()
    const other = id === 'x' ? 'webhook' : 'x'
    if (draftVersions[other] === expected) draftVersions[other] = result.revision
    feedback[id] = { ok: true, text: '配置已保存。' }
    emit('saved')
    publish('settings')
  } catch (error) {
    await load()
    if (!conflict()) feedback[id] = { ok: false, text: errorText(error, '配置保存失败。') }
  }
  finally { working.value = '' }
}
const clock = new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
const test = async (id: XConnection) => {
  if (working.value) return
  const testedRevision = settings.value?.revision
  working.value = 'test-' + id
  delete feedback[id]
  try {
    const result = await xApi.testConnection(id)
    if (settings.value?.revision !== testedRevision) return
    const time = Date.parse(result.testedAt)
    feedback[id] = { ok: result.ok, text: result.message + (Number.isFinite(time) ? ' · ' + clock.format(time) : '') }
  } catch (error) {
    if (settings.value?.revision === testedRevision) feedback[id] = { ok: false, text: errorText(error, '连接测试失败。') }
  }
  finally { working.value = '' }
}
</script>

<template>
  <div v-if="loadError" class="load-error" role="alert">{{ loadError }} <button type="button" @click="load">重新读取</button></div>
  <div v-if="!settings && !loadError" class="empty" role="status">正在读取配置</div>
  <template v-if="settings">
    <p v-if="!settings.storageAvailable" class="load-error">系统安全存储不可用，当前可通过环境变量配置连接。</p>
    <div class="connections">
      <form v-for="group in groups" :key="group.id" :aria-label="group.name + ' 配置'" class="connection panel"
        autocomplete="off" @submit.prevent="save(group.id, group.fields)">
        <div class="title"><span class="icon"><component :is="group.icon" :size="18" /></span><h2>{{ group.name }}</h2></div>
        <p class="description">{{ group.description }}</p>
        <div class="fields">
          <div v-for="field in group.fields" :key="field" class="field">
            <div class="label"><label :for="'x-config-' + field">{{ labels[field] }}</label><small v-if="field === 'webhookToken'">可选</small></div>
            <input :id="'x-config-' + field" type="password" :aria-label="labels[field]" :value="drafts[field] ?? ''"
              :placeholder="placeholder(field)" :disabled="!!working || !settings.storageAvailable || drafts[field] === null"
              autocomplete="new-password" spellcheck="false" maxlength="8192" @input="input(group.id, field, $event)" />
            <div class="field-meta">
              <span><i :class="{ ready: settings[field].configured }"></i>{{ settings[field].source === 'saved' && !settings[field].configured ? '本机值无法解锁' : sources[settings[field].source] }}<template v-if="field === 'webhookUrl' && settings.webhookUrl.host"> · {{ settings.webhookUrl.host }}</template></span>
              <button v-if="settings[field].source === 'saved'" type="button" :disabled="!!working"
                :aria-label="(drafts[field] === null ? '撤销移除 ' : '移除本机 ') + labels[field]" @click="toggleReset(group.id, field)">
                {{ drafts[field] === null ? '撤销移除' : '移除本机值' }}
              </button>
            </div>
          </div>
        </div>
        <p v-if="group.id === 'webhook' && drafts.webhookUrl" class="hint">新接收地址如需鉴权，请同时填写该地址的 Token。</p>
        <p v-if="group.fields.some(field => drafts[field] === null)" class="hint">保存后将采用可用的环境配置。</p>
        <footer>
          <p v-if="feedback[group.id]" class="result" :class="{ success: feedback[group.id]?.ok }" aria-live="polite">
            <component :is="feedback[group.id]?.ok ? CheckCircle2 : CircleAlert" :size="15" />{{ feedback[group.id]?.text }}
          </p>
          <p class="hint">{{ changed(group.fields) ? '保存修改后即可测试。' : group.id === 'webhook' ? '测试会向接收端发送一条连接测试事件。' : '测试使用当前令牌查询公开账号。' }}</p>
          <div class="actions">
            <button class="action primary" type="submit" :aria-label="'保存 ' + group.name + ' 配置'"
              :disabled="!canSave(group.fields)">{{ working === 'save-' + group.id ? '保存中' : '保存配置' }}</button>
            <button class="action" type="button" :aria-label="'测试 ' + group.name + ' 连接'"
              :disabled="changed(group.fields) || !!working || !(group.id === 'x' ? settings.xToken.configured : settings.webhookUrl.configured)"
              @click="test(group.id)">{{ working === 'test-' + group.id ? '测试中' : '测试连接' }}</button>
          </div>
        </footer>
      </form>
    </div>
  </template>
</template>

<style scoped lang="scss">
.connections { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; }
.connection { display: flex; flex-direction: column; margin: 0; padding: clamp(18px, 2.3vw, 30px); }
.title, .label, .actions, .field-meta, .result { display: flex; align-items: center; gap: 8px; }
.icon { display: grid; place-items: center; width: 32px; height: 32px; background: var(--soft); border-radius: 10px; }
.description { margin-top: 9px; color: var(--muted); font-size: 14px; }
.fields { margin: 22px 0 14px; display: grid; gap: 16px; }
label { font-weight: 550; font-size: 14px; }
small, .field-meta, .hint { font-size: 12px; color: var(--muted); }
input { width: 100%; min-width: 0; height: 40px; margin-top: 7px; padding: 0 12px; border: 1px solid var(--line); border-radius: 9px; background: var(--surface); color: var(--text); }
input:disabled { background: var(--soft); }
.field-meta { justify-content: space-between; flex-wrap: wrap; margin: 5px 0 0; overflow-wrap: anywhere;
  i { display: inline-block; width: 6px; height: 6px; margin-right: 5px; border-radius: 50%; background: var(--dim); }
  i.ready { background: var(--down); }
  button { padding: 2px 0; color: var(--muted); font-size: 12px; text-decoration: underline; text-underline-offset: 2px; }
}
footer { margin-top: auto; padding-top: 15px; }
.actions { margin-top: 10px; }
.result { margin-bottom: 10px; color: var(--up); font-size: 13px; overflow-wrap: anywhere; }
.success { color: var(--down); }
.load-error { margin-bottom: 14px; color: var(--muted); font-size: 13px; button { color: var(--primary); } }
@media (max-width: 760px) { .connections { grid-template-columns: minmax(0, 1fr); gap: 14px; } }
</style>
