<script setup>
import { computed } from 'vue'
const props = defineProps({ data: { type: Object, required: true } })
const fmt = new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY' })
const money = v => v !== null && v !== undefined && Number.isFinite(Number(v)) ? fmt.format(Number(v)) : '—'
const months = computed(() => Array.isArray(props.data.monthlyBreakdown) ? props.data.monthlyBreakdown : [])
const categories = computed(() => Array.isArray(props.data.categories) ? props.data.categories : [])
const peak = computed(() => Math.max(1, ...months.value.flatMap(x => [Number(x.totalIncome) || 0, Number(x.totalExpense) || 0])))
const bar = v => `${Math.max(0, Math.min(100, Number(v) / peak.value * 100))}%`
</script>

<template>
  <section class="analytics-card" aria-label="年度收支分析">
    <header><span class="glyph">▥</span><div><strong>{{ data.year }} 年度收支分析</strong><small>{{ data.periodType === 'YEAR_TO_DATE' ? '本年累计 · 截至查询时' : '完整年度' }} · 模拟银行数据</small></div></header>
    <div class="totals">
      <div><small>收入</small><b class="in">{{ money(data.totalIncome) }}</b></div>
      <div><small>支出</small><b>{{ money(data.totalExpense) }}</b></div>
      <div><small>净现金流</small><b>{{ money(data.netCashFlow) }}</b></div>
    </div>
    <h4>月度收支趋势</h4>
    <div class="legend"><span><i class="swatch income"></i>收入</span><span><i class="swatch expense"></i>支出</span></div>
    <div v-for="m in months" :key="m.month" class="month-row">
      <span class="month-label">{{ m.month }}</span>
      <div class="bars">
        <div class="track"><div class="income bar" :style="{width: bar(m.totalIncome)}"></div></div>
        <div class="track"><div class="expense bar" :style="{width: bar(m.totalExpense)}"></div></div>
      </div>
      <div class="month-values"><span class="in">{{ money(m.totalIncome) }}</span><span>{{ money(m.totalExpense) }}</span></div>
    </div>
    <h4>支出分类</h4>
    <p v-if="!categories.length" class="note">暂无支出分类记录。</p>
    <div v-for="c in categories" :key="c.name" class="category-row"><span>{{ c.name }} · {{ c.count }} 笔</span><b>{{ money(c.amount) }}</b></div>
    <p class="note">统计包含转账等资金流入流出，不等同于纯消费。查询期间：{{ data.periodStart }} 至 {{ data.periodEndExclusive }}（不含截止时刻）。数据源：{{ data.source }}</p>
  </section>
</template>

<style scoped>
.analytics-card{background:#fff;border:1px solid #e1e8f2;border-radius:16px;padding:20px 22px;color:#203552;min-width:0}header{display:flex;gap:12px;align-items:center}header div{display:grid;gap:4px}header small,small,.note{font-size:11px;color:#8494a8}.glyph{display:grid;place-items:center;width:36px;height:36px;background:#e9f2ff;color:#3479c9;border-radius:11px;font-weight:800}.totals{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:18px 0}.totals div{display:grid;gap:7px;background:#f6f9fd;border-radius:10px;padding:12px;min-width:0}.totals b{font-size:clamp(12px,2.3vw,18px);overflow-wrap:anywhere;font-variant-numeric:tabular-nums}.in{color:#138660}h4{font-size:13px;margin:18px 0 10px}.legend{display:flex;gap:14px;font-size:11px;color:#63778e}.legend span{display:flex;align-items:center;gap:5px}.swatch{width:10px;height:10px;border-radius:2px;display:inline-block}.income{background:#219a78}.expense{background:#5484ca}.month-row{display:grid;grid-template-columns:64px minmax(30px,1fr) minmax(75px,100px);align-items:center;gap:9px;padding:8px 0;border-bottom:1px solid #eff2f7;font-size:11px}.month-label{font-variant-numeric:tabular-nums}.bars{display:grid;gap:5px}.track{background:#f0f4f9;height:7px;border-radius:4px;overflow:hidden}.bar{height:100%;border-radius:4px}.month-values{display:grid;text-align:right;gap:3px;overflow-wrap:anywhere}.category-row{display:flex;justify-content:space-between;gap:12px;font-size:12px;padding:10px 0;border-bottom:1px solid #eff2f7}.note{line-height:1.65;overflow-wrap:anywhere;margin:12px 0 0}@media(max-width:420px){.analytics-card{padding:14px}.totals{grid-template-columns:1fr}}
</style>
