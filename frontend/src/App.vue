<script setup>
import { ref, onMounted, nextTick } from 'vue'

const shortcuts = [
  { label: '查询余额', message: '我的余额是多少', icon: '◉' },
  { label: '交易流水', message: '查询最近交易', icon: '▤' },
  { label: '常用收款人', message: '我的常用收款人', icon: '♙' },
  { label: '订阅代扣', message: '有哪些自动扣费', icon: '▣' }
]

const messages = ref([{
  id: 'welcome', role: 'assistant', content: '你好，我是 BankPilot。今天可查询模拟账户余额、最近交易、常用收款人和订阅代扣。', intent: 'welcome', data: null
}])
const input = ref('')
const busy = ref(false)
const status = ref('连接检测中')
const endRef = ref(null)

function amount(value) {
  if (value === undefined || value === null || value === '') return '—'
  const num = Number(value)
  if (!Number.isFinite(num)) return '—'
  return new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY' }).format(num)
}
function directionOf(row) { return row.direction === 'IN' ? '收入' : '支出' }
function dateOf(row) { return row.occurredAt ?? row.occurred_at ?? '—' }
function payeeOf(row) { return row.payeeName ?? row.payee_name ?? '—' }
function payeeAccountOf(row) { return row.payeeAccountMasked ?? row.payee_account_masked ?? '—' }
function merchantOf(row) { return row.merchantName ?? row.merchant_name ?? '—' }
function cycleOf(row) { return row.billingCycle === 'MONTHLY' ? '每月' : (row.billingCycle ?? '—') }
function nextPayOf(row) { return row.nextPayDate ?? row.next_pay_date ?? '—' }
async function scrollToBottom() { await nextTick(); endRef.value?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }

async function checkHealth() {
  try {
    const response = await fetch('/api/agent/health', { signal: AbortSignal.timeout(4000) })
    if (!response.ok) throw new Error('status')
    status.value = '交互服务已连接'
  } catch {
    status.value = '交互服务未连接'
  }
}

async function send(message) {
  const text = String(message ?? input.value).trim()
  if (!text || busy.value) return
  input.value = ''
  messages.value.push({ id: crypto.randomUUID(), role: 'user', content: text })
  busy.value = true
  await scrollToBottom()
  try {
    const response = await fetch('/api/agent/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text }),
      signal: AbortSignal.timeout(12000)
    })
    const payload = await response.json()
    if (!response.ok) throw new Error(payload.detail || '查询失败')
    messages.value.push({ id: crypto.randomUUID(), role: 'assistant',
      content: payload.reply, intent: payload.intent, data: payload.data, source: payload.source,
      requestId: payload.requestId })
  } catch (err) {
    messages.value.push({ id: crypto.randomUUID(), role: 'assistant',
      content: `请求失败：${err.message}。请检查 Python 服务、Java 服务和 MySQL 是否已启动。`, intent: 'error' })
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
      <div class="side-heading">今日进度</div>
      <div class="progress-item done">✓ Day 1 · 环境搭建</div>
      <div class="progress-item active">● Day 2 · 银行查询</div>
      <div class="progress-item muted">○ Day 3 · 转账订单</div>
      <div class="progress-item muted">○ Day 4 · 授权执行</div>
      <div class="side-note">本地模拟环境<br/>本版本只支持查询，不会执行任何真实资金操作。</div>
    </aside>

    <main class="main">
      <header class="header">
        <div><h1>银行智能助手</h1><p>用自然语言查询你的模拟银行账户</p></div>
        <span class="server-status" :class="status === '交互服务已连接' ? 'online' : 'offline'">● {{ status }}</span>
      </header>

      <div class="content">
        <div class="welcome-card"><div class="welcome-kicker">BankPilot / DAY 02</div><h2>今天想查询什么？</h2><p>试试快捷问题，或在下面输入你的银行业务需求。</p>
          <div class="shortcuts"><button v-for="shortcut in shortcuts" :key="shortcut.label" @click="send(shortcut.message)" :disabled="busy"><span>{{ shortcut.icon }}</span>{{ shortcut.label }}</button></div>
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
              <div v-if="message.source === 'mock-api'" class="mock-warning">⚠ 当前使用本地假银行数据，尚未连接 Java/MySQL</div>
              <div v-if="message.requestId" class="request-id">查询编号：{{ message.requestId }}</div>
            </div>
          </div>
          <div v-if="busy" class="typing">正在查询银行接口…</div>
          <div ref="endRef"></div>
        </div>
      </div>

      <footer class="footer">
        <form @submit.prevent="send()"><input v-model="input" :disabled="busy" maxlength="300" placeholder="输入：查询最近交易 / 有哪些自动扣费…" aria-label="输入查询需求"/><button :disabled="busy || !input.trim()" type="submit">发送 ↗</button></form>
        <p>Day 2 使用规则路由，尚未接入大模型。所有数据显示自银行查询接口；请勿输入真实银行卡或密码。</p>
      </footer>
    </main>
  </div>
</template>
