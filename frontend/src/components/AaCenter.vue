<script setup>
import { onMounted, onUnmounted, ref } from 'vue'

const props = defineProps({ fetcher: { type: Function, required: true }, userId: { type: Number, required: true } })
const open = ref(false)
const incoming = ref([])
const outgoing = ref([])
const busy = ref(false)
const error = ref('')
const action = ref({})
let alive = true
const money = value => Number.isFinite(Number(value)) ? new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY' }).format(Number(value)) : '—'
const uid = () => crypto.randomUUID()
const state = id => action.value[id] || null
function mark(id, change) { action.value = { ...action.value, [id]: { ...(action.value[id] || {}), ...change } } }
const states = { PENDING: '待付款', PAYING: '银行审批中', PAID: '已支付', DECLINED: '已拒绝', FAILED: '付款失败' }

async function refresh() {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    const [a, b] = await Promise.all([props.fetcher('/api/agent/aa/inbox'), props.fetcher('/api/agent/aa/outgoing')])
    if (!alive) return
    incoming.value = a
    outgoing.value = b
    for (const item of a) {
      if (item.status === 'PAID' || item.status === 'DECLINED' || item.status === 'FAILED') mark(item.itemId, { order: null, uncertain: false })
    }
  } catch (e) { if (alive) error.value = `获取 AA 数据失败：${e.message}` }
  finally { if (alive) busy.value = false }
}

async function prepare(item) {
  if (busy.value || state(item.itemId)?.uncertain) return
  busy.value = true; error.value = ''
  const key = state(item.itemId)?.prepareKey || uid()
  mark(item.itemId, { prepareKey: key })
  try {
    const order = await props.fetcher(`/api/agent/aa/items/${encodeURIComponent(item.itemId)}/payment/prepare`, 'POST', { requestId: key })
    if (alive) mark(item.itemId, { order, confirmed: false, otp: '', otpRequested: false })
    if (alive) await loadAfterAction()
  } catch (e) { if (alive) fail(item.itemId, e, '准备付款') }
  finally { if (alive) busy.value = false }
}
async function restore(item) {
  if (busy.value) return
  busy.value = true; error.value = ''
  try {
    const order = await props.fetcher(`/api/agent/aa/items/${encodeURIComponent(item.itemId)}/payment`)
    if (alive) mark(item.itemId, { order, uncertain: order.status !== 'PENDING_APPROVAL' })
  } catch (e) { if (alive) fail(item.itemId, e, '恢复付款订单') }
  finally { if (alive) busy.value = false }
}
async function loadAfterAction() {
  const [a, b] = await Promise.all([props.fetcher('/api/agent/aa/inbox'), props.fetcher('/api/agent/aa/outgoing')])
  if (alive) { incoming.value = a; outgoing.value = b }
}
function fail(id, e, label) {
  error.value = `${label}失败：${e.message}`
  if (e.uncertain || e.httpStatus === 409 || e.httpStatus >= 500) {
    mark(id, { uncertain: true })
    error.value += ' 处理结果可能已变化，请刷新并核查原银行订单，不要重复支付。'
  }
}
async function requestOtp(item) {
  if (busy.value || state(item.itemId)?.uncertain) return
  busy.value = true; error.value = ''
  try {
    await props.fetcher(`/api/agent/aa/items/${encodeURIComponent(item.itemId)}/otp/request`, 'POST', {})
    if (alive) mark(item.itemId, { otpRequested: true })
  } catch (e) { if (alive) fail(item.itemId, e, '申请验证码') }
  finally { if (alive) busy.value = false }
}
async function pay(item) {
  const data = state(item.itemId)
  if (busy.value || !data?.confirmed || data?.uncertain || !data?.order) return
  if (data.order.riskLevel === 'RED' && (!data.otpRequested || !/^\d{6}$/.test(data.otp || ''))) {
    error.value = 'RED 风险请先申请并输入六位 OTP。'; return
  }
  busy.value = true; error.value = ''
  const key = data.confirmKey || uid()
  mark(item.itemId, { confirmKey: key })
  try {
    await props.fetcher(`/api/agent/aa/items/${encodeURIComponent(item.itemId)}/payment/confirm`, 'POST',
      { requestId: key, confirmed: true, otpCode: data.order.riskLevel === 'RED' ? data.otp : null }, 90000)
    if (alive) { mark(item.itemId, { order: null, otp: '', confirmed: false }); await loadAfterAction() }
  } catch (e) { if (alive) fail(item.itemId, e, '确认付款') }
  finally { if (alive) busy.value = false }
}
async function decline(item) {
  if (busy.value || state(item.itemId)?.uncertain) return
  busy.value = true; error.value = ''
  const key = state(item.itemId)?.declineKey || uid()
  mark(item.itemId, { declineKey: key })
  try {
    await props.fetcher(`/api/agent/aa/items/${encodeURIComponent(item.itemId)}/decline`, 'POST', { requestId: key })
    if (alive) await loadAfterAction()
  } catch (e) { if (alive) fail(item.itemId, e, '拒绝请求') }
  finally { if (alive) busy.value = false }
}
function toggle() { open.value = !open.value; if (open.value) refresh() }
onMounted(refresh)
onUnmounted(() => { alive = false })
defineExpose({ refresh })
</script>

