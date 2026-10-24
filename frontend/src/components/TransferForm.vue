<script setup>
import { ref, computed } from 'vue'
const props = defineProps({ payees: { type: Array, default: () => [] }, payeeName: { type: String, default: '' }, amount: { type: String, default: '' }, requestId: { type: String, required: true }, busy: { type: Boolean, default: false }, completed: { type: Boolean, default: false } })
const emit = defineEmits(['prepare'])
const exact = props.payees.filter(p => p.payeeName === props.payeeName)
const payeeId = ref(exact.length === 1 ? String(exact[0].id) : '')
const transferAmount = ref(props.amount || '')
const remark = ref('')
const validationError = ref('')
const hasPayees = computed(() => props.payees.length > 0)
function submit() {
  validationError.value = ''
  if (!payeeId.value || !props.payees.some(p => String(p.id) === payeeId.value)) {
    validationError.value = '请从已保存的常用收款人中选择。'
    return
  }
  if (!/^(?:0|[1-9]\d{0,8})(?:\.\d{1,2})?$/.test(transferAmount.value)) {
    validationError.value = '金额格式错误：请填写数字，最多两位小数。'
    return
  }
  const value = Number(transferAmount.value)
  if (!(value > 0 && value <= 1_000_000)) {
    validationError.value = '金额必须大于零且不超过演示限额。'
    return
  }
  if (props.completed) return
  emit('prepare', { payeeId: Number(payeeId.value), amount: transferAmount.value, requestId: props.requestId, remark: remark.value.trim() })
}
</script>

<template>
  <section class="data-panel transfer-form" aria-label="转账草稿填写">
    <div class="panel-subtitle">转账草稿 · 只创建待审批订单</div>
    <form @submit.prevent="submit" class="transfer-fields">
      <label>收款人（仅限已保存账户）
        <select v-model="payeeId" :disabled="busy || completed || !hasPayees" required>
          <option value="">请选择收款人</option>
          <option v-for="p in payees" :key="p.id" :value="String(p.id)">{{ p.payeeName }} · {{ p.payeeAccountMasked }}</option>
        </select>
      </label>
      <label>金额（元）
        <input v-model="transferAmount" :disabled="busy || completed" inputmode="decimal" maxlength="14" placeholder="200.00" required />
      </label>
      <label>备注（可选）
        <input v-model="remark" :disabled="busy || completed" maxlength="80" placeholder="例如：AA 晚餐" />
      </label>
      <div v-if="validationError" class="validation-error" role="alert">{{ validationError }}</div>
      <button class="action-primary" type="submit" :disabled="busy || completed || !hasPayees">{{ completed ? '订单已创建' : (busy ? '正在创建订单…' : '创建待确认订单') }}</button>
    </form>
    <p class="security-note">本操作只向 Java 后端提交建单请求，不会扣款。Day 4 才开发用户确认与强验证。</p>
  </section>
</template>
