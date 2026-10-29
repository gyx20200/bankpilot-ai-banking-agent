<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import DynamicWorkflowCard from './components/DynamicWorkflowCard.vue'

// Day 6 4G: one input -> dynamic planner -> LangGraph -> bank. No direct Java call.
const input = ref('')
const token = ref('') // Demo only. Never stored in localStorage/sessionStorage.
const loginPassword = ref('')
const loginMessage = ref('')
const bankMode = ref('java')
const modelName = ref('')
const modelConfigured = ref(false)
const connected = ref(false)
const busy = ref(false)
const workingThread = ref(null)
const lastRef = ref(null)
const messages = ref([{
  id: 'welcome', role: 'assistant', intent: 'notice',
  reply: '你好，我是 BankPilot。现在可以在同一个聊天框查询账户、分析收支、转账和取消代扣；需要改变银行状态时，我会先请你确认。',
}])
const examples = [
  '我的余额是多少？',
  '查询最近交易和常用收款人',
  '分析2026年10月收支，并查询自动扣费',
  '给李四转200元',
  '取消视频会员代扣',
  '分析2026年9月收支，查询余额，并取消视频会员代扣',
]

const waitingStatuses = ['WAITING_TRANSFER_APPROVAL', 'WAITING_APPROVAL']
const needsAttention = m => m.intent === 'dynamic' && (
  waitingStatuses.includes(m.data?.status) || m.data?.status === 'NOT_CONFIRMED' || m.uncertain
)
const pending = computed(() => messages.value.some(needsAttention))
const pendingItem = computed(() => messages.value.find(needsAttention))
const hasConversation = computed(() => messages.value.some(m => m.role === 'user'))
const settingsOpen = ref(false)
const isAuthenticated = computed(() => Boolean(token.value.trim()))

function headers() {
  const h = { 'Content-Type': 'application/json; charset=utf-8' }
  if (token.value.trim()) h.Authorization = `Bearer ${token.value.trim()}`
  return h
}

async function req(path, method = 'GET', payload = undefined, timeoutMs = 90000) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const response = await fetch(path, {
      method, headers: headers(),
      body: payload === undefined ? undefined : JSON.stringify(payload),
      signal: controller.signal,
    })
    const body = await response.json().catch(() => ({}))
    if (!response.ok) {
      const detail = body.detail
      const msg = typeof detail === 'string' ? detail : (detail ? JSON.stringify(detail) : `HTTP ${response.status}`)
      const error = new Error(msg)
      error.httpStatus = response.status
      throw error
    }
    return body
  } catch (error) {
    if (error.name === 'AbortError') {
      const timeout = new Error('请求超时，银行操作可能已经提交，请先核对原订单状态，勿重复发起。')
      timeout.uncertain = true
      throw timeout
    }
    if (error instanceof TypeError) {
      const network = new Error('网络连接异常，银行操作状态可能尚未确认，请勿重复提交。')
      network.uncertain = true
      throw network
    }
    throw error
  } finally {
    clearTimeout(timer)
  }
}

async function scroll() {
  await nextTick()
  lastRef.value?.scrollIntoView({ behavior: 'smooth', block: 'end' })
}

function pushAssistant(reply, more = {}) {
  messages.value.push({ id: crypto.randomUUID(), role: 'assistant', intent: 'notice', reply, ...more })
}

function summary(data) {
  const s = data?.status
  switch (s) {
    case 'WAITING_TRANSFER_APPROVAL': return '只读任务已完成，银行转账订单已创建，等待你单独确认；高风险转账需要 OTP。'
    case 'WAITING_APPROVAL': return '只读任务已完成，取消代扣申请等待你的明确审批。订阅目前未取消。'
    case 'COMPLETED': return '任务已完成。以下数据和业务状态来自银行接口，请查看每一项的结果。'
    case 'REJECTED': return '用户拒绝的操作已由银行处理，请核对各订单状态。'
    case 'NEEDS_CLARIFICATION': return '指令信息还不完整，请根据下方提示重新输入包含完整参数的指令。'
    case 'TARGET_NOT_FOUND':
    case 'TARGET_AMBIGUOUS':
    case 'PAYEE_NOT_FOUND':
    case 'PAYEE_AMBIGUOUS':
    case 'TARGET_INVALID':
    case 'INCOMPLETE': return '业务对象或查询结果未通过校验，没有继续创建相关银行订单。'
    case 'NOT_IMPLEMENTED_YET': return '其中有尚未接入的业务，本次没有执行银行操作。'
    default: return '已返回当前任务状态。请按下方结果核实后再继续。'
  }
}

