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
const emit = defineEmits(['decision', 'otpRequest'])
const confirmed = ref(false)
const otp = ref('')
const otpRequested = ref(false)
const localError = ref('')

const order = computed(() => props.task.transferOrder || null)
const cancellation = computed(() => props.task.cancellationOrder || null)
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
const outcomes = computed(() => props.task.writeOutcomes || {})

const taskNames = {
  get_balance: '查询余额', get_transactions: '最近交易', get_payees: '查询收款人',
  monthly_analytics: '月度收支分析', list_subscriptions: '查询代扣订阅',
  transfer_prepare: '模拟转账', cancel_subscription: '取消代扣',
}
const states = {
  COMPLETED: '全部完成', PARTIALLY_COMPLETED: '部分完成', REJECTED: '全部拒绝 / 已拒绝',
  WAITING_TRANSFER_APPROVAL: '等待转账审批', WAITING_APPROVAL: '等待代扣审批',
  NEEDS_CLARIFICATION: '需要补充信息', NOT_IMPLEMENTED_YET: '未支持的操作',
  TARGET_NOT_FOUND: '未找到有效订阅', TARGET_AMBIGUOUS: '多个订阅匹配',
  TARGET_INVALID: '订阅信息异常', PAYEE_NOT_FOUND: '未找到收款人',
  PAYEE_AMBIGUOUS: '多个收款人匹配', INCOMPLETE: '查询未完成', UNKNOWN: '结果待核查',
}

