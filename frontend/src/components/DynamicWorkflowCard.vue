<script setup>
import { computed, ref, watch } from 'vue'
import MonthlyAnalyticsCard from './MonthlyAnalyticsCard.vue'

const props = defineProps({
  task: { type: Object, required: true },
  busy: { type: Boolean, default: false },
  locked: { type: Boolean, default: false },
  actionError: { type: String, default: '' },
  otpNotice: { type: String, default: '' },
})
const emit = defineEmits(['decision', 'otpRequest', 'refresh', 'recover', 'recipientSelect', 'recipientCancel'])
const confirmed = ref(false)
const otp = ref('')
const otpRequested = ref(false)
const localError = ref('')

const order = computed(() => props.task.transferOrder || null)
const cancellation = computed(() => props.task.cancellationOrder || null)
const aaCollection = computed(() => props.task.aaCollection || null)
const scheduled = computed(() => props.task.scheduledTransfer || null)
const isSchedulePending = computed(() => status.value === 'WAITING_SCHEDULE_AUTH' && scheduled.value?.status === 'PENDING_AUTH')
const isAaPending = computed(() => status.value === 'WAITING_AA_CONFIRMATION' && aaCollection.value?.status === 'DRAFT')
const status = computed(() => props.task.status || 'UNKNOWN')
const isTransferPending = computed(() => status.value === 'WAITING_TRANSFER_APPROVAL' && Boolean(order.value?.orderId))
const isCancellationPending = computed(() => status.value === 'WAITING_APPROVAL' && Boolean(cancellation.value?.orderId))
const riskRed = computed(() => order.value?.riskLevel === 'RED')
const planTasks = computed(() => Array.isArray(props.task.plan?.tasks) ? props.task.plan.tasks : [])
const results = computed(() => props.task.results || {})
const balance = computed(() => results.value.get_balance?.status === 'SUCCESS' ? results.value.get_balance.data : null)
const transactions = computed(() => results.value.get_transactions?.status === 'SUCCESS' && Array.isArray(results.value.get_transactions.data) ? results.value.get_transactions.data : null)
const payees = computed(() => results.value.get_payees?.status === 'SUCCESS' && Array.isArray(results.value.get_payees.data) ? results.value.get_payees.data : null)
const subscriptions = computed(() => results.value.list_subscriptions?.status === 'SUCCESS' && Array.isArray(results.value.list_subscriptions.data) ? results.value.list_subscriptions.data : null)
const monthly = computed(() => results.value.monthly_analytics?.status === 'SUCCESS' ? results.value.monthly_analytics.data : null)
const requested = computed(() => new Set(planTasks.value.map(t => t.type)))
const showBalance = computed(() => balance.value && requested.value.has('get_balance'))
const showTransactions = computed(() => transactions.value && requested.value.has('get_transactions'))
const showPayees = computed(() => payees.value && requested.value.has('get_payees'))
const showSubscriptions = computed(() => subscriptions.value && requested.value.has('list_subscriptions'))
const showMonthly = computed(() => monthly.value && requested.value.has('monthly_analytics'))
const hasVisibleRead = computed(() => showBalance.value || showTransactions.value || showPayees.value || showSubscriptions.value || showMonthly.value)
const readCount = computed(() => [showBalance, showTransactions, showPayees, showSubscriptions, showMonthly].filter(flag => Boolean(flag.value)).length)
const technicalOpen = ref(false)
const recipientChoices = computed(() => Array.isArray(props.task.recipientChoices) ? props.task.recipientChoices : [])
const choosingRecipient = computed(() => status.value === 'WAITING_RECIPIENT_SELECTION' && recipientChoices.value.length > 1)
const selectedRecipientId = ref(null)

const taskNames = {
  get_balance: '查询余额', get_transactions: '最近交易', get_payees: '查询收款人',
  monthly_analytics: '月度收支分析', list_subscriptions: '查询代扣订阅',
  transfer_prepare: '模拟转账', cancel_subscription: '取消代扣',
  create_aa_collection: 'AA收款', schedule_transfer: '定时转账',
}
const states = {
  COMPLETED: '任务完成', REJECTED: '用户已拒绝', NOT_CONFIRMED: '银行结果待核查',
  WAITING_TRANSFER_APPROVAL: '等待转账审批', WAITING_APPROVAL: '等待代扣审批',
  WAITING_SCHEDULE_AUTH: '预约强制OTP验证', WAITING_RECIPIENT_SELECTION: '请选择收款人', WAITING_AA_CONFIRMATION: '确认AA收款请求', RECIPIENT_INVALID_SELECTION: '收款人选择无效',
  NEEDS_CLARIFICATION: '需要补充信息', NOT_IMPLEMENTED_YET: '未支持的操作',
  TARGET_NOT_FOUND: '未找到有效订阅', TARGET_AMBIGUOUS: '多个订阅匹配',
  TARGET_INVALID: '订阅信息异常', PAYEE_NOT_FOUND: '未找到收款人',
  PAYEE_AMBIGUOUS: '多个收款人匹配', INCOMPLETE: '查询未完成', UNKNOWN: '结果待核查',
}