async function checkHealth() {
  try {
    const h = await req('/api/agent/health', 'GET', undefined, 12000)
    bankMode.value = h.bankMode === 'mock' ? 'mock' : 'java'
    modelConfigured.value = Boolean(h.modelConfigured)
    modelName.value = h.modelName || ''
    connected.value = true
  } catch {
    connected.value = false
  }
}

function useMockToken() {
  token.value = 'mock-day4-token'
  settingsOpen.value = false
  loginMessage.value = '已连接 Mock 演示账户'
}

function fillExample(example) {
  if (busy.value || pending.value) return
  input.value = example
  document.getElementById('bank-command')?.focus()
}

async function send() {
  const message = input.value.trim()
  if (!message || busy.value) return
  if (pending.value) {
    pushAssistant('请先完成当前审批，或刷新并核查原订单状态；暂不创建新的敏感订单。')
    await scroll()
    return
  }
  if (!token.value.trim()) {
    pushAssistant('请先在顶部填写登录 Token，Mock 模式可使用“填入 Mock 测试令牌”。')
    await scroll()
    return
  }
  busy.value = true
  input.value = ''
  messages.value.push({ id: crypto.randomUUID(), role: 'user', reply: message })
  await scroll()
  try {
    const data = await req('/api/agent/workflows/dynamic/start', 'POST', { message })
    messages.value.push({ id: crypto.randomUUID(), role: 'assistant', intent: 'dynamic', reply: summary(data), data, originalMessage: message, uncertain: false, actionError: '' })
  } catch (e) {
    // A POST may have reached the bank even when its HTTP response was lost.
    pushAssistant(`任务提交未能确认：${e.message}${e.uncertain || e.httpStatus === 409 || (e.httpStatus >= 500) ? ' 可能已生成银行申请或存在未处理订单，暂不要重复发送同一指令。' : e.httpStatus === 422 ? ' 请重新输入含完整参数的业务指令。' : ''}`, { intent: 'error' })
  } finally {
    busy.value = false
    await scroll()
  }
}

function updateTask(item, data) {
  // Preserve read results and initial plan if a resume response omits optional fields.
  const previous = item.data || {}
  const merged = { ...previous, ...data }
  for (const k of ['plan', 'results', 'candidate', 'cancellationOrder', 'transferOrder', 'transferCandidate']) {
    if (data[k] == null && previous[k] != null) merged[k] = previous[k]
  }
  item.data = merged
  item.reply = summary(merged)
  item.actionError = ''
  item.uncertain = false
}

async function performDecision({ threadId, kind, approved, otpCode }) {
  const item = messages.value.find(m => m.intent === 'dynamic' && m.data?.threadId === threadId)
  if (!item || busy.value || item.uncertain) return
  const expected = kind === 'transfer' ? 'WAITING_TRANSFER_APPROVAL' : 'WAITING_APPROVAL'
  if (item.data.status !== expected) return
  if (!token.value.trim()) { item.actionError = '请先登录，不能提交审批。'; return }
  const payload = { threadId, approved: approved === true }
  if (kind === 'transfer' && approved && otpCode) payload.otpCode = otpCode
  const path = '/api/agent/workflows/dynamic/resume'
  busy.value = true
  workingThread.value = threadId
  item.actionError = ''
  await scroll()
  try {
    const result = await req(path, 'POST', payload, 90000)
    updateTask(item, result)
  } catch (e) {
    item.actionError = `审批请求未完成：${e.message}`
    // Invalid OTP may be corrected; unknown outcomes require status inspection.
    // Timeout/network/500/409 may have unknown side effects: block same-card retries.
    if (e.uncertain || e.httpStatus === 409 || e.httpStatus >= 500) {
      item.uncertain = true
      item.actionError += ' 结果可能已经发生变化，请核查原银行订单，不要再次点击批准或拒绝。'
    }
  } finally {
    busy.value = false
    workingThread.value = null
    await scroll()
  }
}

