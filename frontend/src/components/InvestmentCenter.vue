<script setup>
import { ref, watch } from 'vue'
const props = defineProps({ token: { type: String, default: '' } })
const products = ref([]), portfolio = ref([]), orders = ref([])
const prompt = ref('比较现有模拟理财产品')
const status = ref(''), error = ref(''), report = ref(null), loading = ref(false)
const scores = ref({ lossTolerance: 1, horizon: 1, experience: 1 })
const risk = ref(null)
const pendingRequestId = ref('')
const base = '/api/agent/investments'

async function api(path, method = 'GET', body) {
  if (!props.token) throw new Error('请先登录模拟银行')
  const res = await fetch(base + path, {
    method,
    headers: { Authorization: `Bearer ${props.token}`, 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body)
  })
  const value = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(`银行请求失败 (${res.status})；请查询原订单，不要重复提交。`)
  return value
}
async function refresh() {
  if (!props.token) return
  loading.value = true; error.value = ''
  try {
    const [p, h, o] = await Promise.all([api('/products'), api('/portfolio'), api('/orders')])
    products.value = p; portfolio.value = h; orders.value = o
    try { risk.value = await api('/profile') } catch { risk.value = null }
  } catch (e) { error.value = e.message } finally { loading.value = false }
}
async function assess() {
  loading.value = true; error.value = ''
  try { risk.value = await api('/profile/assess', 'POST', scores.value) }
  catch (e) { error.value = e.message } finally { loading.value = false }
}
async function start() {
  if (loading.value) return
  loading.value = true; error.value = ''; status.value = ''; report.value = null
  // Keep a stable key in component memory if an HTTP response is lost.
  if (!pendingRequestId.value) pendingRequestId.value = crypto.randomUUID().replaceAll('-', '')
  try {
    report.value = await api('/start', 'POST', { message: prompt.value, requestId: pendingRequestId.value })
    status.value = report.value.status || ''
    if (status.value !== 'WAITING_INVESTMENT_APPROVAL') pendingRequestId.value = ''
  } catch (e) {
    error.value = `${e.message} 原申请编号已保留，请先查询订单。`
  } finally { loading.value = false }
}
async function decision(approved) {
  if (loading.value || status.value !== 'WAITING_INVESTMENT_APPROVAL') return
  loading.value = true; error.value = ''
  try {
    report.value = await api('/resume', 'POST', { threadId: report.value.threadId, approved })
    status.value = report.value.status
    pendingRequestId.value = ''
    await refresh()
  } catch (e) { error.value = e.message } finally { loading.value = false }
}
function newRequest() {
  if (status.value === 'WAITING_INVESTMENT_APPROVAL') return
  pendingRequestId.value = ''; report.value = null; status.value = ''; error.value = ''
}
watch(() => props.token, () => {
  products.value = []; portfolio.value = []; orders.value = []; risk.value = null
  report.value = null; status.value = ''; pendingRequestId.value = ''
  if (props.token) refresh()
}, { immediate: true })
</script>

<template>
  <section class="investment-center" aria-label="模拟理财中心">
    <h3>理财中心（仅模拟）</h3>
    <p>固定演示净值，无真实收益、保本承诺或金融产品交易。需完成模拟风险测评；申购、赎回必须由本人确认。</p>
    <button type="button" :disabled="loading || !token" @click="refresh">刷新理财数据</button>
    <p v-if="error" role="alert">{{ error }}</p>
    <div v-if="!risk">
      <h4>模拟适当性测评</h4>
      <label>亏损承受程度<select v-model.number="scores.lossTolerance"><option :value="1">低</option><option :value="2">中</option><option :value="3">高</option></select></label>
      <label>投资期限<select v-model.number="scores.horizon"><option :value="1">短</option><option :value="2">中</option><option :value="3">长</option></select></label>
      <label>风险认知<select v-model.number="scores.experience"><option :value="1">初级</option><option :value="2">中级</option><option :value="3">高级</option></select></label>
      <button :disabled="loading" type="button" @click="assess">提交模拟测评</button>
    </div>
    <p v-else>当前模拟风险等级：R{{ risk.riskLevel }}</p>
    <h4>产品比较</h4>
    <table><thead><tr><th>名称</th><th>风险</th><th>模拟单位净值</th></tr></thead><tbody>
      <tr v-for="p in products" :key="p.productId"><td>{{ p.name }}</td><td>R{{ p.riskLevel }}</td><td>¥{{ p.nav }}</td></tr>
    </tbody></table>
    <h4>当前持仓</h4>
    <p v-if="!portfolio.length">暂无模拟持仓</p>
    <p v-for="x in portfolio" :key="x.productId">{{ x.productName }}：{{ x.units }} 份；演示市值 ¥{{ x.demoMarketValue }}</p>
    <h4>自然语言理财办理（独立受控工作流）</h4>
    <textarea v-model="prompt" rows="2" placeholder="例如：申购稳健模拟理财10份" :disabled="loading || status === 'WAITING_INVESTMENT_APPROVAL'" />
    <div><button type="button" :disabled="loading || !token || status === 'WAITING_INVESTMENT_APPROVAL'" @click="start">分析 / 创建待确认订单</button>
      <button type="button" :disabled="loading || status === 'WAITING_INVESTMENT_APPROVAL'" @click="newRequest">新申请</button></div>
    <p v-if="status">工作流：{{ status }}；{{ report?.details }}</p>
    <div v-if="status === 'WAITING_INVESTMENT_APPROVAL' && report?.order">
      <strong>银行待确认订单 #{{ report.order.orderId }}</strong>
      <p>{{ report.order.productName }}，{{ report.order.action === 'BUY' ? '申购' : '赎回' }} {{ report.order.units }} 份，模拟金额 ¥{{ report.order.amount }}；风险 R{{ report.order.riskLevel }}</p>
      <p>仅在您核对订单后点击；模型不能替您批准。页面关闭后，请从银行订单列表查询原单。</p>
      <button type="button" :disabled="loading" @click="decision(true)">我确认，执行模拟交易</button>
      <button type="button" :disabled="loading" @click="decision(false)">拒绝 / 取消</button>
    </div>
    <pre v-if="report?.result">{{ JSON.stringify(report.result, null, 2) }}</pre>
    <h4>最近银行订单（由 Java 返回）</h4>
    <p v-for="o in orders" :key="o.orderId">#{{ o.orderId }} {{ o.productName }} {{ o.action }} {{ o.units }} 份 — {{ o.status }}</p>
  </section>
</template>
<style scoped>
.investment-center { border:1px solid #d6dce4;border-radius:12px;padding:16px;margin:12px 0;display:grid;gap:8px }
.investment-center table{width:100%;border-collapse:collapse;text-align:left}
.investment-center th,.investment-center td{border-bottom:1px solid #e5e7eb;padding:6px}
.investment-center textarea {width:100%;font:inherit}
.investment-center button {margin-right:8px;padding:6px 10px}
.investment-center p {margin:4px 0}
</style>