watch([status, () => order.value?.orderId, () => cancellation.value?.orderId], () => {
  selectedRecipientId.value = null
  confirmed.value = false
  otp.value = ''
  otpRequested.value = false
  localError.value = ''
})
watch(() => props.otpNotice, value => { if (value) otpRequested.value = true })

function money(value) {
  const number = Number(value)
  return Number.isFinite(number) ? new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY' }).format(number) : '—'
}
function when(t) { return t.occurredAt || t.occurred_at || '' }
function merchant(s) { return s.merchantName || s.merchant_name || '未知商户' }
function labelOf(item) {
  if (item.type === 'monthly_analytics') return `${taskNames[item.type]}（${item.month || '月份待确认'}）`
  if (item.type === 'schedule_transfer') return `${taskNames[item.type]}（${money(item.amount)}，${item.execute_at || '待确认时间'}）`
  if (item.type === 'transfer_prepare') return `${taskNames[item.type]}（${item.payee_name || item.payee_phone || '未知'}，${money(item.amount)}）`
  if (item.type === 'create_aa_collection') return `${taskNames[item.type]}（${money(item.amount)}）`
  if (item.type === 'cancel_subscription') return `${taskNames[item.type]}（${item.target_name || '未知'}）`
  return taskNames[item.type] || item.type
}
function confirmRecipient() {
  if (props.busy || props.locked) return
  const id = Number(selectedRecipientId.value)
  if (!Number.isSafeInteger(id) || !recipientChoices.value.some(p => p.recipientId === id)) {
    localError.value = '请选择列表中的正确收款账户。'
    return
  }
  localError.value = ''
  emit('recipientSelect', { threadId: props.task.threadId, recipientId: id })
}
function approve(kind) {
  localError.value = ''
  if (props.busy || props.locked) return
  if (!confirmed.value) { localError.value = '请先核对金额和业务对象，并勾选明确确认。'; return }
  if ((kind === 'transfer' && riskRed.value) || kind === 'schedule') {
    if (!otpRequested.value) { localError.value = 'RED 风险请先向银行申请验证码。'; return }
    if (!/^\d{6}$/.test(otp.value)) { localError.value = '请填写银行提供的六位验证码。'; return }
  }
  const code = (kind === 'transfer' && riskRed.value) || kind === 'schedule' ? otp.value : undefined
  emit('decision', { threadId: props.task.threadId, kind, approved: true, otpCode: code })
  otp.value = '' // Never send OTP to model or store it in conversation messages.
}
function reject(kind) {
  if (props.busy || props.locked) return
  localError.value = ''
  emit('decision', { threadId: props.task.threadId, kind, approved: false })
  otp.value = ''
}
</script>

