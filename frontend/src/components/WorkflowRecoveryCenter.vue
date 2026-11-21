<script setup>
import { ref, watch } from 'vue'
import RecoveredTransferApproval from './RecoveredTransferApproval.vue'

const props = defineProps({
  conversationId: { type: String, default: '' },
  fetcher: { type: Function, required: true },
})
const items = ref([])
const selected = ref(null)
const busy = ref(false)
const error = ref('')
const selectedThread = ref('')
let revision = 0

function reset() {
  revision += 1
  items.value = []
  selected.value = null
  selectedThread.value = ''
  error.value = ''
  busy.value = false
}

async function refresh() {
  const conversation = props.conversationId
  const version = ++revision
  selected.value = null
  selectedThread.value = ''
  error.value = ''
  items.value = []
  if (!conversation) {
    error.value = '请先打开一个已保存的聊天会话。'
    return
  }
  busy.value = true
  try {
    const response = await props.fetcher(
      `/api/agent/workflows/sessions?conversationId=${encodeURIComponent(conversation)}`,
      'GET', undefined, 12000,
    )
    if (revision !== version) return
    if (!Array.isArray(response.items)) throw new Error('工作流列表响应无效')
    items.value = response.items
  } catch (e) {
    if (revision === version) error.value = e.message || '查询失败'
  } finally {
    if (revision === version) busy.value = false
  }
}

async function inspect(threadId) {
  const version = ++revision
  error.value = ''
  selected.value = null
  selectedThread.value = threadId
  busy.value = true
  try {
    const data = await props.fetcher(
      `/api/agent/workflows/dynamic/${encodeURIComponent(threadId)}/recovery`,
      'GET', undefined, 12000,
    )
    if (revision !== version) return
    // D5 read-only inspection remains intentionally unchanged.
    if (data.threadId !== threadId || data.canResume !== false || data.readOnly !== true) {
      throw new Error('恢复接口未返回受保护的只读结果')
    }
    selected.value = data
  } catch (e) {
    if (revision === version) error.value = e.message || '查询失败'
  } finally {
    if (revision === version) busy.value = false
  }
}

watch(() => props.conversationId, reset)
defineExpose({ refresh, reset })
</script>

<template>
  <section class="d5-recovery" aria-label="历史智能工作流">
    <header>
      <div><strong>工作流检查点</strong><p>当前会话 · 重启后只读核对及安全续接</p></div>
      <button type="button" :disabled="busy || !conversationId" @click="refresh">刷新</button>
    </header>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="busy" class="muted">正在向银行服务验证工作流归属……</p>
    <p v-if="!busy && !items.length && !error" class="muted">当前没有已加载的工作流，点击“刷新”查询。</p>
    <div v-for="s in items" :key="s.threadId" class="session">
      <div class="row"><strong>工作流</strong><span class="state">{{ s.expired ? '已过期' : s.status }}</span></div>
      <p class="id">{{ s.threadId }}</p>
      <p class="muted">创建：{{ s.createdAt }}</p>
      <p class="muted">有效期至：{{ s.expiresAt }}</p>
      <button type="button" :disabled="busy" @click="inspect(s.threadId)">只读检查原任务</button>
    </div>
    <section v-if="selected" class="inspection" aria-label="原工作流检查结果">
      <div class="row"><strong>恢复检查</strong><span>{{ selected.checkpointFound ? '已找到检查点' : '无检查点' }}</span></div>
      <p>原 threadId：<span class="id">{{ selected.threadId }}</span></p>
      <p>原 orderId：{{ selected.orderId || '当前线程没有银行订单' }}</p>
      <p>检查点状态：{{ selected.status }}</p>
      <p>银行订单实时状态：{{ selected.bankOrderStatus || 'UNKNOWN' }}</p>
      <p>待执行节点：{{ (selected.nextNodes || []).join('、') || '无' }}</p>
      <p class="muted">已过期：{{ selected.expired ? '是' : '否' }} · 本区只读查看</p>
      <p class="warning">D5 检查点本身不会执行银行操作。D6 仅允许经额外核验的模拟转账人工审批恢复。</p>
      <RecoveredTransferApproval
        v-if="selectedThread && selected.checkpointFound && !selected.expired && selected.status === 'WAITING_TRANSFER_APPROVAL'"
        :key="selectedThread"
        :thread-id="selectedThread"
        :fetcher="fetcher"
      />
    </section>
  </section>
</template>

<style scoped>
.d5-recovery{padding:16px;color:#263a56;font-size:13px}header,.row{display:flex;justify-content:space-between;align-items:center;gap:10px}header p,.muted{font-size:12px;color:#708199;line-height:1.6}button{border:1px solid #bfd1e9;background:#f3f8ff;color:#205c99;border-radius:8px;padding:7px 11px;cursor:pointer}button:disabled{opacity:.5;cursor:default}.session,.inspection{border:1px solid #dce4f0;border-radius:10px;margin-top:14px;padding:14px;overflow-wrap:anywhere}.session .id{font-family:monospace;font-size:11px;color:#6a7d96}.state{border-radius:8px;background:#fff6df;padding:4px 7px}.error{color:#b33434}.inspection p{line-height:1.55}.inspection .id{font-family:monospace;word-break:break-all}.warning{border-top:1px solid #edf1f6;padding-top:10px;color:#8a611d}
</style>