async function refreshTask(threadId) {
  const item = messages.value.find(m => m.intent === 'dynamic' && m.data?.threadId === threadId)
  if (!item || busy.value) return
  busy.value = true
  workingThread.value = threadId
  try {
    const state = await req(`/api/agent/workflows/dynamic/${encodeURIComponent(threadId)}`, 'GET', undefined, 20000)
    updateTask(item, state)
    if (state.status === 'NOT_CONFIRMED') {
      item.uncertain = true
      item.actionError = '银行操作结果尚未确认，请核查原订单，不要创建新申请。'
    }
  } catch (e) {
    item.actionError = `查询工作流状态失败：${e.message}`
    item.uncertain = true
  } finally {
    busy.value = false
    workingThread.value = null
    await scroll()
  }
}

async function recoverWorkflow(threadId, approved) {
  const item = messages.value.find(m => m.intent === 'dynamic' && m.data?.threadId === threadId)
  if (!item || busy.value || typeof approved !== 'boolean') return
  busy.value = true
  workingThread.value = threadId
  try {
    // Same existing thread, same saved decision and bank idempotency keys.
    const result = await req('/api/agent/workflows/dynamic/resume', 'POST',
                             { threadId, approved }, 90000)
    updateTask(item, result)
  } catch (e) {
    item.uncertain = true
    item.actionError = `恢复未确认：${e.message}。请刷新原任务并核实银行订单状态。`
  } finally {
    busy.value = false
    workingThread.value = null
    await scroll()
  }
}

async function requestOtp(threadId) {
  const item = messages.value.find(m => m.intent === 'dynamic' && m.data?.threadId === threadId)
  if (!item || busy.value || item.uncertain || item.data?.status !== 'WAITING_TRANSFER_APPROVAL') return
  busy.value = true
  workingThread.value = threadId
  item.actionError = ''
  try {
    const result = await req('/api/agent/workflows/dynamic/transfer/otp/request', 'POST', { threadId }, 30000)
    item.otpNotice = `验证码申请已受理，时效 ${result.expiresInSeconds ?? 120} 秒。请使用银行演示验证渠道提供的验证码。`
  } catch (e) {
    item.actionError = `申请验证码失败：${e.message}`
  } finally {
    busy.value = false
    workingThread.value = null
    await scroll()
  }
}

async function demoLogin() {
  if (busy.value || !loginPassword.value) return
  busy.value = true
  loginMessage.value = ''
  try {
    const result = await req('/api/agent/auth/demo-login', 'POST', { password: loginPassword.value }, 20000)
    token.value = result.token
    settingsOpen.value = false
    loginMessage.value = `已登录：${result.displayName || '演示账户'}`
  } catch (e) {
    loginMessage.value = `登录失败：${e.message}`
  } finally {
    loginPassword.value = ''
    busy.value = false
  }
}

// Only for a demo session whose pending BANK orders were independently verified
// to be in a terminal state. Never claims to finish a server-side workflow.
function restartVerifiedLocalChat() {
  if (busy.value) return
  const accepted = window.confirm(
    '请先在 Java/MySQL 核实所有相关银行订单都已结束（如取消申请为 CANCELLED、原订阅仍 ACTIVE），\n' +
    '并确认没有 PENDING_APPROVAL、AUTHORIZED 或其他未完成的操作。\n\n' +
    '继续只会清空当前网页的聊天和审批卡；不会撤销或完成银行订单，也不会修改 LangGraph Checkpoint。\n' +
    '如银行订单仍未结束，请取消并先核查原订单。\n\n确定重新开始本地聊天吗？'
  )
  if (!accepted) return

  messages.value = [{
    id: 'welcome', role: 'assistant', intent: 'notice',
    reply: '你好，我是 BankPilot。现在可以在同一个聊天框查询账户、分析收支、转账和取消代扣；需要改变银行状态时，我会先请你确认。',
  }]
  input.value = ''
  workingThread.value = null
  settingsOpen.value = false
  // Keep the existing login token so harmless read-only questions work immediately.
  // Do not alter bank data or the Python checkpoint.
}

onMounted(checkHealth)
</script>

