<script setup>
import { computed, ref, watch } from 'vue'
const props = defineProps({ data: { type: Object, required: true } })
const fmt = new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY' })
const money = v => v !== null && v !== undefined && Number.isFinite(Number(v)) ? fmt.format(Number(v)) : '—'
const items = computed(() => Array.isArray(props.data.items) ? props.data.items : [])
const shown = ref(20)
watch(() => props.data, () => { shown.value = 20 })
const label = code => ({LARGE_OUTFLOW: '大额支出', POSSIBLE_DUPLICATE: '疑似重复扣费'})[code] || '待核实事件'
</script>

<template>
  <section class="anomaly-card" aria-label="异常交易检测">
    <header><span class="glyph">!</span><div><strong>{{ data.month }} 异常交易检测</strong><small>模拟规则 · 只读分析</small></div></header>
    <div class="totals"><div><small>已扫描支出</small><b>{{ data.scannedCount }} 笔</b></div><div><small>命中规则事件</small><b>{{ data.anomalyCount }} 条</b></div></div>
    <p class="rules">大额支出阈值 {{ money(data.largeOutflowThreshold) }}；同账户、同商户、同金额且间隔不超过 {{ data.duplicateWindowMinutes }} 分钟为疑似重复。</p>
    <p v-if="!items.length" class="empty">本次扫描没有发现命中上述规则的事件，不代表所有交易均安全。</p>
    <article v-for="event in items.slice(0, shown)" :key="`${event.transactionId}-${event.ruleCode}`" class="event">
      <div class="event-top"><strong>{{ label(event.ruleCode) }}</strong><b>{{ money(event.amount) }}</b></div>
      <div class="meta">{{ event.merchantName || '未知商户' }} · {{ event.category }} · {{ event.occurredAt }}</div>
      <div class="meta">交易编号：{{ event.transactionId }}<span v-if="event.relatedTransactionId != null"> · 前一笔：{{ event.relatedTransactionId }}</span></div>
      <p>{{ event.reason }}</p>
    </article>
    <p v-if="items.length > shown" class="meta">已显示 {{ shown }} / {{ items.length }} 条规则事件。</p>
    <button v-if="items.length > shown" type="button" @click="shown += 20">显示更多</button>
    <p class="note">规则命中不等于已确认盗刷或重复扣款。同一笔交易可命中多条规则。未执行冻结、退款或资金操作。查询截止：{{ data.periodEndExclusive }}（不含）。</p>
  </section>
</template>

<style scoped>
.anomaly-card{background:#fff;border:1px solid #e1e8f2;border-radius:16px;padding:20px 22px;color:#203552;min-width:0}header{display:flex;gap:12px;align-items:center}header div{display:grid;gap:4px}header small,small,.meta,.note{font-size:11px;color:#8494a8}.glyph{display:grid;place-items:center;width:36px;height:36px;border-radius:11px;background:#fff2dc;color:#a77525;font-weight:800}.totals{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:18px 0}.totals div{display:grid;gap:6px;border-radius:10px;background:#f6f9fd;padding:12px}.totals b{font-size:18px}.rules,.empty{font-size:12px;line-height:1.7;color:#657d99}.event{border-top:1px solid #eff2f7;padding:12px 0;overflow-wrap:anywhere}.event-top{display:flex;justify-content:space-between;gap:12px;font-size:13px;color:#9a6524}.meta{margin:5px 0}.event p,.note{font-size:11px;line-height:1.7;margin:6px 0 0}.note{margin:14px 0 0}button{font:inherit;font-size:12px;padding:7px 12px;border:1px solid #dce6f3;border-radius:8px;background:#f8fbff;color:#325171;cursor:pointer}
</style>
