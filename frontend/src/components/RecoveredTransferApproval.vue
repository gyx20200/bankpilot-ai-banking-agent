<script setup>
import { ref, watch } from 'vue'

// Deliberately isolated from DynamicWorkflowCard's in-process controls.
// Only allows explicitly re-confirming an independently preflighted transfer.
const props = defineProps({
  threadId: { type: String, required: true },
  fetcher: { type: Function, required: true },
})
const emit = defineEmits(['completed'])
const quote = ref(null)
const busy = ref(false)
const checked = ref(false)
const otpCode = ref('')
const otpMessage = ref('')
const error = ref('')
const outcome = ref(null)
const locked = ref(false)
let revision = 0

watch(() => props.threadId, () => {
  revision += 1
  quote.value = null
  checked.value = false
  otpCode.value = ''
  otpMessage.value = ''
  error.value = ''
  outcome.value = null
  locked.value = false
})

async function inspect() {
  const v = ++revision
  quote.value = null
  checked.value = false
  otpCode.value = ''
  error.value = ''
  busy.value = true
  try {
    const result = await props.fetcher(
      `/api/agent/workflows/recovery/${encodeURIComponent(props.threadId)}/preview`,
      'GET', undefined, 12000,
    )
    if (revision !== v) return
    if (!result.canResume || result.threadId !== props.threadId || result.bankOrderStatus !== 'PENDING_APPROVAL') {
      throw new Error('安全预检未通过')
    }
    quote.value = result
    locked.value = false
  } catch (e) {
    if (revision === v) error.value = e.message || '恢复预检失败'
  } finally {
    if (revision === v) busy.value = false
  }
}

async function requestOtp() {
  if (!quote.value || !quote.value.requiresOtp || busy.value || locked.value) return
  busy.value = true
  otpMessage.value = ''
  error.value = ''
  try {
    const result = await props.fetcher(
      `/api/agent/workflows/recovery/${encodeURIComponent(props.threadId)}/otp/request`,
      'POST', {}, 12000,
    )
    otpMessage.value = `已向模拟银行申请 OTP，请在有效期内输入（${result.expiresInSeconds}秒）。`
  } catch (e) {
    error.value = e.message || 'OTP 申请失败'
  } finally { busy.value = false }
}

async function act(approved) {
  if (!quote.value || !checked.value || busy.value || locked.value) return
  if (approved && quote.value.requiresOtp && !/^\d{6}$/.test(otpCode.value)) {
    error.value = '高风险转账需要6位银行OTP'
    return
  }
  busy.value = true
  locked.value = true // A network timeout may mean that Java already claimed.
  error.value = ''
  try {
    const result = await props.fetcher(
      `/api/agent/workflows/recovery/${encodeURIComponent(props.threadId)}/resume`,
      'POST', {
        approved,
        expectedCheckpointId: quote.value.checkpointId,
        expectedOrderId: quote.value.orderId,
        expectedAccountMasked: quote.value.accountMasked,
        expectedAmount: quote.value.amount,
        otpCode: approved && quote.value.requiresOtp ? otpCode.value : null,
      }, 30000,
    )
    otpCode.value = ''
    if (!result.approvalPersisted || result.threadId !== props.threadId) {
      throw new Error('银行与工作流结果没有全部确认')
    }
    outcome.value = result
    emit('completed', result)
  } catch (e) {
    otpCode.value = ''
    error.value = (e.message || '恢复结果未确认') + '。请只读查询原银行订单，禁止再次点击审批。'
  } finally { busy.value = false }
}
</script>

<template>
  <section class="recovery-approval" aria-label="重启后银行转账审批恢复">
    <div class="title"><strong>D6 · 恢复原转账审批</strong>
      <button type="button" :disabled="busy || locked" @click="inspect">核实原订单</button>
    </div>
    <p class="muted">仅恢复原线程，不重新创建转账订单。恢复前须重新验证当前登录身份。</p>
    <p v-if="error" class="warning" role="alert">{{ error }}</p>
    <p v-if="busy" class="muted">正在向银行核实工作流……</p>
    <div v-if="quote" class="details">
      <p>原订单：{{ quote.orderId }}</p>
      <p>收款人：<b>{{ quote.payeeName }}</b></p>
      <p>账户：<b>{{ quote.accountMasked }}</b></p>
      <p>金额：<strong>¥{{ quote.amount }}</strong></p>
      <p>备注：{{ quote.remark || '无' }}</p>
      <p>风险级别：{{ quote.riskLevel }} · 银行状态：{{ quote.bankOrderStatus }}</p>
      <p>有效期至：{{ quote.expiresAt }}</p>
      <div v-if="quote.requiresOtp && !locked" class="otp">
        <button type="button" :disabled="busy" @click="requestOtp">申请新的银行 OTP</button>
        <input v-model="otpCode" type="password" maxlength="6" inputmode="numeric"
               autocomplete="one-time-code" placeholder="6位OTP（确认转账时需要）" />
        <p class="muted">{{ otpMessage }}</p>
      </div>
      <label v-if="!locked" class="confirm">
        <input v-model="checked" type="checkbox" />
        我已核对收款人、账户尾号、金额及风险等级，理解此操作可能产生模拟资金变动。
      </label>
      <div v-if="!locked" class="buttons">
        <button type="button" :disabled="!checked || busy" @click="act(false)">拒绝并关闭原订单</button>
        <button type="button" class="danger" :disabled="!checked || busy" @click="act(true)">确认原订单转账</button>
      </div>
      <p v-else-if="outcome" class="success">银行已确认：{{ outcome.bankOrderStatus }}。请刷新原任务中心查看记录。</p>
      <p v-else-if="locked" class="warning">已提交恢复请求，当前结果未确认；不要重复发送。请刷新原订单状态。</p>
    </div>
  </section>
</template>

<style scoped>
.recovery-approval{border:1px solid #d7e3f3;border-radius:10px;padding:14px;margin-top:14px;color:#253a57;font-size:13px}
.title,.buttons{display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap}
button{border:1px solid #b5cee7;background:#f5f9ff;color:#255d92;border-radius:8px;padding:8px;cursor:pointer}
button:disabled{opacity:.5;cursor:default}.danger{background:#2265b8;color:white;border:0}
.muted{font-size:12px;color:#71839b}.warning{color:#a44c24}.success{color:#187b50}.details p{margin:8px 0;overflow-wrap:anywhere}
.otp{border-top:1px solid #eef1f5;padding-top:9px}.otp input{padding:7px;border:1px solid #bccfe1;border-radius:7px;max-width:220px;margin-left:8px}
.confirm{display:flex;gap:7px;margin:12px 0;line-height:1.7;align-items:flex-start}
</style>