<template>
  <div class="workflow-results" :class="{ 'has-multiple-reads': readCount >= 2 }" aria-label="银行业务处理结果">
    <div class="result-status-row">
      <span class="result-status-icon" :class="{ 'is-done': status === 'COMPLETED', 'is-waiting': isTransferPending || isCancellationPending || choosingRecipient || isAaPending || isSchedulePending }" aria-hidden="true">{{ status === 'COMPLETED' ? '✓' : (isTransferPending || isCancellationPending || choosingRecipient || isAaPending || isSchedulePending ? '·' : 'i') }}</span>
      <span class="result-status-text">{{ states[status] || '处理结果' }}</span>
      <span v-if="planTasks.length > 1" class="result-multi">{{ planTasks.length }} 项任务</span>
    </div>

    <div v-if="showBalance" class="result-card balance-card" aria-label="账户余额">
      <div class="result-title"><span class="result-glyph blue" aria-hidden="true">¥</span><div><strong>账户余额</strong><small>{{ balance.accountNoMasked || '当前账户' }}</small></div><span class="result-title-side">实时查询</span></div>
      <div class="balance-amount">{{ money(balance.balance) }}</div>
      <p class="balance-hint">数据来自银行账户接口</p>
    </div>

    <div v-if="showTransactions" class="result-card">
      <div class="result-title"><span class="result-glyph lilac" aria-hidden="true">≡</span><div><strong>最近交易</strong><small>银行交易明细</small></div><span class="result-title-side">{{ transactions.length }} 笔</span></div>
      <div v-if="!transactions.length" class="empty-line">暂无交易记录</div>
      <div v-for="(t, i) in transactions.slice(0, 20)" :key="t.id || i" class="result-line"><div><strong>{{ merchant(t) }}</strong><small>{{ when(t) }} {{ t.category ? ' · ' + t.category : '' }}</small></div><b :class="t.direction === 'IN' ? 'money-in' : 'money-out'">{{ t.direction === 'IN' ? '+' : '−' }}{{ money(t.amount) }}</b></div>
      <p v-if="transactions.length > 20" class="soft-note">仅显示前 20 笔，完整结果可通过银行流水查看。</p>
    </div>

    <div v-if="showPayees" class="result-card">
      <div class="result-title"><span class="result-glyph lilac" aria-hidden="true">◇</span><div><strong>常用收款人</strong><small>已保存的银行收款账户</small></div></div>
      <div v-if="!payees.length" class="empty-line">暂无常用收款人</div>
      <div v-for="(p, i) in payees" :key="p.id || i" class="result-line"><div><strong>{{ p.payeeName || '未知收款人' }}</strong><small>{{ p.payeeAccountMasked || p.accountMasked || '' }}</small></div></div>
    </div>

    <div v-if="showSubscriptions" class="result-card">
      <div class="result-title"><span class="result-glyph teal" aria-hidden="true">↻</span><div><strong>自动扣费</strong><small>已开通的订阅和代扣协议</small></div><span class="result-title-side">{{ subscriptions.length }} 项</span></div>
      <div v-if="!subscriptions.length" class="empty-line">暂无订阅代扣</div>
      <div v-for="(s, i) in subscriptions" :key="s.id || i" class="result-line"><div><strong>{{ merchant(s) }}</strong><small>{{ s.billingCycle === 'MONTHLY' ? '每月扣费' : (s.billingCycle || '自动扣费') }} · {{ s.status === 'CANCELLED' ? '已取消' : (s.status === 'ACTIVE' ? '生效中' : s.status) }}</small></div><b>{{ money(s.amount) }}</b></div>
      <p v-if="cancellation" class="soft-note">这里展示的是任务开始时的订阅信息，最新状态以取消订单结果为准。</p>
    </div>

    <MonthlyAnalyticsCard v-if="showMonthly" :data="monthly" />

    <div v-if="choosingRecipient" class="result-card recipient-picker" aria-label="选择重名收款人">
      <div class="result-title"><span class="result-glyph blue" aria-hidden="true">◎</span><div><strong>请选择正确的收款人</strong><small>同名用户需要人工选择；目前未创建转账订单</small></div></div>
      <p class="recipient-tip">下列候选信息来自银行目录。请选择对应的脱敏账号，避免转给同名的其他人。</p>
      <div class="recipient-options">
        <label v-for="p in recipientChoices" :key="p.recipientId" class="recipient-option" :class="{ active: Number(selectedRecipientId) === p.recipientId }">
          <input v-model="selectedRecipientId" type="radio" name="transfer-recipient" :value="p.recipientId" :disabled="busy || locked" />
          <span class="recipient-person"><strong>{{ p.payeeName }}</strong><small>银行账户 {{ p.accountMasked }}</small></span>
          <span class="recipient-radio-mark" aria-hidden="true"></span>
        </label>
      </div>
      <div class="approval-actions"><button class="approval-primary" type="button" :disabled="busy || locked || selectedRecipientId == null" @click="confirmRecipient">确认收款对象并继续</button><button class="approval-secondary" type="button" :disabled="busy" @click="emit('recipientCancel', task.threadId)">放弃本次转账</button><button class="approval-secondary" type="button" :disabled="busy" @click="emit('refresh', task.threadId)">刷新任务状态</button></div>
    </div>

    <div v-if="order" class="result-card transfer-card" aria-label="转账订单">
      <div class="result-title"><span class="result-glyph blue" aria-hidden="true">↗</span><div><strong>模拟转账</strong><small>{{ order.status === 'SUCCESS' ? '银行已确认执行成功' : (order.status === 'CANCELLED' || order.status === 'REJECTED' ? '该笔转账已取消' : '请核对以下交易信息') }}</small></div><span class="risk-pill" :class="order.riskLevel === 'RED' ? 'risk-red' : order.riskLevel === 'YELLOW' ? 'risk-yellow' : 'risk-neutral'">{{ order.riskLevel === 'RED' ? '红色风险 · OTP' : (order.riskLevel === 'YELLOW' ? '黄色风险 · 需确认' : (order.riskLevel || '待核查')) }}</span></div>
      <div class="transfer-amount">{{ money(order.amount) }}</div>
      <div class="detail-grid"><div><span>收款人</span><strong>{{ order.payeeName || task.transferCandidate?.payeeName || '—' }}</strong></div><div><span>收款账户</span><strong>{{ order.accountMasked || task.transferCandidate?.accountMasked || '—' }}</strong></div><div v-if="order.remark || task.transferCandidate?.remark" class="transfer-remark"><span>转账备注</span><strong>{{ order.remark || task.transferCandidate?.remark }}</strong></div></div>
      <div class="order-current"><span>银行状态</span><strong :class="order.status === 'SUCCESS' ? 'state-success' : ''">{{ order.status === 'SUCCESS' ? '转账成功' : (order.status === 'PENDING_APPROVAL' ? '待批准' : (order.status || '核查中')) }}</strong></div>

    <div v-if="isTransferPending" class="approval-card transfer-approval" :class="{ 'approval-red': riskRed }" aria-label="转账人工审批">
      <div class="approval-heading"><span class="approval-mark" aria-hidden="true">!</span><div><strong>{{ riskRed ? '高风险转账 · 需完成安全验证' : '请核对并确认本笔转账' }}</strong><p>{{ riskRed ? '本笔交易须完成 OTP 验证后才能提交。' : '本笔交易需要由你明确确认后执行。' }}</p></div></div>
      <div v-if="riskRed" class="otp-area">
        <div class="otp-head"><div><strong>银行安全验证</strong><small>高风险转账需要一次性验证码</small></div><button type="button" class="otp-request" :disabled="busy || locked" @click="emit('otpRequest', task.threadId)">申请验证码</button></div>
        <p v-if="otpNotice" class="otp-feedback" role="status">{{ otpNotice }}</p>
        <input v-model="otp" type="password" inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="输入六位 OTP 验证码" aria-label="六位银行验证码" :disabled="busy || locked" />
        <p class="otp-hint">验证码仅用于本次授权，不会保存到聊天记录。</p>
      </div>
      <label class="approval-check"><input v-model="confirmed" type="checkbox" :disabled="busy || locked" /> <span>我已核对收款人、金额及账户，明确批准这笔模拟转账。</span></label>
      <div class="approval-actions"><button class="approval-primary" type="button" :disabled="busy || locked || !confirmed || (riskRed && (!otpRequested || !/^\d{6}$/.test(otp)))" @click="approve('transfer')">{{ busy ? '处理中…' : '确认转账' }}</button><button class="approval-secondary" type="button" :disabled="busy || locked" @click="reject('transfer')">拒绝转账</button></div>
    </div>
    </div>

    <div v-if="scheduled" class="result-card" aria-label="预约转账申请">
      <div class="result-title"><span class="result-glyph blue">◷</span><div><strong>单次定时转账</strong><small>预约成功并不代表已扣款</small></div><span class="result-title-side">需 OTP 授权</span></div>
      <div class="transfer-amount">{{ money(scheduled.amount) }}</div>
      <div class="detail-grid"><div><span>收款人</span><strong>{{ scheduled.payeeName }}</strong></div><div><span>银行收款账户</span><strong>{{ scheduled.accountMasked }}</strong></div><div><span>预定执行时间</span><strong>{{ scheduled.executeAt?.replace('T', ' ') }}</strong></div><div><span>预约状态</span><strong>{{ scheduled.status }}</strong></div><div v-if="scheduled.remark"><span>备注</span><strong>{{ scheduled.remark }}</strong></div></div>
      <p class="soft-note">OTP 用于授权固定金额、收款人和执行时间；到期由银行执行。错过执行窗口不补执行，失败不自动重试。</p>
    </div>
    <div v-if="isSchedulePending" class="approval-card approval-schedule" aria-label="定时转账强制OTP预授权">
      <div class="approval-heading"><span class="approval-mark">!</span><div><strong>请确认预约并完成强验证</strong><p>所有金额都必须提前 OTP。此时不会从账户扣款。</p></div></div>
      <div class="otp-area">
        <div class="otp-head"><div><strong>预约专属 OTP</strong><small>验证码只验证此笔固定预约，不会永久保存验证码</small></div><button type="button" class="otp-request" :disabled="busy || locked" @click="emit('otpRequest', task.threadId)">申请验证码</button></div>
        <p v-if="otpNotice" class="otp-feedback">{{ otpNotice }}</p>
        <input v-model="otp" type="password" inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="输入六位 OTP" :disabled="busy || locked" />
      </div>
      <label class="approval-check"><input v-model="confirmed" type="checkbox" :disabled="busy || locked"/><span>我已经核对收款人、金额、时间和备注，同意创建专属预授权。</span></label>
      <div class="approval-actions"><button type="button" class="approval-primary" :disabled="busy || locked || !confirmed || !otpRequested || !/^\d{6}$/.test(otp)" @click="approve('schedule')">验证 OTP 并预约</button><button type="button" class="approval-secondary" :disabled="busy || locked" @click="reject('schedule')">取消本次预约</button></div>
    </div>

    <div v-if="aaCollection" class="result-card" aria-label="AA收款申请">
      <div class="result-title"><span class="result-glyph blue" aria-hidden="true">◎</span><div><strong>AA 收款明细</strong><small>{{ aaCollection.reason || 'AA 费用分摊' }}</small></div><span class="result-title-side">{{ aaCollection.status === 'DRAFT' ? '待发布' : aaCollection.status === 'CANCELLED' ? '已撤销' : '银行已记录' }}</span></div>
      <div class="detail-grid" style="margin-top:16px"><div><span>费用总额</span><strong>{{ money(aaCollection.totalAmount) }}</strong></div><div><span>需要向其他人收取</span><strong>{{ money(aaCollection.requestedAmount) }}</strong></div><div><span>自己承担</span><strong>{{ money(aaCollection.selfAmount) }}</strong></div><div><span>已实际收到</span><strong>{{ money(aaCollection.receivedAmount) }}</strong></div></div>
      <div v-for="item in aaCollection.items" :key="item.itemId" class="result-line"><div><strong>{{ item.payerName }}</strong><small>独立确认后付款</small></div><b>{{ money(item.amount) }} · {{ item.status === 'PAID' ? '已支付' : item.status === 'DECLINED' ? '已拒绝' : '待付款' }}</b></div>
      <p class="soft-note">仅发布收款请求不会扣款。付款方登录自己的账户后才能批准并支付。</p>
    </div>
    <div v-if="isAaPending" class="approval-card" aria-label="AA发布人工确认">
      <div class="approval-heading"><span class="approval-mark" aria-hidden="true">!</span><div><strong>确认发布 AA 收款请求</strong><p>请核对每位付款人和金额；发布后不会立即从他人账户扣款。</p></div></div>
      <label class="approval-check"><input v-model="confirmed" type="checkbox" :disabled="busy || locked" /><span>我已核对收款人员和金额，明确同意发送以上收款请求。</span></label>
      <div class="approval-actions"><button class="approval-primary" type="button" :disabled="busy || locked || !confirmed" @click="approve('aa')">确认发布</button><button class="approval-secondary" type="button" :disabled="busy || locked" @click="reject('aa')">取消草稿</button></div>
    </div>

    <div v-if="cancellation" class="result-card cancel-card" aria-label="取消代扣申请">
      <div class="result-title"><span class="result-glyph teal" aria-hidden="true">↻</span><div><strong>取消自动扣费</strong><small>{{ task.candidate?.merchantName || '订阅服务' }}</small></div><span class="result-title-side">{{ cancellation.status === 'SUCCESS' ? '已取消' : cancellation.status === 'REJECTED' ? '已保留订阅' : '等待确认' }}</span></div>
      <div class="cancel-amount"><strong>{{ money(task.candidate?.amount) }}</strong><span>{{ task.candidate?.billingCycle === 'MONTHLY' ? '每月扣费' : '订阅金额' }}</span></div>
      <div class="order-current"><span>订阅状态</span><strong :class="cancellation.subscriptionStatus === 'CANCELLED' ? 'state-success' : ''">{{ cancellation.subscriptionStatus === 'CANCELLED' ? '已取消' : cancellation.subscriptionStatus === 'ACTIVE' ? '仍然有效' : (cancellation.subscriptionStatus || '待核查') }}</strong></div>
    </div>

    <div v-if="isCancellationPending" class="approval-card" aria-label="代扣取消人工审批">
      <div class="approval-heading"><span class="approval-mark" aria-hidden="true">!</span><div><strong>请确认取消自动扣费</strong><p>此次复合任务最多包含一项需要审批的业务，确认仅作用于这一项订阅。</p></div></div>
      <label class="approval-check"><input v-model="confirmed" type="checkbox" :disabled="busy || locked" /><span>我已核对订阅名称，明确同意取消这项自动扣费。</span></label>
      <div class="approval-actions"><button class="approval-primary" type="button" :disabled="busy || locked || !confirmed" @click="approve('cancel')">{{ busy ? '处理中…' : '确认取消' }}</button><button class="approval-secondary" type="button" :disabled="busy || locked" @click="reject('cancel')">保留订阅</button></div>
    </div>

    <div v-if="task.details && !['COMPLETED', 'WAITING_TRANSFER_APPROVAL', 'WAITING_APPROVAL', 'WAITING_RECIPIENT_SELECTION', 'WAITING_AA_CONFIRMATION', 'WAITING_SCHEDULE_AUTH'].includes(status)" class="result-detail-note">{{ task.details }}</div>
    <div v-if="localError || actionError" class="result-error" role="alert">{{ localError || actionError }}</div>
    <div v-if="locked" class="result-lock" role="alert">银行状态暂时无法确认，已锁定审批操作。请先核实原订单，避免重复提交。</div>
    <div v-if="task.threadId && (locked || isTransferPending || isCancellationPending || isAaPending || isSchedulePending || status === 'NOT_CONFIRMED')" class="approval-actions">
      <button type="button" class="approval-secondary" :disabled="busy" @click="emit('refresh', task.threadId)">刷新原任务状态</button>
      <button v-if="status === 'NOT_CONFIRMED' && typeof task.approvalDecision === 'boolean'" type="button" class="approval-secondary" :disabled="busy" @click="emit('recover', task.threadId, task.approvalDecision)">按原审批决定恢复</button>
    </div>
    <p v-if="task.bankOrderStatus" class="soft-note">银行原订单状态：{{ task.bankOrderStatus }}（不会自动创建新订单）</p>

    <details class="technical-details">
      <summary>查看订单信息</summary>
      <div v-if="order?.orderId">转账订单：{{ order.orderId }}</div>
      <div v-if="scheduled?.scheduleId">预约编号：{{ scheduled.scheduleId }}</div>
      <div v-if="cancellation?.orderId">代扣申请：{{ cancellation.orderId }}</div>
      <div v-if="task.threadId">任务编号：{{ task.threadId }}</div>
    </details>
  </div>
