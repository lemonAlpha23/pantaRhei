<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { CircleAlert, Plus, RefreshCw } from 'lucide-vue-next'
import type { AlertDirection } from '../../../../shared/alerts'
import { errorText } from '../../core/http'
import { usePageWindowState } from '../../core/page-window'
import { useWorkspace } from '../market/store'
import AlertList from './AlertList.vue'
import { useAlertsStore } from './store'

const alerts = useAlertsStore()
const market = useWorkspace()
const tab = ref<'rules' | 'history'>('rules')
const symbol = ref('')
const direction = ref<AlertDirection>('above')
const target = ref('')
const initial = usePageWindowState(() => ({
  tab: tab.value, symbol: symbol.value, direction: direction.value, target: target.value,
}))
tab.value = initial.tab === 'history' ? 'history' : 'rules'
symbol.value = initial.symbol ?? ''
direction.value = initial.direction === 'below' ? 'below' : 'above'
target.value = initial.target ?? ''
watch(() => alerts.historyRequested, requested => {
  if (requested) {
    tab.value = 'history'
    alerts.historyRequested = false
  }
}, { immediate: true })

watch(() => market.instruments, catalog => {
  if (catalog.length && !catalog.some(stock => stock.symbol === symbol.value)) {
    symbol.value = (catalog.find(stock => stock.symbol === market.selected) ?? catalog[0]).symbol
  }
}, { immediate: true })

const busy = ref('')
const formError = ref('')
const actionError = ref('')
const feedback = ref('')
const enabled = computed(() => alerts.snapshot?.rules.some(rule => rule.enabled) ?? false)
const read = async () => {
  actionError.value = ''
  try {
    await alerts.getAlerts()
  } catch (error) {
    actionError.value = errorText(error, '提醒读取失败，请重试。')
  }
}
onMounted(read)

const act = async (key: string, operation: () => Promise<unknown>) => {
  if (busy.value) return
  busy.value = key
  feedback.value = ''
  actionError.value = ''
  try {
    await operation()
  } catch (error) {
    actionError.value = errorText(error, '操作失败，请重试。')
  } finally {
    busy.value = ''
  }
}
const create = () => {
  const amount = Number(target.value)
  if (!symbol.value || !/^(?:\d+(?:\.\d{0,2})?|\.\d{1,2})$/.test(target.value.trim()) ||
    amount <= 0 || amount > 999999.99) {
    formError.value = '请输入 0.01 至 999999.99 元之间的价格，最多两位小数。'
    return
  }
  const rule = { symbol: symbol.value, direction: direction.value, target: amount }
  void act('create', async () => {
    await alerts.createAlert(rule)
    target.value = ''
    tab.value = 'rules'
    feedback.value = '提醒已创建。'
  })
}
const toggle = (id: number, next: boolean) => act('toggle', () => alerts.setAlertEnabled(id, next))
const remove = (id: number) => act('delete', () => alerts.deleteAlert(id))
const check = () => act('check', async () => {
  const previous = alerts.snapshot?.events[0]?.id
  const { rules, evaluated } = await alerts.checkAlerts()
  if (!rules) feedback.value = '当前没有已启用的规则。'
  else if (!evaluated) feedback.value = '暂未取得可用于判断的新报价。'
  else {
    const result = alerts.snapshot?.events[0]?.id === previous ? '没有新增触发记录。' : '有新的触发记录。'
    feedback.value = evaluated < rules ? `已检查 ${evaluated} / ${rules} 条规则，${result}` : result
  }
})
</script>

<template>
  <section class="alerts-view" aria-labelledby="alerts-title">
    <header class="heading">
      <div><h1 id="alerts-title">价格提醒</h1><p>应用运行时每 30 秒检查报价，达到目标价后提醒一次。</p></div>
      <button type="button" class="action" aria-label="立即检查" :disabled="!enabled || !!busy" @click="check">
        <RefreshCw :size="15" :class="{ spin: busy === 'check' }" />{{ busy === 'check' ? '检查中' : '立即检查' }}
      </button>
    </header>
    <div v-if="actionError" role="alert" class="alert-message">
      <CircleAlert :size="16" />{{ actionError }}
      <button v-if="!alerts.snapshot" type="button" @click="read">重新读取</button>
    </div>
    <p v-if="feedback" role="status" class="feedback">{{ feedback }}</p>

    <div class="content">
      <aside class="editor panel" aria-labelledby="new-alert">
        <h2 id="new-alert">新建提醒</h2>
        <form novalidate @submit.prevent="create">
          <label class="field"><span>股票</span>
            <select v-model="symbol" aria-label="股票" :disabled="!!busy || !market.instruments.length">
              <option v-if="!market.instruments.length" value="">{{ market.starting ? '正在读取股票库' : '暂无可选股票' }}</option>
              <option v-for="stock in market.instruments" :key="stock.symbol" :value="stock.symbol">{{ stock.name }} · {{ stock.symbol }}</option>
            </select>
          </label>
          <fieldset :disabled="!!busy"><legend>触发条件</legend>
            <div class="conditions">
              <button type="button" :aria-pressed="direction === 'above'" @click="direction = 'above'">达到或高于</button>
              <button type="button" :aria-pressed="direction === 'below'" @click="direction = 'below'">达到或低于</button>
            </div>
          </fieldset>
          <label class="field"><span>目标价</span>
            <span class="amount"><input v-model="target" aria-label="目标价" :aria-invalid="!!formError"
              :aria-describedby="formError ? 'target-error' : undefined" :disabled="!!busy" inputmode="decimal"
              placeholder="0.00" maxlength="16" autocomplete="off" @input="formError = ''" /><span>元</span></span>
          </label>
          <p v-if="formError" id="target-error" role="alert" class="invalid">{{ formError }}</p>
          <button v-if="market.startupError" type="button" class="action" @click="market.initialize">重新读取股票库</button>
          <button type="submit" class="action primary" :disabled="!symbol || !market.instruments.length || !!busy || !alerts.snapshot">
            <Plus :size="16" />{{ busy === 'create' ? '正在创建' : '创建提醒' }}
          </button>
        </form>
      </aside>

      <section class="ledger" aria-label="提醒管理">
        <div class="tabs" role="group" aria-label="提醒视图">
          <button type="button" aria-label="提醒规则" :aria-pressed="tab === 'rules'" @click="tab = 'rules'">提醒规则
            <span v-if="alerts.snapshot">{{ alerts.snapshot.rules.length }}</span></button>
          <button type="button" aria-label="触发记录" :aria-pressed="tab === 'history'" @click="tab = 'history'">触发记录
            <span v-if="alerts.snapshot">{{ alerts.snapshot.events.length }}</span></button>
        </div>
        <AlertList v-if="alerts.snapshot" :snapshot="alerts.snapshot" :tab="tab" :busy="!!busy" @toggle="toggle" @remove="remove" />
        <div v-else-if="!actionError" class="empty" role="status">正在读取提醒</div>
      </section>
    </div>
  </section>
