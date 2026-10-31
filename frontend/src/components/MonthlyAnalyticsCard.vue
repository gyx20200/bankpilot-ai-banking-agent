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
        <div class="monthly-eyebrow">账户账单 / MONTHLY STATEMENT</div>
        <h4>月度收支分析 · {{ monthLabel }}</h4>
      </div>
      <span class="monthly-source">{{ data?.source === 'mysql' ? '银行统计' : '银行接口数据' }}</span>
    </div>

    <div v-if="!valid" class="monthly-empty" role="alert">
      收支统计数据格式异常，无法展示，请重试查询。
    </div>
    <template v-else>
      <div class="monthly-summary">
        <div class="monthly-metric">
          <span class="monthly-metric-label">本月收入</span>
          <strong class="monthly-positive">{{ money(data.totalIncome) }}</strong>
        </div>
        <div class="monthly-metric">
          <span class="monthly-metric-label">本月支出</span>
          <strong class="monthly-expense">{{ money(data.totalExpense) }}</strong>
        </div>
        <div class="monthly-metric monthly-net">
          <span class="monthly-metric-label">净现金流</span>
          <strong :class="netCashFlow >= 0 ? 'monthly-positive' : 'monthly-negative'">
            {{ netCashFlow > 0 ? '+' : '' }}{{ money(data.netCashFlow) }}
          </strong>
        </div>
      </div>

      <div class="monthly-section-title">
        <strong>支出分类</strong>
        <span>按银行流水类别汇总</span>
      </div>

      <div v-if="categories.length" class="monthly-categories">
        <div v-for="category in categories" :key="category.key" class="monthly-category">
          <div class="monthly-category-top">
            <span class="monthly-category-name">{{ category.name }}</span>
            <span class="monthly-category-value">{{ money(category.amount) }}</span>
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
          <div class="monthly-count">{{ category.count !== null ? `${category.count} 笔` : '—' }} · {{ percentText(category.percentage) }}</div>
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

/* Real bank-statement presentation, no calculated month-on-month or invented advice. */
.monthly-card{width:min(810px,100%);border:1px solid #dfe7f0;border-radius:14px;padding:23px 25px;box-shadow:0 7px 25px rgba(26,54,85,.035)}
.monthly-heading h4{font-size:20px;color:#172b44;line-height:1.4;margin-top:7px}
.monthly-eyebrow{font-size:11px;color:#768aa1;letter-spacing:1.2px}
.monthly-source{border:1px solid #e2e8f0;background:#fff;font-size:11px;color:#6c7d90}
.monthly-summary{grid-template-columns:repeat(3,minmax(0,1fr));gap:0;margin:24px 0;border-top:1px solid #e9eef4;border-bottom:1px solid #e9eef4;padding:23px 0}
.monthly-metric,.monthly-net{grid-column:auto;background:none;border-radius:0;padding:0 12px 0 0}
.monthly-metric + .monthly-metric{border-left:1px solid #e3e9f0;padding-left:20px}
.monthly-metric-label{font-size:13px;margin-bottom:9px}
.monthly-metric strong,.monthly-net strong{font-size:clamp(17px,2.5vw,25px);font-weight:760;letter-spacing:-.5px}
.monthly-positive{color:#182f4c}.monthly-net .monthly-positive{color:#1963b4}.monthly-negative{color:#ba343d}
.monthly-expense{color:#182f4c}
.monthly-section-title{margin-bottom:12px}.monthly-section-title strong{font-size:15px;color:#1c324e}.monthly-section-title span{font-size:12px}
.monthly-categories{gap:0}.monthly-category{display:grid;grid-template-columns:minmax(75px,.8fr) minmax(100px,2.2fr) minmax(75px,.65fr) minmax(90px,1fr);align-items:center;gap:12px;padding:13px 0;border-bottom:1px solid #edf1f5}
.monthly-category-top{display:contents}.monthly-category-name{grid-column:1;grid-row:1;font-size:14px;color:#273d56}.monthly-category-value{grid-column:4;grid-row:1;text-align:right;font-size:14px;font-weight:670;color:#22364e}
.monthly-track{grid-column:2;grid-row:1;margin:0;height:6px;background:#ecf0f5;border-radius:8px}.monthly-bar{background:#3978b9}
.monthly-count{grid-column:3;grid-row:1;font-size:12px;margin:0;color:#788b9e;white-space:nowrap;text-align:right}
.monthly-footnote{margin-top:16px;padding-top:14px;font-size:11px;color:#7d8ca0}
@media(max-width:620px){.monthly-card{padding:18px}.monthly-summary{grid-template-columns:1fr;gap:13px;padding:16px 0}.monthly-metric + .monthly-metric{border-left:0;border-top:1px solid #edf1f5;padding:12px 0 0}.monthly-metric{padding:0}.monthly-category{grid-template-columns:70px minmax(40px,1fr) 62px;gap:8px}.monthly-category-top{display:contents}.monthly-category-value{grid-column:3}.monthly-track{grid-column:2}.monthly-count{grid-column:2;text-align:left;grid-row:2}.monthly-category{row-gap:6px}.monthly-category-name{grid-column:1;grid-row:1}.monthly-track{grid-row:1}.monthly-category-value{grid-row:1}}
</style>