<template>
  <section class="aa-center" aria-label="AA 收付款中心">
    <div class="aa-top">
      <div class="aa-head"><span class="aa-icon">◎</span><div><strong>AA 收付款</strong><small>查看别人向你发起的请求，以及你的收款进度</small></div></div>
      <div class="aa-tools"><span class="aa-count">{{ incoming.filter(x => x.status === 'PENDING' || x.status === 'PAYING').length }} 项待处理</span><button type="button" @click="toggle">{{ open ? '收起' : '查看请求' }}</button></div>
    </div>
    <div v-if="open" class="aa-body">
      <div v-if="error" class="aa-error" role="alert">{{ error }}</div>
      <button class="aa-refresh" type="button" :disabled="busy" @click="refresh">{{ busy ? '处理中…' : '刷新银行状态' }}</button>
      <h3>发给我的付款请求</h3>
      <p v-if="!incoming.length" class="aa-empty">暂无 AA 付款请求。</p>
      <article v-for="item in incoming" :key="item.itemId" class="aa-entry">
        <div class="aa-entry-top"><div><strong>{{ item.initiatorName }} 发起的收款</strong><small>{{ item.reason || 'AA 费用' }}</small></div><span class="aa-state">{{ states[item.status] || item.status }}</span></div>
        <div class="aa-amount">{{ money(item.amount) }}</div>
        <template v-if="item.status === 'PENDING' && !state(item.itemId)?.order">
          <div class="aa-actions"><button type="button" :disabled="busy || state(item.itemId)?.uncertain" @click="prepare(item)">查看并准备付款</button><button class="outline" type="button" :disabled="busy || state(item.itemId)?.uncertain" @click="decline(item)">拒绝</button></div>
        </template>
        <template v-if="item.status === 'PAYING' || state(item.itemId)?.order">
          <div v-if="state(item.itemId)?.order" class="aa-approval">
            <p>付款对象：{{ item.initiatorName }} · 银行风控：<strong>{{ state(item.itemId).order.riskLevel }}</strong></p>
            <button v-if="state(item.itemId).order.riskLevel === 'RED'" class="outline" type="button" :disabled="busy || state(item.itemId)?.uncertain" @click="requestOtp(item)">向银行申请 OTP</button>
            <input v-if="state(item.itemId).order.riskLevel === 'RED'" :value="state(item.itemId).otp || ''" inputmode="numeric" maxlength="6" placeholder="输入六位 OTP" aria-label="AA 付款验证码" @input="mark(item.itemId,{otp:$event.target.value})" />
            <label class="aa-check"><input type="checkbox" :checked="!!state(item.itemId).confirmed" @change="mark(item.itemId,{confirmed:$event.target.checked})" />我确认由本人账户向 {{ item.initiatorName }} 支付 {{ money(item.amount) }}</label>
            <div class="aa-actions"><button type="button" :disabled="busy || state(item.itemId)?.uncertain || !state(item.itemId)?.confirmed" @click="pay(item)">确认银行付款</button><button class="outline" type="button" :disabled="busy || state(item.itemId)?.uncertain" @click="decline(item)">放弃付款</button></div>
          </div>
          <div v-else><p class="aa-empty">已创建原银行转账订单，请先恢复并核对该订单，不要重新建单。</p><button class="aa-refresh" type="button" :disabled="busy" @click="restore(item)">恢复原付款订单</button></div>
        </template>
        <small v-if="item.transferOrderId" class="aa-order">关联转账订单：{{ item.transferOrderId }}</small>
      </article>
      <h3>我发起的收款</h3>
      <p v-if="!outgoing.length" class="aa-empty">暂无已发布的 AA 收款单。</p>
      <article v-for="record in outgoing" :key="record.collectionId" class="aa-entry">
        <div class="aa-entry-top"><div><strong>{{ record.reason || 'AA 收款' }}</strong><small>银行收款单：{{ record.collectionId }}</small></div><span class="aa-state">{{ record.status }}</span></div>
        <p class="aa-total">实际已收 <strong>{{ money(record.receivedAmount) }}</strong> / {{ money(record.requestedAmount) }}</p>
        <div v-for="person in record.items" :key="person.itemId" class="aa-person"><span>{{ person.payerName }} · {{ money(person.amount) }}</span><span>{{ states[person.status] || person.status }}</span></div>
      </article>
    </div>
  </section>
