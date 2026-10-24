<script setup>
defineProps({ order: { type: Object, required: true } })
function money(amount) {
  const n = Number(amount)
  return Number.isFinite(n) ? new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY' }).format(n) : '—'
}
</script>

<template>
  <section class="data-panel order-card" aria-label="待确认转账订单">
    <div class="order-heading"><span>转账订单预览</span><span class="risk-badge" :class="order.riskLevel === 'RED' ? 'risk-red' : 'risk-yellow'">{{ order.riskLevel === 'RED' ? '红色 · 强验证' : '黄色 · 用户确认' }}</span></div>
    <div class="order-money">{{ money(order.amount) }}</div>
    <dl class="order-details">
      <div><dt>收款人</dt><dd>{{ order.payeeName }}</dd></div>
      <div><dt>收款账户</dt><dd>{{ order.accountMasked }}</dd></div>
      <div><dt>订单编号</dt><dd class="break-id">{{ order.orderId }}</dd></div>
      <div><dt>订单状态</dt><dd>{{ order.status === 'PENDING_APPROVAL' ? '待用户确认' : order.status }}</dd></div>
    </dl>
    <div class="order-awaiting">⏳ 尚未扣款；待 Day 4 接入银行后端审批与验证。</div>
  </section>
</template>
