<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import DynamicWorkflowCard from './components/DynamicWorkflowCard.vue'
import AuthPanel from './components/AuthPanel.vue'
import AaCenter from './components/AaCenter.vue'
import ScheduleCenter from './components/ScheduleCenter.vue'

// Day 6 4G: one input -> dynamic planner -> LangGraph -> bank. No direct Java call.
const input = ref('')
const token = ref('') // Memory only. Never write to localStorage/sessionStorage.
const currentUser = ref(null)
const authMode = ref('login')
const authNotice = ref('')
const bankMode = ref('java')
const modelName = ref('')
const modelConfigured = ref(false)
const connected = ref(false)
const busy = ref(false)
const workingThread = ref(null)
const lastRef = ref(null)
const aaCenter = ref(null)
const scheduleCenter = ref(null)
const messages = ref([{
  id: 'welcome', role: 'assistant', intent: 'notice',
  reply: '你好，我是 BankPilot。现在可以在同一个聊天框查询账户、分析收支、转账和取消代扣；需要改变银行状态时，我会先请你确认。',
}])
const examples = [
  '我的余额是多少？',
  '查询最近交易和常用收款人',
  '分析2026年10月收支，并查询自动扣费',
  '给李四转200元，备注聚餐',
  '取消视频会员代扣',
  '我和张三、李四聚餐300元，三个人AA，帮我收款',
  '明天下午3点给李四转200元，备注生活费',
  '分析2026年9月收支，查询余额，并取消视频会员代扣',
]

const waitingStatuses = ['WAITING_RECIPIENT_SELECTION', 'WAITING_TRANSFER_APPROVAL', 'WAITING_APPROVAL', 'WAITING_AA_CONFIRMATION', 'WAITING_SCHEDULE_AUTH']
const needsAttention = m => m.intent === 'dynamic' && (
  waitingStatuses.includes(m.data?.status) || m.data?.status === 'NOT_CONFIRMED' || m.uncertain
)
const pending = computed(() => messages.value.some(needsAttention))
const pendingItem = computed(() => messages.value.find(needsAttention))
const hasConversation = computed(() => messages.value.some(m => m.role === 'user'))
const settingsOpen = ref(false)
const isAuthenticated = computed(() => Boolean(token.value.trim() && currentUser.value?.userId))

function headers(overrideToken = undefined) {
  const h = { 'Content-Type': 'application/json; charset=utf-8' }
  const activeToken = overrideToken === undefined ? token.value : overrideToken
  if (activeToken?.trim()) h.Authorization = `Bearer ${activeToken.trim()}`
  return h
}