</template>

<style scoped>
.aa-center{margin:8px 0 24px;border:1px solid #dce7f5;border-radius:18px;background:linear-gradient(130deg,#fff,#f4f9ff);box-shadow:0 8px 22px #10294909;max-width:760px}
.aa-top,.aa-entry-top{display:flex;justify-content:space-between;align-items:center;gap:16px}.aa-top{padding:17px 20px}.aa-head{display:flex;align-items:center;gap:12px}.aa-icon{width:39px;height:39px;display:grid;place-items:center;border-radius:12px;background:#e6f1ff;color:#2275da;font-size:25px}.aa-head>div,.aa-entry-top>div{display:grid;gap:4px}.aa-head strong{font-size:14px;color:#1a3454}.aa-head small,.aa-entry-top small{font-size:11px;color:#899ab0}.aa-tools{display:flex;align-items:center;gap:10px}.aa-count,.aa-state{font-size:11px;background:#eaf2ff;color:#366da7;border-radius:9px;padding:6px 8px;white-space:nowrap}.aa-tools button,.aa-actions button,.aa-approval>button,.aa-refresh{border:0;border-radius:9px;background:#2378da;color:#fff;font-size:12px;font-weight:700;padding:10px 13px;cursor:pointer}.aa-body{border-top:1px solid #e9eff7;padding:15px 20px 20px;display:grid;gap:12px}.aa-body h3{font-size:13px;color:#1b3557;margin:14px 0 2px}.aa-refresh{justify-self:start;background:#e9f1fb;color:#376997}.aa-entry{border:1px solid #e4ebf5;border-radius:13px;background:#fff;padding:16px;display:grid;gap:11px}.aa-entry-top strong{font-size:13px;color:#243d59}.aa-amount{font-size:24px;color:#1f69c3;font-weight:800}.aa-actions{display:flex;gap:9px;flex-wrap:wrap}.aa-actions .outline,.aa-approval button.outline{background:#f1f6fd;color:#386d9f}.aa-approval{padding:12px;border-radius:10px;background:#f7faff;display:grid;gap:10px;font-size:12px;color:#4d6787}.aa-approval p{margin:0}.aa-approval input:not([type=checkbox]){border:1px solid #cfddec;border-radius:8px;padding:9px;max-width:220px}.aa-check{display:flex;gap:9px;align-items:flex-start;line-height:1.5}.aa-check input{margin-top:3px}.aa-total{font-size:12px;color:#71859d;margin:0}.aa-total strong{font-size:19px;color:#2073c8}.aa-person{display:flex;justify-content:space-between;gap:12px;font-size:12px;border-top:1px solid #eef2f8;padding-top:9px}.aa-error{background:#fff1f1;color:#b73535;padding:12px;border-radius:10px;font-size:12px}.aa-empty,.aa-order{font-size:11px;color:#8294aa;margin:0;overflow-wrap:anywhere}.aa-body button:disabled{cursor:not-allowed;opacity:.45}@media(max-width:650px){.aa-top{align-items:flex-start;flex-direction:column}.aa-body{padding:12px}.aa-center{margin:8px 0 18px}}
</style>