watch([status, () => order.value?.orderId, () => cancellation.value?.orderId], () => {
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
  if (item.type === 'transfer_prepare') return `${taskNames[item.type]}（${item.payee_name || '未知'}，${money(item.amount)}）`
  if (item.type === 'cancel_subscription') return `${taskNames[item.type]}（${item.target_name || '未知'}）`
  return taskNames[item.type] || item.type
}
function outcomeLabel(value) {
  return value === 'SUCCESS' ? '成功' : value === 'REJECTED' ? '已拒绝' : (value || '等待最终结果')
}
function approve(kind) {
  localError.value = ''
  if (!confirmed.value) { localError.value = '请先核对金额和业务对象，并勾选明确确认。'; return }
  if (kind === 'transfer' && riskRed.value) {
    if (!otpRequested.value) { localError.value = 'RED 风险请先向银行申请验证码。'; return }
    if (!/^\d{6}$/.test(otp.value)) { localError.value = '请填写银行提供的六位验证码。'; return }
  }
  const code = kind === 'transfer' && riskRed.value ? otp.value : undefined
  emit('decision', { threadId: props.task.threadId, kind, approved: true, otpCode: code })
  otp.value = '' // Never send OTP to model or store it in conversation messages.
}
function reject(kind) {
  localError.value = ''
  emit('decision', { threadId: props.task.threadId, kind, approved: false })
  otp.value = ''
}
</script>

<template>
  <section class="panel dynamic-workflow" aria-label="LangGraph 动态任务结果">
    <div class="wf-header">
      <strong>BankPilot · 动态任务工作流</strong>
      <span class="wf-state" :class="{ waiting: isTransferPending || isCancellationPending, done: status === 'COMPLETED' }">{{ states[status] || status }}</span>
    </div>
    <p class="wf-meta">线程 {{ task.threadId || '—' }}</p>

    <div v-if="planTasks.length" class="wf-block">
      <h4>任务规划</h4>
      <div v-for="(item, i) in planTasks" :key="`${item.type}-${i}`" class="wf-line">
        <span>{{ i + 1 }}. {{ labelOf(item) }}</span><span class="small-muted">{{ item.type }}</span>
      </div>
      <p class="small-muted">任务依赖由 LangGraph 补全；新增的查询依赖不需要再次审批。</p>
    </div>

    <div v-if="balance || transactions || payees || subscriptions" class="wf-block">
      <h4>银行查询结果</h4>
      <div v-if="balance" class="wf-balance">
        <span>账户余额 {{ balance.accountNoMasked || '' }}</span>
        <strong>{{ money(balance.balance) }}</strong>
      </div>
      <template v-if="transactions">
        <h5>交易流水</h5>
        <p v-if="!transactions.length" class="small-muted">暂无流水</p>
        <div v-for="(t, i) in transactions" :key="t.id || i" class="wf-line">
          <span>{{ merchant(t) }}<small>{{ when(t) }} · {{ t.category || '' }}</small></span>
          <strong>{{ t.direction === 'IN' ? '+' : '−' }}{{ money(t.amount) }}</strong>
        </div>
      </template>
      <template v-if="payees">
        <h5>常用收款人</h5>
        <p v-if="!payees.length" class="small-muted">暂无记录</p>
        <div v-for="(p, i) in payees" :key="p.id || i" class="wf-line">
          <span>{{ p.payeeName || '未知' }}</span><span>{{ p.payeeAccountMasked || p.accountMasked || '' }}</span>
        </div>
      </template>
      <template v-if="subscriptions">
        <h5>订阅代扣</h5>
        <p v-if="!subscriptions.length" class="small-muted">暂无订阅</p>
        <div v-for="(s, i) in subscriptions" :key="s.id || i" class="wf-line">
          <span>{{ merchant(s) }}<small>{{ s.status }} · {{ s.billingCycle || '' }}</small></span>
          <strong>{{ money(s.amount) }}</strong>
        </div>
        <p class="small-muted">上面为任务开始时的订阅快照；如已取消，请以下方订单核实状态为准。</p>
      </template>
    </div>

    <MonthlyAnalyticsCard v-if="monthly" :data="monthly" />

    <div v-if="order" class="wf-block">
      <div class="wf-title-row"><h4>转账订单</h4><span class="wf-risk" :class="order.riskLevel === 'RED' ? 'red' : 'yellow'">{{ order.riskLevel || '风险待核查' }}</span></div>
      <div class="wf-total">{{ money(order.amount) }}</div>
      <div class="wf-line"><span>收款人</span><strong>{{ order.payeeName || task.transferCandidate?.payeeName || '—' }}</strong></div>
      <div class="wf-line"><span>收款账户</span><strong>{{ order.accountMasked || task.transferCandidate?.accountMasked || '—' }}</strong></div>
      <div class="wf-line"><span>转账订单号</span><span class="wf-id">{{ order.orderId }}</span></div>
      <div class="wf-line"><span>银行订单状态</span><strong>{{ order.status }}</strong></div>
    </div>

    <div v-if="isTransferPending" class="wf-approval" aria-label="转账人工审批">
      <h4>第一项审批：确认本次转账</h4>
      <p>请核对收款人、掩码账号和金额。确认只授权这一笔转账，不代表同意取消代扣。</p>
      <div v-if="riskRed" class="otp-box">
        <div class="wf-actions">
          <button type="button" class="secondary" :disabled="busy || locked" @click="emit('otpRequest', task.threadId)">申请银行 OTP</button>
        </div>
        <p v-if="otpNotice" class="small-muted" role="status">{{ otpNotice }}</p>
        <label for="bank-otp" class="otp-label-inline">六位银行验证码
          <input id="bank-otp" v-model="otp" type="password" inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="请输入六位验证码" :disabled="busy || locked" />
        </label>
        <p class="small-muted">验证码由银行校验。请勿在聊天输入框发送 OTP。</p>
      </div>
      <label class="wf-check"><input v-model="confirmed" type="checkbox" :disabled="busy || locked" /> 我已核对本次转账信息，明确批准这笔模拟交易</label>
      <div class="wf-actions">
        <button type="button" class="primary" :disabled="busy || locked || !confirmed || (riskRed && (!otpRequested || !/^\d{6}$/.test(otp)))" @click="approve('transfer')">{{ busy ? '处理中…' : '批准本次转账' }}</button>
        <button type="button" class="secondary" :disabled="busy || locked" @click="reject('transfer')">拒绝转账</button>
      </div>
    </div>

    <div v-if="cancellation" class="wf-block">
      <h4>代扣取消申请</h4>
      <div class="wf-line"><span>订阅名称</span><strong>{{ task.candidate?.merchantName || '—' }}</strong></div>
      <div class="wf-line"><span>订阅金额</span><strong>{{ money(task.candidate?.amount) }}</strong></div>
      <div class="wf-line"><span>申请编号</span><span class="wf-id">{{ cancellation.orderId }}</span></div>
      <div class="wf-line"><span>申请状态</span><strong>{{ cancellation.status }}</strong></div>
      <div class="wf-line"><span>订阅状态</span><strong>{{ cancellation.subscriptionStatus || '待查询' }}</strong></div>
    </div>

    <div v-if="isCancellationPending" class="wf-approval" aria-label="取消代扣人工审批">
      <h4>{{ order ? '第二项审批：取消代扣' : '确认取消代扣' }}</h4>
      <p>批准后银行才会尝试取消当前订阅。拒绝后订阅保持有效。此决定与此前转账审批相互独立。</p>
      <label class="wf-check"><input v-model="confirmed" type="checkbox" :disabled="busy || locked" /> 我已核对订阅名称和金额，明确同意取消该项代扣</label>
      <div class="wf-actions">
        <button type="button" class="primary" :disabled="busy || locked || !confirmed" @click="approve('cancel')">{{ busy ? '处理中…' : '批准取消代扣' }}</button>
        <button type="button" class="secondary" :disabled="busy || locked" @click="reject('cancel')">拒绝，保留代扣</button>
      </div>
    </div>

    <div v-if="Object.keys(outcomes).length" class="wf-block">
      <h4>多业务最终结果</h4>
      <div v-if="outcomes.transfer_prepare" class="wf-line"><span>转账</span><strong>{{ outcomeLabel(outcomes.transfer_prepare) }}</strong></div>
      <div v-if="outcomes.cancel_subscription" class="wf-line"><span>取消代扣</span><strong>{{ outcomeLabel(outcomes.cancel_subscription) }}</strong></div>
      <p class="small-muted">不同业务之间不自动回滚已完成的银行交易。</p>
    </div>

    <p v-if="task.details" class="wf-note">{{ task.details }}</p>
    <p v-if="localError || actionError" class="wf-error" role="alert">{{ localError || actionError }}</p>
    <p v-if="locked" class="wf-warning" role="alert">银行状态存在不确定性，已锁定本卡片的审批按钮。请通过原银行订单号核查，勿再次创建相同订单。</p>
    <p class="wf-meta wf-footer">模型只规划任务；审批来自用户操作，最终结果以 Mock/Java 银行接口为准。</p>
  </section>
</template>

<style scoped>
.dynamic-workflow { width:min(740px,100%); max-width:100%; min-width:0; display:flex; flex-direction:column; gap:14px; box-sizing:border-box; }
.wf-header,.wf-title-row {display:flex;gap:10px;align-items:center;justify-content:space-between;flex-wrap:wrap}
.wf-header strong {font-size:14px;color:#223e60}
.wf-state {font-size:11px;background:#eef1f5;color:#61738b;border-radius:8px;padding:6px 9px}
.wf-state.waiting {background:#fff1d3;color:#8a621d}
.wf-state.done {background:#e4f7ee;color:#18764f}
.wf-meta,.small-muted {font-size:11px;color:#8293a7;line-height:1.7;overflow-wrap:anywhere}
.wf-meta {margin:0}.wf-footer{border-top:1px solid #e9eef5;padding-top:12px}
.wf-block {border:1px solid #e1e9f1;border-radius:12px;padding:14px;min-width:0}
.wf-block h4,.wf-approval h4{font-size:13px;color:#213d5b;margin:0 0 10px}
.wf-block h5 {font-size:12px;color:#506b86;margin:14px 0 7px}
.wf-block p.small-muted{margin-bottom:0}
.wf-line {display:flex;justify-content:space-between;gap:14px;align-items:flex-start;padding:9px 0;border-bottom:1px solid #eef2f7;font-size:12px;line-height:1.5}
.wf-line:last-child {border-bottom:0}
.wf-line span,.wf-line strong{min-width:0;overflow-wrap:anywhere}
.wf-line>span:first-child{color:#50657c}
.wf-line strong{text-align:right;color:#20374f}
.wf-line small{display:block;color:#8c9cad;margin-top:3px}
.wf-line .small-muted{font-size:10px}
.wf-balance{background:#eff5fd;border-radius:10px;padding:12px;display:flex;gap:6px;flex-direction:column}
.wf-balance span{font-size:12px;color:#71849c}.wf-balance strong{font-size:23px;color:#1d567f}
.wf-total{font-size:26px;font-weight:800;color:#164475;text-align:center;padding:10px 0}
.wf-risk{font-size:11px;border-radius:7px;padding:5px 8px}.wf-risk.red{background:#ffe8e8;color:#a53b3b}.wf-risk.yellow{background:#fff3d3;color:#9b6b1f}
.wf-id{overflow-wrap:anywhere;font-family:ui-monospace,monospace;text-align:right;color:#466587}
.wf-approval{background:#fff9ed;border:1px solid #f0dfb8;border-radius:12px;padding:14px}
.wf-approval p{font-size:12px;line-height:1.8;color:#70623e;margin:0 0 11px}
.wf-check{display:flex;gap:9px;align-items:flex-start;font-size:12px;line-height:1.65;color:#4b6178;margin-bottom:13px}
.wf-check input{margin-top:4px}
.wf-actions{display:flex;gap:9px;flex-wrap:wrap}.wf-actions button{border-radius:8px;padding:10px 13px;font-size:12px}
.otp-box{background:white;border:1px solid #efe3c8;border-radius:10px;padding:12px;margin-bottom:12px}
.otp-box p{margin-top:9px}.otp-label-inline{font-size:12px;color:#4a6179;display:flex;flex-direction:column;gap:6px;margin-top:10px}
.otp-label-inline input{border:1px solid #cbd7e5;border-radius:8px;padding:9px 11px;width:min(240px,100%)}
.wf-note{font-size:12px;color:#57708b;background:#eff5fc;border-radius:9px;padding:10px;margin:0;line-height:1.7}
.wf-error{font-size:12px;color:#ad3333;background:#fff0f0;border-radius:9px;padding:10px;margin:0;line-height:1.7}
.wf-warning{font-size:12px;color:#905d11;background:#fff3d4;border-radius:9px;padding:10px;margin:0;line-height:1.7}
@media(max-width:530px){.wf-line{gap:8px}.wf-actions button{flex:1}.wf-block{padding:11px}.dynamic-workflow{padding:12px}}
</style>
