<script setup>
import { onMounted, onUnmounted, ref } from 'vue'

const props = defineProps({ fetcher: { type: Function, required: true }, userId: { type: Number, required: true } })
const open = ref(false)
const list = ref([])
const busy = ref(false)
const error = ref('')
const pending = ref({})
let alive = true
const money = v => Number.isFinite(Number(v)) ? new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY' }).format(Number(v)) : '—'
const state = { PENDING_AUTH: '待OTP授权', SCHEDULED: '已预约', PROCESSING: '执行中', SUCCESS: '已完成', CANCELLED: '已取消', FAILED: '执行失败', MISSED: '已错过，不补执行', UNKNOWN: '结果待核实' }
async function refresh() {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    const data = await props.fetcher('/api/agent/schedules')
    if (alive) list.value = Array.isArray(data) ? data : []
  } catch (e) { if (alive) error.value = `预约查询失败：${e.message}` }
  finally { if (alive) busy.value = false }
}
async function cancel(item) {
  if (busy.value || pending.value[item.scheduleId]) return
  if (!window.confirm(`确认取消给 ${item.payeeName} 的 ${money(item.amount)} 定时预约吗？`)) return
  busy.value = true
  error.value = ''
  const id = item.scheduleId
  const key = crypto.randomUUID()
  pending.value = { ...pending.value, [id]: key }
  try {
    await props.fetcher(`/api/agent/schedules/${encodeURIComponent(id)}/cancel`, 'POST', { requestId: key })
    if (alive) {
      const data = await props.fetcher('/api/agent/schedules')
      list.value = data
      const next = { ...pending.value }; delete next[id]; pending.value = next
    }
  } catch (e) {
    if (alive) error.value = `取消结果未确认：${e.message}。请先刷新银行预约状态，不要重复创建。`
  } finally { if (alive) busy.value = false }
}
function toggle() { open.value = !open.value; if (open.value) refresh() }
onMounted(refresh)
onUnmounted(() => { alive = false })
defineExpose({ refresh })
</script>

<template>
  <section class="schedule-center" aria-label="定时转账中心">
    <div class="schedule-top">
      <div class="schedule-heading"><span class="schedule-icon">◷</span><div><strong>定时转账</strong><small>已授权预约由银行到期执行，查看进度或取消尚未执行的计划</small></div></div>
      <button type="button" class="schedule-toggle" @click="toggle">{{ open ? '收起' : '查看预约' }}</button>
    </div>
    <div v-if="open" class="schedule-body">
      <p v-if="error" class="schedule-error" role="alert">{{ error }}</p>
      <button type="button" class="schedule-refresh" :disabled="busy" @click="refresh">{{ busy ? '查询中…' : '刷新银行状态' }}</button>
      <p v-if="!list.length" class="schedule-empty">暂无预约转账。可以在聊天框输入：“明天下午3点给李四转200元”。</p>
      <article v-for="item in list" :key="item.scheduleId" class="schedule-item">
        <div class="schedule-item-top"><strong>{{ item.payeeName }} · {{ money(item.amount) }}</strong><span class="schedule-state">{{ state[item.status] || item.status }}</span></div>
        <p>预约时间：{{ item.executeAt?.replace('T', ' ') }}</p>
        <p>收款账户：{{ item.accountMasked }}<span v-if="item.remark"> · {{ item.remark }}</span></p>
        <p v-if="item.failureReason" class="schedule-error">{{ item.failureReason }}</p>
        <p v-if="item.orderId">实际转账单号：{{ item.orderId }}</p>
        <button v-if="['SCHEDULED','PENDING_AUTH'].includes(item.status)" type="button" class="schedule-cancel" :disabled="busy || Boolean(pending[item.scheduleId])" @click="cancel(item)">取消本次预约</button>
      </article>
    </div>
  </section>
</template>

<style scoped>
.schedule-center{margin:10px 0 18px;background:linear-gradient(135deg,#fff,#f6faff);border:1px solid #e0eaf6;border-radius:16px;box-shadow:0 6px 22px rgba(26,65,115,.04);overflow:hidden}
.schedule-top{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:18px 20px}.schedule-heading{display:flex;align-items:center;gap:12px}.schedule-heading>div{display:grid;gap:4px}.schedule-heading strong{color:#203c61;font-size:15px}.schedule-heading small{font-size:11px;color:#8296ad;line-height:1.6}.schedule-icon{display:grid;place-items:center;background:#e9f2ff;color:#307bd8;width:38px;height:38px;border-radius:12px;font-size:23px}.schedule-toggle,.schedule-refresh,.schedule-cancel{background:white;border:1px solid #d7e4f5;color:#2369ac;border-radius:9px;padding:9px 14px;font-weight:650;font-size:12px;cursor:pointer}.schedule-body{padding:0 20px 19px}.schedule-refresh{margin:0 0 12px}.schedule-item{background:white;border:1px solid #e4ecf6;border-radius:12px;padding:14px 16px;margin:9px 0}.schedule-item-top{display:flex;align-items:center;justify-content:space-between;gap:10px}.schedule-item-top strong{color:#153d65;font-size:13px}.schedule-state{font-size:11px;color:#3476b6;background:#edf5ff;border-radius:8px;padding:5px 9px}.schedule-item p{font-size:12px;color:#72859b;margin:8px 0 0;overflow-wrap:anywhere}.schedule-item .schedule-error,.schedule-error{color:#b64b41;font-size:12px}.schedule-cancel{margin-top:12px;color:#a94a45;border-color:#e5cac8}.schedule-empty{color:#8598aa;font-size:12px;line-height:1.7}.schedule-toggle:disabled,.schedule-cancel:disabled{opacity:.5;cursor:not-allowed}@media(max-width:640px){.schedule-top{padding:14px}.schedule-heading small{font-size:10px}.schedule-body{padding:0 14px 14px}}
</style>
