<script setup>
import { ref, onMounted, nextTick } from 'vue'
import TransferForm from './components/TransferForm.vue'
import TransferOrderCard from './components/TransferOrderCard.vue'

const shortcuts = [
  { label: '查询余额', message: '我的余额是多少', icon: '◉' },
  { label: '交易流水', message: '查询最近交易', icon: '▤' },
  { label: '常用收款人', message: '我的常用收款人', icon: '♙' },
  { label: '订阅代扣', message: '有哪些自动扣费', icon: '▣' },
  { label: '智能转账', message: '给李四转200元', icon: '↗' },
  { label: '转账参数补全', message: '给李四转', icon: '✎' }
]

const messages = ref([{
  id: 'welcome', role: 'assistant', content: '你好，我是 BankPilot。支持四种模拟银行查询，以及自然语言创建转账待确认订单。Day 3 不执行扣款。', intent: 'welcome', data: null
}])
const input = ref('')
const authToken = ref('') // In-memory only. NEVER persist to localStorage, URL or logs.
const bankMode = ref('java')
const busy = ref(false)
const completedRequests = ref([])
const status = ref('连接检测中')
const endRef = ref(null)

function amount(value) {
  if (value === undefined || value === null || value === '') return '—'
  const num = Number(value)
  return Number.isFinite(num) ? new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY' }).format(num) : '—'
}
function dateOf(row) { return row.occurredAt ?? row.occurred_at ?? '—' }
function payeeOf(row) { return row.payeeName ?? row.payee_name ?? '—' }
function payeeAccountOf(row) { return row.payeeAccountMasked ?? row.payee_account_masked ?? '—' }
function merchantOf(row) { return row.merchantName ?? row.merchant_name ?? '—' }
function cycleOf(row) { return row.billingCycle === 'MONTHLY' ? '每月' : (row.billingCycle ?? '—') }
function nextPayOf(row) { return row.nextPayDate ?? row.next_pay_date ?? '—' }
function apiHeaders() {
  const headers = { 'Content-Type': 'application/json' }
  if (authToken.value.trim()) headers.Authorization = `Bearer ${authToken.value.trim()}`
  return headers
}
function addResponse(payload) {
  messages.value.push({ id: crypto.randomUUID(), role: 'assistant', content: payload.reply,
    intent: payload.intent, action: payload.action, data: payload.data, source: payload.source, requestId: payload.requestId })
}
function addError(message) {
  messages.value.push({ id: crypto.randomUUID(), role: 'assistant', content: `请求失败：${message}。请检查对应服务和接口授权。`, intent: 'error' })
}
async function scrollToBottom() { await nextTick(); endRef.value?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }

async function checkHealth() {
  try {
    const r = await fetch('/api/agent/health', { signal: AbortSignal.timeout(4000) })
    if (!r.ok) throw new Error('Agent service unavailable')
    const payload = await r.json()
    bankMode.value = payload.bankMode === 'mock' ? 'mock' : 'java'
    status.value = '交互服务已连接'
  } catch {
    status.value = '交互服务未连接'
  }
}

async function postJson(path, body) {
  const response = await fetch(path, { method: 'POST', headers: apiHeaders(), body: JSON.stringify(body), signal: AbortSignal.timeout(15000) })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : `HTTP ${response.status}`)
  return payload
}

async function send(message) {
  const text = String(message ?? input.value).trim()
  if (!text || busy.value) return
  input.value = ''
  const requestId = crypto.randomUUID()
  messages.value.push({ id: crypto.randomUUID(), role: 'user', content: text })
  busy.value = true
  await scrollToBottom()
  try {
    addResponse(await postJson('/api/agent/chat', { message: text, requestId }))
  } catch (err) {
    addError(err.message)
  } finally {
    busy.value = false
    await scrollToBottom()
  }
}

async function submitTransfer(form) {
  if (busy.value || completedRequests.value.includes(form.requestId)) return
  busy.value = true
  try {
    const result = await postJson('/api/agent/transfers/prepare', form)
    addResponse(result)
    completedRequests.value.push(form.requestId)
  } catch (err) {
    addError(err.message)
  } finally {
    busy.value = false
    await scrollToBottom()
  }
}

onMounted(checkHealth)
</script>