</template>

<style scoped lang="scss">
.heading {
  display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 14px; margin-bottom: 28px;
  h1 { font-size: clamp(30px, 3vw, 44px); font-weight: 550; letter-spacing: -.05em; }
  p { margin-top: 3px; color: var(--muted); font-size: 14px; }
}
.content { display: grid; grid-template-columns: minmax(0, 1fr) minmax(265px, 310px); align-items: start; gap: clamp(24px, 3.4vw, 52px); }
.editor {
  grid-column: 2; grid-row: 1; padding: 23px; h2 { margin-bottom: 19px; }
  form { display: grid; gap: 17px; }
  .primary { margin-top: 4px; min-height: 41px; }
}
.field { display: grid; gap: 7px; > span:first-child { font-size: 13px; font-weight: 550; } }
select, .amount {
  width: 100%; height: 42px; padding: 0 11px; border: 1px solid var(--line); border-radius: 9px; color: var(--text);
  background: var(--surface); font: inherit; font-size: 14px;
}
select:focus-visible, .amount:focus-within { outline: 2px solid var(--primary); outline-offset: 2px; }
.amount {
  display: flex; align-items: center; gap: 8px;
  input { width: 100%; min-width: 0; padding: 0; border: 0; background: transparent; color: var(--text); outline: 0; }
  > span { color: var(--muted); font-size: 13px; }
}
fieldset { min-width: 0; margin: 0; padding: 0; border: 0; legend { margin-bottom: 7px; padding: 0; font-size: 13px; font-weight: 550; } }
.conditions { display: grid; grid-template-columns: 1fr 1fr; gap: 4px; padding: 4px; background: var(--soft); border-radius: 10px;
  button { min-height: 32px; padding: 0 4px; border-radius: 7px; color: var(--muted); font-size: 13px; }
  [aria-pressed=true] { color: var(--primary); background: var(--surface); box-shadow: 0 1px 3px rgb(16 24 40 / 12%); font-weight: 550; }
}
.invalid { margin-top: -9px; color: var(--up); font-size: 12px; }
.ledger { grid-column: 1; grid-row: 1; min-width: 0; }
.tabs {
  display: flex; gap: 23px; margin-bottom: 4px; border-bottom: 1px solid var(--line);
  button { display: flex; align-items: center; gap: 7px; margin-bottom: -1px; padding: 8px 0 14px; border-bottom: 2px solid transparent;
    color: var(--muted); font-size: 16px; font-weight: 550; }
  [aria-pressed=true] { color: var(--text); border-color: var(--primary); }
  span { padding: 0 6px; border-radius: 5px; background: var(--soft); font-size: 12px; font-variant-numeric: tabular-nums; }
}
.alert-message, .feedback { margin-bottom: 15px; font-size: 13px; color: var(--muted); }
.alert-message { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; padding: 10px 12px; background: var(--soft); border-radius: 9px;
  button { padding: 0; color: var(--primary); }
}
.spin { animation: rotate 1s linear infinite; } @keyframes rotate { to { transform: rotate(360deg); } }
@media (max-width: 880px) {
  .content { display: flex; flex-direction: column; gap: 23px; }
  .editor, .ledger { width: 100%; }
  .editor { padding: 18px; h2 { margin-bottom: 14px; } }
  .editor form { grid-template-columns: 1fr 1fr; align-items: end; gap: 12px 15px; .primary { margin: 0; } }
}
@media (max-width: 540px) {
  .heading { margin-bottom: 18px; align-items: start; p { font-size: 13px; } }
  .editor form { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
  .field:first-child, fieldset, .invalid { grid-column: 1 / -1; }
  .editor .primary { grid-column: 2; grid-row: 3; }
}
</style>
