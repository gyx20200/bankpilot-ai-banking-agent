<script setup>
import { computed } from 'vue'

// 只展示 Agent 返回的银行统计结果；不在前端自行汇总银行流水。
const props = defineProps({
  data: { type: Object, required: true }
})

const toNumber = (value) => {
  if (value === null || value === undefined || value === '') return NaN
  const n = Number(value)
  return Number.isFinite(n) ? n : NaN
}

const money = (value) => {
  const n = toNumber(value)
  if (!Number.isFinite(n)) return '—'
  return new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency: 'CNY',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(n)
}

const monthLabel = computed(() => {
  const month = props.data?.month
  if (typeof month !== 'string' || !/^\d{4}-(0[1-9]|1[0-2])$/.test(month)) return '未知月份'
  const [year, mm] = month.split('-')
  return `${year} 年 ${Number(mm)} 月`
})

const income = computed(() => toNumber(props.data?.totalIncome))
const expense = computed(() => toNumber(props.data?.totalExpense))
const netCashFlow = computed(() => toNumber(props.data?.netCashFlow))
const valid = computed(() =>
  monthLabel.value !== '未知月份' &&
  Number.isFinite(income.value) &&
  Number.isFinite(expense.value) &&
  Number.isFinite(netCashFlow.value) &&
  income.value >= 0 && expense.value >= 0
)

const categories = computed(() => {
  if (!Array.isArray(props.data?.categories)) return []
  return props.data.categories
    .filter(item => item && Number.isFinite(toNumber(item.amount)) && toNumber(item.amount) > 0)
    .map((item, index) => {
      const amount = toNumber(item.amount)
      const percentage = expense.value > 0 ? (amount / expense.value) * 100 : 0
      const count = toNumber(item.count)
      return {
        key: `${String(item.name ?? '未分类')}-${index}`,
        name: String(item.name || '未分类'),
        amount,
        count: Number.isInteger(count) && count >= 0 ? count : null,
        percentage: Math.max(0, Math.min(100, percentage))
      }
    })
    .sort((a, b) => b.amount - a.amount)
})

const percentText = value => `${value.toFixed(1)}%`
</script>

<template>
  <section class="panel monthly-card" aria-label="月度收支分析">
    <div class="monthly-heading">
      <div>
        <div class="monthly-eyebrow">MONTHLY CASH FLOW</div>
        <h4>月度收支分析 · {{ monthLabel }}</h4>
      </div>
      <span class="monthly-source">{{ data?.source === 'mysql' ? 'MySQL 统计' : '银行接口数据' }}</span>
    </div>

    <div v-if="!valid" class="monthly-empty" role="alert">
      收支统计数据格式异常，无法展示，请重试查询。
    </div>
    <template v-else>
      <div class="monthly-summary">
        <div class="monthly-metric">
          <span class="monthly-metric-label">当月总收入</span>
          <strong class="monthly-positive">{{ money(data.totalIncome) }}</strong>
        </div>
        <div class="monthly-metric">
          <span class="monthly-metric-label">当月总支出</span>
          <strong class="monthly-expense">{{ money(data.totalExpense) }}</strong>
        </div>
        <div class="monthly-metric monthly-net">
          <span class="monthly-metric-label">净现金流（收入－支出）</span>
          <strong :class="netCashFlow >= 0 ? 'monthly-positive' : 'monthly-negative'">
            {{ netCashFlow > 0 ? '+' : '' }}{{ money(data.netCashFlow) }}
          </strong>
        </div>
      </div>

      <div class="monthly-section-title">
        <strong>支出构成</strong>
        <span>按银行流水类别汇总</span>
      </div>

      <div v-if="categories.length" class="monthly-categories">
        <div v-for="category in categories" :key="category.key" class="monthly-category">
          <div class="monthly-category-top">
            <span class="monthly-category-name">{{ category.name }}</span>
            <span class="monthly-category-value">{{ money(category.amount) }} · {{ percentText(category.percentage) }}</span>
          </div>
          <div
            class="monthly-track"
            role="progressbar"
            :aria-label="`${category.name}支出占比`"
            :aria-valuenow="Number(category.percentage.toFixed(1))"
            aria-valuemin="0"
            aria-valuemax="100"
          >
            <div class="monthly-bar" :style="{ width: `${category.percentage}%` }"></div>
          </div>
          <div v-if="category.count !== null" class="monthly-count">{{ category.count }} 笔</div>
        </div>
      </div>
      <p v-else class="monthly-empty">该月暂无可展示的支出分类。</p>

      <div class="monthly-footnote">
        <span>统计月份：{{ data.month }} · 币种：{{ data.currency || 'CNY' }}</span>
        <span>提示：总支出包含账户转账转出，不等同于纯消费金额；以上为模拟银行数据。</span>
      </div>
    </template>
  </section>
</template>

<style scoped>
.monthly-card { width: min(590px, 100%); min-width: 0; }
.monthly-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.monthly-heading h4 { margin: 5px 0 0; line-height: 1.5; }
.monthly-eyebrow { font-size: 10px; font-weight: 750; color: #5f85b5; letter-spacing: 1px; }
.monthly-source { flex-shrink: 0; padding: 5px 8px; border-radius: 7px; background: #edf5ff; color: #356b9b; font-size: 10px; }
.monthly-summary { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin: 17px 0 20px; }
.monthly-metric { padding: 13px; background: #f5f8fc; border-radius: 11px; min-width: 0; }
.monthly-metric-label { display: block; color: #71849a; font-size: 11px; line-height: 1.5; margin-bottom: 7px; }
.monthly-metric strong { display: block; font-size: clamp(15px, 3vw, 21px); font-weight: 800; overflow-wrap: anywhere; font-variant-numeric: tabular-nums; }
.monthly-net { grid-column: 1 / -1; background: #eff5fc; }
.monthly-net strong { font-size: clamp(18px, 3vw, 24px); }
.monthly-positive { color: #187957; }
.monthly-expense { color: #2f5578; }
.monthly-negative { color: #bc4b4b; }
.monthly-section-title { display: flex; flex-wrap: wrap; gap: 5px 12px; align-items: baseline; justify-content: space-between; margin-bottom: 14px; }
.monthly-section-title strong { font-size: 13px; color: #243e59; }
.monthly-section-title span { color: #8798a8; font-size: 11px; }
.monthly-categories { display: grid; gap: 14px; }
.monthly-category-top { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 5px 12px; align-items: baseline; font-size: 12px; }
.monthly-category-name { font-weight: 650; color: #324c65; }
.monthly-category-value { color: #455f79; font-variant-numeric: tabular-nums; }
.monthly-track { height: 9px; margin-top: 7px; background: #edf1f7; border-radius: 20px; overflow: hidden; }
.monthly-bar { height: 100%; background: linear-gradient(90deg, #4687d2, #79a9dc); border-radius: inherit; }
.monthly-count { font-size: 10px; color: #8b9aac; margin-top: 4px; }
.monthly-empty { color: #72869a; background: #f5f8fc; padding: 12px; border-radius: 9px; font-size: 12px; margin-top: 12px; }
.monthly-footnote { border-top: 1px solid #e9eef4; margin-top: 18px; padding-top: 12px; display: grid; gap: 5px; color: #8495a7; font-size: 10px; line-height: 1.6; }
@media (max-width: 520px) { .monthly-card { width: 100%; } .monthly-heading { flex-wrap: wrap; } .monthly-summary { gap: 7px; } .monthly-metric { padding: 10px; } }
</style>