</template>

<style scoped>
.workflow-results{display:flex;flex-direction:column;gap:12px;width:min(640px,100%);min-width:0;margin-top:10px;color:#203552}
.result-status-row{display:flex;align-items:center;gap:9px;padding:1px 2px 5px}
.result-status-icon{display:grid;place-items:center;width:24px;height:24px;border-radius:8px;background:#eaf0fb;color:#5278a9;font-weight:800}
.result-status-icon.is-waiting{background:#fff2dc;color:#a77525;font-size:26px;line-height:0}
.result-status-icon.is-done{background:#e4f5eb;color:#168057;font-size:14px}
.result-status-text{font-size:12px;font-weight:700;color:#52677e}.result-multi{margin-left:auto;color:#8b9aae;font-size:11px}
.result-card{background:#fff;border:1px solid #e1e8f2;border-radius:16px;padding:20px 22px;box-shadow:0 4px 18px rgba(35,60,94,.035)}
.result-title{display:flex;align-items:center;gap:12px;min-width:0}
.result-title>div{min-width:0;display:grid;gap:3px}.result-title strong{font-size:14px;font-weight:750;color:#1b324e}.result-title small{font-size:11px;color:#8c9aab}
.result-title-side{font-size:11px;color:#6b88ab;background:#f1f6fc;padding:6px 9px;border-radius:7px;margin-left:auto;white-space:nowrap}
.result-glyph{display:grid;place-items:center;width:36px;height:36px;border-radius:11px;font-weight:800;font-size:17px;flex-shrink:0}
.result-glyph.blue{background:#e9f2ff;color:#3479c9}.result-glyph.lilac{background:#f0effd;color:#8071bb}.result-glyph.teal{background:#e7f8f4;color:#269b84}
.balance-card{background:linear-gradient(135deg,#fff 40%,#f3f8ff 100%)}
.balance-amount{font-size:clamp(28px,4vw,36px);font-weight:800;letter-spacing:-.9px;color:#164a82;margin:19px 0 6px;font-variant-numeric:tabular-nums}.balance-hint,.soft-note{font-size:11px;color:#92a0b0;line-height:1.65;margin:8px 0 0}
.result-line{display:flex;justify-content:space-between;align-items:center;gap:18px;padding:13px 0;border-bottom:1px solid #eff2f7;font-size:13px}
.result-line:last-of-type{border-bottom:0}.result-line>div{display:grid;gap:4px}.result-line strong{color:#273f5b;font-size:13px}.result-line small{color:#9aa6b3;font-size:11px}.result-line b{font-size:13px;color:#325171;font-weight:700;white-space:nowrap}.money-in,.state-success{color:#138660!important}.money-out{color:#2d577f!important}
.empty-line{padding:15px 2px 5px;color:#94a2b0;font-size:12px}
.transfer-amount{font-size:clamp(27px,4vw,36px);font-weight:800;text-align:center;color:#153d72;letter-spacing:-.8px;margin:23px 0 17px;font-variant-numeric:tabular-nums}
.detail-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-bottom:14px}
.detail-grid .transfer-remark{grid-column:1/-1}
.recipient-tip{font-size:12px;line-height:1.75;color:#6b8199;margin:16px 0 12px}
.recipient-options{display:grid;gap:9px;margin-bottom:16px}.recipient-option{display:flex;gap:12px;align-items:center;padding:13px 16px;border:1px solid #dce6f3;border-radius:12px;cursor:pointer;background:#f8fbff;transition:border-color .15s,background .15s}.recipient-option.active{border-color:#3688e6;background:#edf6ff;box-shadow:0 0 0 2px rgba(54,136,230,.08)}.recipient-option input{accent-color:#2078da;width:17px;height:17px}.recipient-person{display:grid;gap:4px}.recipient-person strong{font-size:13px;color:#173954}.recipient-person small{font-size:11px;color:#6c829b}
.detail-grid>div{background:#f6f9fd;border-radius:10px;padding:12px;display:flex;flex-direction:column;gap:6px;min-width:0}.detail-grid span{font-size:11px;color:#8797aa}.detail-grid strong{font-size:13px;color:#213c5b;overflow-wrap:anywhere}
.order-current{border-top:1px solid #edf1f7;padding-top:13px;display:flex;justify-content:space-between;gap:12px;font-size:12px;color:#8394a6}.order-current strong{color:#44617e}
.risk-pill{margin-left:auto;white-space:nowrap;font-size:11px;font-weight:650;padding:7px 9px;border-radius:8px}.risk-yellow{background:#fff3df;color:#a77525}.risk-red{background:#fff0ed;color:#c05242}
.cancel-amount{display:flex;align-items:baseline;gap:10px;margin:21px 0 16px}.cancel-amount strong{font-size:27px;color:#1d456e}.cancel-amount span{font-size:12px;color:#95a2b0}
.approval-card{border:1px solid #ecd8b6;background:#fffaf1;border-radius:16px;padding:19px 20px}
.approval-heading{display:flex;gap:10px;align-items:flex-start}.approval-mark{display:grid;place-items:center;border-radius:9px;background:#ffe6ad;color:#916519;width:30px;height:30px;font-weight:800;flex-shrink:0}.approval-heading strong{font-size:14px;color:#5d491f}.approval-heading p{font-size:12px;color:#9e865c;line-height:1.6;margin:4px 0 0}
.approval-check{display:flex;align-items:flex-start;gap:10px;line-height:1.7;color:#6d634f;font-size:12px;margin:17px 0 14px}.approval-check input{accent-color:#2372c4;flex-shrink:0;margin-top:4px;width:15px;height:15px}
.approval-actions{display:flex;gap:10px;flex-wrap:wrap}.approval-actions button{border-radius:10px;padding:11px 18px;font-weight:700;font-size:12px;transition:transform .15s,box-shadow .15s}.approval-actions button:not(:disabled):hover{transform:translateY(-1px)}.approval-primary{background:#236ebc;color:white;border:1px solid #236ebc;box-shadow:0 3px 8px rgba(35,110,188,.17)}.approval-secondary{background:white;color:#51677e;border:1px solid #d5e0ea}.approval-actions button:disabled{opacity:.45;cursor:not-allowed;box-shadow:none}
.otp-area{background:white;border:1px solid #efdfc5;border-radius:12px;padding:14px;margin-top:14px}.otp-head{display:flex;justify-content:space-between;gap:8px;align-items:center}.otp-head>div{display:grid;gap:4px}.otp-head strong{font-size:12px;color:#4b5c6e}.otp-head small,.otp-hint{font-size:11px;color:#98a3af}.otp-request{border:1px solid #ccd9e8;background:#f5f9ff;color:#346b9f;border-radius:8px;padding:9px 12px;font-size:11px;white-space:nowrap}.otp-area>input{width:min(260px,100%);border:1px solid #ccd8e5;border-radius:9px;padding:11px 12px;margin-top:13px;letter-spacing:2px;font-weight:650}.otp-feedback{font-size:11px;color:#347258;margin:10px 0 0}.otp-hint{margin:8px 0 0}
.result-detail-note{font-size:12px;color:#596f84;line-height:1.7;padding:12px 15px;background:#f2f6fc;border-radius:10px;overflow-wrap:anywhere}.result-error,.result-lock{font-size:12px;line-height:1.7;padding:12px 14px;border-radius:10px}.result-error{background:#fff0f1;color:#b64040}.result-lock{background:#fff5df;color:#916519}
.technical-details{font-size:11px;color:#94a2af;padding:1px 3px}.technical-details summary{cursor:pointer;display:inline-block;font-size:11px;color:#93a4b7}.technical-details>div{padding:5px 0;overflow-wrap:anywhere}
@media(max-width:550px){.result-card{padding:16px}.approval-card{padding:16px}.detail-grid{grid-template-columns:1fr}.approval-actions button{flex:1}.result-title{gap:8px}.result-title-side,.risk-pill{font-size:10px}.result-line{gap:8px}}

/* Bank-style results: slim borders, restrained typography, no decorative gradients. */
.workflow-results{width:min(810px,100%);gap:13px;margin-top:13px;color:#172b46}
.result-status-row{padding:0 2px 2px}
.result-status-text{font-size:13px;color:#455c75}
.result-card{border-radius:14px;padding:22px 24px;border-color:#dfe6ef;box-shadow:0 7px 25px rgba(26,54,85,.035)}
.result-title strong{font-size:16px;font-weight:750;color:#162a44}
.result-title small{font-size:12px;color:#798aa0}
.result-title-side{background:#f4f7fb;color:#647992;font-size:12px}
.result-glyph{width:37px;height:37px;border-radius:10px;font-size:18px}
.result-glyph.blue,.result-glyph.lilac,.result-glyph.teal{background:#edf3fb;color:#2467b3}
.balance-card{background:#fff}
.balance-amount{color:#142b49;letter-spacing:-1px;font-size:clamp(30px,4vw,40px);margin:20px 0 6px}
.balance-hint,.soft-note{font-size:12px;line-height:1.7;color:#8091a7}
.result-line{padding:14px 0;gap:14px}
.result-line strong,.result-line b{font-size:14px}
.result-line small{font-size:12px;color:#7f90a5}
.money-in{color:#148458!important}.money-out{color:#1d3350!important}
.transfer-amount{text-align:left;font-size:clamp(30px,4vw,40px);color:#142b49;margin:20px 0 17px}
.detail-grid{gap:0;border-top:1px solid #e8edf3;margin-bottom:10px}
.detail-grid>div{background:transparent;border-bottom:1px solid #e8edf3;border-radius:0;padding:13px 2px;display:grid;grid-template-columns:minmax(90px,32%) 1fr;align-items:center;gap:10px}
.detail-grid .transfer-remark{grid-column:1/-1}
.detail-grid span{font-size:13px;color:#76869b}
.detail-grid strong{font-size:14px;font-weight:650;color:#182d47}
.risk-pill{font-size:12px;border-radius:7px;padding:7px 11px}
.risk-yellow{background:#fff3df;color:#96600b}.risk-red{background:#fcebed;color:#b52c38}
.approval-card{border:1px solid #ebdcbd;background:#fff9eb;border-radius:12px;padding:18px 21px;box-shadow:none}
.approval-heading strong{font-size:14px;color:#805612}
.approval-heading p{font-size:13px;color:#8c6f40}
.approval-mark{background:#fae6b9;color:#8d6116}
.approval-card.approval-red{border-color:#efcfd1;background:#fff2f2}
.approval-red .approval-mark{background:#fce2e4;color:#a82937}
.approval-red .approval-heading strong{color:#a32c38}
.approval-red .approval-heading p{color:#9b5b63}
.approval-card.approval-schedule{background:#fafbfc;border-color:#e2e8f0}
.approval-schedule .approval-heading strong{color:#263e59}
.approval-schedule .approval-heading p{color:#65788f}
.approval-schedule .approval-mark{background:#e8eef7;color:#38648f}
.approval-check{font-size:13px;color:#47576b}
.approval-actions button{font-size:13px;padding:11px 20px}
.approval-primary{background:#1464d2;border-color:#1464d2;box-shadow:none}
.approval-primary:hover:not(:disabled){background:#0e57bd}
.otp-area{border-color:#e7dadd;border-radius:10px;margin-top:14px}
.otp-head strong{font-size:13px}.otp-head small{font-size:12px}
.otp-request,.technical-details summary{font-size:12px}
.technical-details{font-size:12px}.result-detail-note{background:#f5f7fa;font-size:13px}
@media(max-width:550px){.result-card{padding:17px}.detail-grid>div{grid-template-columns:1fr;gap:4px}.transfer-amount{font-size:29px}.approval-card{padding:16px}}
</style>