async function req(path, method = 'GET', payload = undefined, timeoutMs = 90000, overrideToken = undefined) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const response = await fetch(path, {
      method, headers: headers(overrideToken),
      body: payload === undefined ? undefined : JSON.stringify(payload),
      signal: controller.signal,
    })
    const body = await response.json().catch(() => ({}))
    if (!response.ok) {
      const detail = body.detail
      const msg = typeof detail === 'string' ? detail : (detail ? JSON.stringify(detail) : `HTTP ${response.status}`)
      const error = new Error(msg)
      error.httpStatus = response.status
      // Session has expired/revoked. A new login must be Java-verified.
      if (response.status === 401 && overrideToken === undefined && token.value.trim() &&
          !['/api/agent/auth/login', '/api/agent/auth/register'].includes(path)) {
        resetSession('登录状态已失效，请重新登录。')
      }
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
    case 'WAITING_RECIPIENT_SELECTION': return '找到多个同名收款人，请先选择正确的银行账户。此时尚未创建转账订单。'
    case 'WAITING_TRANSFER_APPROVAL': return '只读任务已完成，银行转账订单已创建，等待你单独确认；高风险转账需要 OTP。'
    case 'WAITING_AA_CONFIRMATION': return 'AA明细已准备好，请核对后确认发布；目前还没有通知其他用户，也没有扣款。'
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

function resetSession(message = '') {
  token.value = ''
  currentUser.value = null
  input.value = ''
  messages.value = [{
    id: 'welcome', role: 'assistant', intent: 'notice',
    reply: '你好，我是 BankPilot。登录后可以查询账户、分析收支、转账和管理代扣。',
  }]
  workingThread.value = null
  settingsOpen.value = false
  authMode.value = 'login'
  authNotice.value = message
  // Clearing the browser UI does not modify any Java bank order.
}

function changeAuthMode(mode) {
  authMode.value = mode
  authNotice.value = ''
}

async function registerUser(fields) {
  if (busy.value || isAuthenticated.value) return
  busy.value = true
  authNotice.value = ''
  try {
    await req('/api/agent/auth/register', 'POST', fields, 20000)
    authMode.value = 'login'
    authNotice.value = '注册成功。请使用刚才设置的用户名和密码登录；注册不会自动登录。'
  } catch (e) {
    authNotice.value = `注册失败：${e.message}`
  } finally {
    busy.value = false
  }
}

async function loginUser(fields) {
  if (busy.value || isAuthenticated.value) return
  busy.value = true
  authNotice.value = ''
  try {
    const login = await req('/api/agent/auth/login', 'POST', fields, 20000)
    if (typeof login.token !== 'string' || !login.token.trim()) throw new Error('银行没有返回登录凭证。')
    // Trust Java /me, not a browser-supplied userId or displayName.
    const identity = await req('/api/agent/auth/me', 'GET', undefined, 20000, login.token)
    if (!Number.isSafeInteger(identity.userId) || identity.userId <= 0) throw new Error('银行认证身份无效。')
    resetSession()
    token.value = login.token
    currentUser.value = identity
  } catch (e) {
    authNotice.value = `登录失败：${e.message}`
  } finally {
    busy.value = false
  }
}

async function logoutUser() {
  if (busy.value || !isAuthenticated.value) return
  busy.value = true
  authNotice.value = ''
  try {
    // Java must revoke the server token; do not claim logout on failed revoke.
    await req('/api/agent/auth/logout', 'POST', undefined, 20000)
    resetSession('已安全退出银行账户。')
  } catch (e) {
    if (isAuthenticated.value) authNotice.value = `银行未确认退出：${e.message}。请重试退出。`
  } finally {
    busy.value = false
  }
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
    pushAssistant('请先登录银行账户。')
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
  for (const k of ['plan', 'results', 'candidate', 'cancellationOrder', 'transferOrder', 'transferCandidate', 'recipientChoices', 'aaCollection', 'scheduledTransfer']) {
    if (data[k] == null && previous[k] != null) merged[k] = previous[k]
  }
  item.data = merged
  item.reply = summary(merged)
  item.actionError = ''
  item.uncertain = false
}

async function cancelRecipient(threadId) {
  const item = messages.value.find(m => m.intent === 'dynamic' && m.data?.threadId === threadId)
  if (!item || busy.value || item.data?.status !== 'WAITING_RECIPIENT_SELECTION') return
  busy.value = true
  workingThread.value = threadId
  try {
    const result = await req('/api/agent/workflows/dynamic/recipient/cancel', 'POST', { threadId }, 30000)
    updateTask(item, result)
  } catch (e) {
    item.actionError = `取消选择失败：${e.message}`
    if (e.uncertain || e.httpStatus >= 500) item.uncertain = true
  } finally {
    busy.value = false
    workingThread.value = null
    await scroll()
  }
}

async function selectRecipient({ threadId, recipientId }) {
  const item = messages.value.find(m => m.intent === 'dynamic' && m.data?.threadId === threadId)
  if (!item || busy.value || item.uncertain || item.data?.status !== 'WAITING_RECIPIENT_SELECTION') return
  busy.value = true
  workingThread.value = threadId
  item.actionError = ''
  try {
    const result = await req('/api/agent/workflows/dynamic/recipient/select', 'POST',
                             { threadId, recipientId }, 90000)
    updateTask(item, result)
  } catch (e) {
    item.actionError = `收款人选择失败：${e.message}`
    if (e.uncertain || e.httpStatus === 409 || e.httpStatus >= 500) {
      item.uncertain = true
      item.actionError += ' 请核查原任务及可能已经创建的银行订单，不要重新创建转账。'
    }
  } finally {
    busy.value = false
    workingThread.value = null
    await scroll()
  }
}

async function performDecision({ threadId, kind, approved, otpCode }) {
  const item = messages.value.find(m => m.intent === 'dynamic' && m.data?.threadId === threadId)
  if (!item || busy.value || item.uncertain) return
  const expected = kind === 'transfer' ? 'WAITING_TRANSFER_APPROVAL' : kind === 'aa' ? 'WAITING_AA_CONFIRMATION' : kind === 'schedule' ? 'WAITING_SCHEDULE_AUTH' : 'WAITING_APPROVAL'
  if (item.data.status !== expected) return
  if (!token.value.trim()) { item.actionError = '请先登录，不能提交审批。'; return }
  const payload = { threadId, approved: approved === true }
  if ((kind === 'transfer' || kind === 'schedule') && approved && otpCode) payload.otpCode = otpCode
  const path = '/api/agent/workflows/dynamic/resume'
  busy.value = true
  workingThread.value = threadId
  item.actionError = ''
  await scroll()
  try {
    const result = await req(path, 'POST', payload, 90000)
    updateTask(item, result)
    if (kind === 'aa' && result.status === 'COMPLETED') aaCenter.value?.refresh()
    if (kind === 'schedule' && result.status === 'COMPLETED') scheduleCenter.value?.refresh()
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
  if (!item || busy.value || item.uncertain || !['WAITING_TRANSFER_APPROVAL','WAITING_SCHEDULE_AUTH'].includes(item.data?.status)) return
  busy.value = true
  workingThread.value = threadId
  item.actionError = ''
  try {
    const otpPath = item.data?.status === 'WAITING_SCHEDULE_AUTH' ? '/api/agent/workflows/dynamic/schedule/otp/request' : '/api/agent/workflows/dynamic/transfer/otp/request'
    const result = await req(otpPath, 'POST', { threadId }, 30000)
    item.otpNotice = `验证码申请已受理，时效 ${result.expiresInSeconds ?? 120} 秒。请使用银行演示验证渠道提供的验证码。`
  } catch (e) {
    item.actionError = `申请验证码失败：${e.message}`
  } finally {
    busy.value = false
    workingThread.value = null
    await scroll()
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
      <div class="sidebar-bottom"><span class="small-led"></span> BANKPILOT DEMO <span class="sidebar-version">DAY 07</span></div>
    </aside>

    <main class="bp-main">
      <header class="bp-header">
        <div class="header-heading">
          <div class="header-title">银行智能助手 <span class="header-divider"></span> <span class="header-subtitle">智慧服务工作台</span></div>
          <div class="header-caption">你的银行事务，交给 BankPilot 安排</div>
        </div>
        <div class="header-actions">
          <span class="service-state" :class="connected ? 'online' : 'offline'"><span class="status-led"></span>{{ connected ? '服务已连接' : '连接未就绪' }}</span>
          <span v-if="isAuthenticated" class="current-user">当前用户：{{ currentUser.displayName }}</span>
          <button v-if="isAuthenticated" type="button" class="settings-trigger" :class="{ 'settings-trigger-open': settingsOpen }" :aria-expanded="settingsOpen" aria-controls="bank-settings" @click="settingsOpen = !settingsOpen">
            <span class="settings-symbol" aria-hidden="true">⚙</span> 连接设置
            <span class="settings-caret" aria-hidden="true">⌄</span>
          </button>
          <button v-if="isAuthenticated" type="button" class="logout-trigger" :disabled="busy" @click="logoutUser">退出登录</button>
        </div>
      </header>

      <section v-if="isAuthenticated && settingsOpen" id="bank-settings" class="connection-drawer" aria-label="银行连接设置">
        <div class="connection-intro"><div><strong>银行连接状态</strong><p>当前用户：{{ currentUser.displayName }}。登录凭证仅保存在本次页面内存。</p></div><button class="close-connection" type="button" aria-label="关闭连接设置" @click="settingsOpen = false">×</button></div>
        <div class="connection-status"><span class="connection-chip">{{ bankMode === 'mock' ? 'Mock 模拟银行' : 'Java 银行服务' }}</span><span class="connection-chip">{{ modelConfigured ? (modelName || 'AI 已配置') : 'AI 配置待检查' }}</span></div>
        <div class="connection-row"><button type="button" class="connection-recheck" :disabled="busy" @click="checkHealth">检查连接</button></div>
        <p class="connection-footnote">页面刷新后需重新登录。退出不会自动取消 Java 中已有的银行订单或预约；若 Agent 重启，旧内存审批任务可能无法恢复。</p>
      </section>

      <section v-if="!isAuthenticated" class="bp-content auth-content">
        <AuthPanel :mode="authMode" :busy="busy" :notice="authNotice"
                   @mode-change="changeAuthMode" @login="loginUser" @register="registerUser" />
      </section>
      <section v-else class="bp-content">
        <p v-if="authNotice" class="session-notice" role="alert">{{ authNotice }}</p>
        <AaCenter :key="currentUser.userId" ref="aaCenter" :user-id="currentUser.userId" :fetcher="req" />
        <ScheduleCenter :key="currentUser.userId" ref="scheduleCenter" :user-id="currentUser.userId" :fetcher="req" />
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
          <button class="sample-combo" type="button" :disabled="busy || pending" @click="fillExample(examples[examples.length - 1])">试试多项业务组合 <span aria-hidden="true">↗</span></button>
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
                  @recipient-select="selectRecipient"
                @recipient-cancel="cancelRecipient"
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

      <footer v-if="isAuthenticated" class="bp-composer">
        <div class="composer-inner">
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