<template>
  <div class="layout bp-shell">
    <aside class="side bp-sidebar" aria-label="应用导航">
      <div class="brand-lockup">
        <span class="brand-mark" aria-hidden="true">B</span>
        <div class="brand-copy"><strong>BankPilot</strong><small>AI BANKING ASSISTANT</small></div>
      </div>

      <div class="sidebar-group">
        <span class="sidebar-caption">工作空间</span>
        <div class="sidebar-active"><span class="sidebar-nav-icon" aria-hidden="true">✦</span> 智能对话 <span class="sidebar-active-dot"></span></div>
      </div>

      <div class="sidebar-spacer"></div>
      <div class="sidebar-capability">
        <span class="sidebar-capability-label">你的智能银行助手</span>
        <p>账户查询、收支分析、模拟转账与代扣管理，都可以用一句话完成。</p>
      </div>
      <div class="sidebar-bottom"><span class="small-led"></span> BANKPILOT DEMO <span class="sidebar-version">DAY 06</span></div>
    </aside>

    <main class="bp-main">
      <header class="bp-header">
        <div class="header-heading">
          <div class="header-title">银行智能助手 <span class="header-divider"></span> <span class="header-subtitle">智慧服务工作台</span></div>
          <div class="header-caption">你的银行事务，交给 BankPilot 安排</div>
        </div>
        <div class="header-actions">
          <span class="service-state" :class="connected ? 'online' : 'offline'"><span class="status-led"></span>{{ connected ? '服务已连接' : '连接未就绪' }}</span>
          <button type="button" class="settings-trigger" :class="{ 'settings-trigger-open': settingsOpen }" :aria-expanded="settingsOpen" aria-controls="bank-settings" @click="settingsOpen = !settingsOpen">
            <span class="settings-symbol" aria-hidden="true">⚙</span> 连接设置
            <span class="settings-caret" aria-hidden="true">⌄</span>
          </button>
        </div>
      </header>

      <section v-if="settingsOpen" id="bank-settings" class="connection-drawer" aria-label="银行连接设置">
        <div class="connection-intro"><div><strong>连接与演示账户</strong><p>仅用于本地演示，凭证不会持久化保存在浏览器中。</p></div><button class="close-connection" type="button" aria-label="关闭连接设置" @click="settingsOpen = false">×</button></div>
        <div class="connection-status"><span class="connection-chip">{{ bankMode === 'mock' ? 'Mock 模拟银行' : 'Java 银行服务' }}</span><span class="connection-chip">{{ modelConfigured ? (modelName || 'AI 已配置') : 'AI 配置待检查' }}</span></div>
        <div v-if="bankMode === 'java'" class="connection-row">
          <input v-model="loginPassword" :disabled="busy" type="password" autocomplete="current-password" placeholder="演示银行登录密码" aria-label="演示银行登录密码" />
          <button type="button" :disabled="busy || !loginPassword" @click="demoLogin">登录</button>
        </div>
        <div class="connection-row">
          <input v-model="token" :disabled="busy || pending" type="password" autocomplete="off" placeholder="登录 Token（不含 Bearer）" aria-label="银行演示登录令牌" />
          <button v-if="bankMode === 'mock'" type="button" :disabled="busy || pending" @click="useMockToken">使用 Mock 账户</button>
          <button type="button" class="connection-recheck" :disabled="busy" @click="checkHealth">检查连接</button>
        </div>
        <p v-if="loginMessage" class="connection-message">{{ loginMessage }}</p>
        <p class="connection-footnote">若页面刷新或 Agent 重启，内存中尚未完成的审批可能无法恢复；不要盲目重复发起资金类业务。</p>
      </section>

      <section class="bp-content">
        <div v-if="!hasConversation" class="welcome-screen">
          <div class="welcome-kicker"><span class="welcome-kicker-dot"></span> BANKPILOT · AI ASSISTANT</div>
          <h1>你好，今天想办理什么？</h1>
          <p class="welcome-description">从查询余额到分析收支，或是转账与管理自动扣费。<br class="welcome-break" />说出你的需求，其余交给智能助手。</p>
          <div class="sample-label">试试这样提问</div>
          <div class="sample-grid">
            <button v-for="(example, index) in examples.slice(0,4)" :key="example" type="button" class="sample-card" :disabled="busy || pending" @click="fillExample(example)">
              <span class="sample-icon" aria-hidden="true">{{ ['¥', '▤', '↗', '⟳'][index] }}</span>
              <span class="sample-text">{{ example }}</span>
              <span class="sample-arrow" aria-hidden="true">↗</span>
            </button>
          </div>
          <button class="sample-combo" type="button" :disabled="busy || pending" @click="fillExample(examples[5])">试试多项业务组合 <span aria-hidden="true">↗</span></button>
        </div>

        <div v-else class="conversation-heading">
          <span class="conversation-overline">CONVERSATION</span><h2>与 BankPilot 的对话</h2>
          <p>查询自动完成，涉及账户变更的操作将单独请你确认。</p>
        </div>

        <div v-if="pending" class="pending-banner" role="status">
          <span class="pending-icon" aria-hidden="true">!</span>
          <div class="pending-banner-body">
            <strong>有一项操作等待你的确认</strong>
            <span>{{ pendingItem?.data?.status === 'NOT_CONFIRMED' || pendingItem?.uncertain ? '任务结果待核查，请先刷新原任务并确认银行订单状态。' : '请在当前任务卡片完成审批，再发起下一条指令。' }}</span>
            <div class="local-recovery">
              <button type="button" class="local-recovery-button" :disabled="busy" @click="restartVerifiedLocalChat">
                已核对银行订单，重新开始本地聊天
              </button>
              <small>仅清除本页聊天记录，不会修改银行订单；请先核实所有相关订单已结束。</small>
            </div>
          </div>
        </div>

        <section class="chat bp-chat" aria-live="polite" aria-label="与 BankPilot 的对话">
          <div v-for="m in messages.filter(m => hasConversation || m.id !== 'welcome')" :key="m.id" class="msg" :class="m.role">
            <div class="avatar bp-avatar" :class="m.role === 'assistant' ? 'bp-avatar-agent' : 'bp-avatar-user'" aria-hidden="true">{{ m.role === 'assistant' ? 'B' : '我' }}</div>
            <div class="msg-content bp-message-content">
              <div v-if="m.role === 'assistant'" class="message-sender">BankPilot <span>智能助手</span></div>
              <div class="bubble bp-bubble">{{ m.reply }}</div>
              <DynamicWorkflowCard
                  v-if="m.intent === 'dynamic' && m.data"
                  :task="m.data"
                  :busy="busy && workingThread === m.data.threadId"
                  :locked="Boolean(m.uncertain)"
                  :action-error="m.actionError || ''"
                  :otp-notice="m.otpNotice || ''"
                  @decision="performDecision"
                  @otp-request="requestOtp"
                  @refresh="refreshTask"
                  @recover="recoverWorkflow"
              />
              <p v-if="m.intent === 'error'" class="error-alert" role="alert">如果是提交超时或订单状态不明，请先核查银行中的原订单，避免重复操作。</p>
            </div>
          </div>
          <p v-if="busy" class="thinking bp-thinking"><span class="spinner"></span> 正在联系银行，请勿重复提交…</p>
          <div ref="lastRef" class="scroll-anchor"></div>
        </section>
      </section>

      <footer class="bp-composer">
        <div class="composer-inner">
          <div v-if="!isAuthenticated" class="composer-connect">尚未登录演示银行。<button type="button" @click="settingsOpen = true">打开连接设置</button></div>
          <form class="composer-form" @submit.prevent="send">
            <input id="bank-command" v-model="input" :disabled="busy || pending" maxlength="300" placeholder="输入你的银行业务需求，例如：给李四转200元" aria-label="输入银行业务指令" />
            <button type="submit" :disabled="busy || pending || !input.trim()" aria-label="发送消息">发送 <span aria-hidden="true">↗</span></button>
          </form>
          <div class="composer-note"><span class="note-lock" aria-hidden="true">◆</span> 涉及转账或取消代扣时，必须由你明确批准后才会执行 <span class="note-dot">·</span> 仅供模拟演示</div>
        </div>
      </footer>
    </main>
  </div>
</template>

<style scoped>
/* Main layout is deliberately centralized in style.css to preserve original cards. */
.pending-banner-body { min-width: 0; }
.local-recovery { display: flex; flex-direction: column; align-items: flex-start; gap: 6px; margin-top: 10px; }
.local-recovery-button {
  background: #fff; border: 1px solid #bfccd8; border-radius: 8px;
  color: #25476d; font-size: 12px; padding: 7px 10px; cursor: pointer;
}
.local-recovery-button:hover:not(:disabled) { background: #f4f7fb; }
.local-recovery-button:disabled { cursor: not-allowed; opacity: .5; }
.local-recovery small { color: #64748b; font-size: 11px; line-height: 1.5; }
</style>