<template>
  <div class="layout">
    <aside class="sidebar">
      <div class="brand"><div class="brand-icon">B</div><div><strong>BankPilot</strong><small>AI Banking Agent</small></div></div>
      <div class="side-heading">项目进度</div>
      <div class="progress-item done">✓ Day 1 · 环境搭建</div>
      <div class="progress-item done">✓ Day 2 · 银行查询</div>
      <div class="progress-item active">● Day 3 · 转账建单</div>
      <div class="progress-item muted">○ Day 4 · 授权执行</div>
      <div class="side-note">本地银行模拟系统<br/>Day 3 仅创建待审批订单。没有真实资金流动和大模型调用。</div>
    </aside>

    <main class="main">
      <header class="header">
        <div><h1>银行智能助手</h1><p>查询模拟账户 · 创建待确认转账订单</p></div>
        <span class="server-status" :class="status === '交互服务已连接' ? 'online' : 'offline'">● {{ status }}</span>
      </header>

      <div class="dev-auth">
        <div class="dev-auth-title">本地开发登录凭证 <span>只保存在当前页面内存</span></div>
        <div class="dev-auth-form">
          <input type="password" v-model="authToken" autocomplete="off" placeholder="粘贴 Java 后端签发的测试 Bearer Token（不含 Bearer 前缀）" aria-label="测试登录凭证" />
          <button v-if="bankMode === 'mock'" type="button" @click="authToken = 'mock-day3-token'">填入 Mock 测试令牌</button>
          <span class="mode-pill">{{ bankMode === 'mock' ? 'Mock 数据 · 不连 MySQL' : 'Java 银行服务' }}</span>
        </div>
        <p>Day 3 调试专用：真实 Java 接口必须由 Spring Security 验证用户身份；禁止把 Token 存到浏览器持久化存储。</p>
      </div>

      <div class="content">
        <div class="welcome-card"><div class="welcome-kicker">BankPilot / DAY 03</div><h2>今天想办理什么？</h2><p>你可以查询银行数据，也可以说“给李四转200元”，系统会生成一张待审批订单。</p>
          <div class="shortcuts"><button v-for="shortcut in shortcuts" :key="shortcut.label" type="button" @click="send(shortcut.message)" :disabled="busy"><span>{{ shortcut.icon }}</span>{{ shortcut.label }}</button></div>
        </div>

        <div class="chat" aria-live="polite">
          <div v-for="message in messages" :key="message.id" class="message" :class="message.role">
            <div class="avatar">{{ message.role === 'assistant' ? 'B' : '我' }}</div>
            <div class="message-body">
              <div class="bubble">{{ message.content }}</div>
              <div v-if="message.intent === 'balance' && message.data" class="data-panel balance-panel">
                <div class="panel-subtitle">模拟账户余额</div>
                <strong>{{ amount(message.data.balance) }}</strong>
                <div class="subline">{{ message.data.userName || '当前用户' }} · {{ message.data.accountNoMasked || '****' }}</div>
              </div>
              <div v-if="message.intent === 'transactions' && Array.isArray(message.data)" class="data-panel">
                <div class="panel-subtitle">最近交易（最多 100 条）</div>
                <div v-if="!message.data.length" class="empty">暂无交易记录</div>
                <div v-for="(t, index) in message.data" :key="t.id ?? index" class="list-row">
                  <div><div class="row-title">{{ merchantOf(t) }}</div><div class="row-meta">{{ t.category || '其他' }} · {{ dateOf(t) }}</div></div>
                  <strong :class="t.direction === 'IN' ? 'in' : 'out'">{{ t.direction === 'IN' ? '+' : '-' }}{{ amount(t.amount) }}</strong>
                </div>
              </div>
              <div v-if="message.intent === 'payees' && Array.isArray(message.data)" class="data-panel">
                <div class="panel-subtitle">常用收款人</div>
                <div v-if="!message.data.length" class="empty">暂无常用收款人</div>
                <div v-for="(p, index) in message.data" :key="p.id ?? index" class="list-row">
                  <div class="row-title">{{ payeeOf(p) }}</div>
                  <div class="row-meta">{{ payeeAccountOf(p) }}</div>
                </div>
              </div>
              <div v-if="message.intent === 'subscriptions' && Array.isArray(message.data)" class="data-panel">
                <div class="panel-subtitle">订阅代扣协议 · 仅查询</div>
                <div v-if="!message.data.length" class="empty">暂无代扣协议</div>
                <div v-for="(s, index) in message.data" :key="s.id ?? index" class="list-row">
                  <div><div class="row-title">{{ merchantOf(s) }} <span class="small-status">{{ s.status === 'ACTIVE' ? '生效中' : '已取消' }}</span></div>
                  <div class="row-meta">{{ cycleOf(s) }} · 下次扣费 {{ nextPayOf(s) }}</div></div>
                  <strong>{{ amount(s.amount) }}</strong>
                </div>
              </div>
              <TransferForm v-if="message.intent === 'transfer' && message.action === 'needs_input' && message.data"
                :payees="message.data.payees" :payee-name="message.data.payeeName" :amount="message.data.amount"
                :request-id="message.data.requestId" :busy="busy" :completed="completedRequests.includes(message.data.requestId)" @prepare="submitTransfer" />
              <TransferOrderCard v-if="message.intent === 'transfer' && message.action === 'prepared' && message.data" :order="message.data" />
              <div v-if="message.source === 'mock-api'" class="mock-warning">⚠ 本地 Mock 银行数据，未连接 Java/MySQL，不能作为真实转账验收。</div>
              <div v-if="message.requestId" class="request-id">请求编号：{{ message.requestId }}</div>
            </div>
          </div>
          <div v-if="busy" class="typing">正在调用银行接口…</div>
          <div ref="endRef"></div>
        </div>
      </div>

      <footer class="footer">
        <form @submit.prevent="send()"><input v-model="input" :disabled="busy" maxlength="300" placeholder="例如：给李四转200元 / 我的余额是多少…" aria-label="输入银行业务需求"/><button :disabled="busy || !input.trim()" type="submit">发送 ↗</button></form>
        <p>Day 3 仅规则识别与转账建单，尚未接入 LLM。所有账户均为模拟数据；请勿输入真实银行卡号、密码或短信验证码。</p>
      </footer>
    </main>
  </div>
</template>
