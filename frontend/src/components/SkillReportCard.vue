
<script setup>
import { computed } from 'vue'
import MonthlyAnalyticsCard from './MonthlyAnalyticsCard.vue'
import TransactionAnomalyCard from './TransactionAnomalyCard.vue'

const props = defineProps({
  data: {
    type: Object,
    required: true
  }
})

const rows = computed(() =>
    Array.isArray(props.data?.steps)
        ? props.data.steps
        : []
)

const valid = computed(() =>
    props.data?.readOnly === true &&
    props.data?.status === 'COMPLETED' &&
    props.data?.dataOrigin === 'JAVA_MYSQL_VIA_MCP'
)

const names = {
  monthly_analytics: '月度收支分析',
  transaction_anomalies: '异常规则检测',
  get_balance: '账户余额',
  get_transactions: '交易流水',
  list_subscriptions: '订阅代扣列表',
}
</script>

<template>
  <section class="skill-report" aria-label="Agent Skill 执行结果">

    <!-- 技能标题 -->
    <header>
      <strong>{{ data.title || 'Agent Skill' }}</strong>
      <span>Skills · MCP 只读</span>
    </header>

    <!-- 技能摘要 -->
    <p v-if="valid" class="summary">
      {{ data.summary }}
    </p>

    <p v-else class="warning">
      技能结果尚未确认；请重新检查任务执行状态。
    </p>

    <!-- 技能执行步骤 -->
    <div v-if="valid" class="steps">
      <article
          v-for="(row, index) in rows"
          :key="row.taskType + index"
      >
        <span>
          {{ index + 1 }}.
          {{ names[row.taskType] || '已注册查询' }}
        </span>

        <span
            :class="row.status === 'SUCCESS' ? 'ok' : 'bad'"
        >
          {{ row.status === 'SUCCESS' ? '成功' : '未确认' }}
        </span>
      </article>
    </div>

    <!-- D11 新增：月度财务体检详细报告 -->
    <div
        v-if="
        valid &&
        data.skillId === 'skill_monthly_finance_review' &&
        data.results
      "
        class="skill-details"
    >

      <!-- 复用月度收支分析组件 -->
      <MonthlyAnalyticsCard
          v-if="data.results.monthly_analytics"
          :data="data.results.monthly_analytics"
      />

      <!-- 复用异常交易检测组件 -->
      <TransactionAnomalyCard
          v-if="data.results.transaction_anomalies"
          :data="data.results.transaction_anomalies"
      />

    </div>

    <!-- 风险说明 -->
    <p v-if="valid" class="note">
      以上结论来源于当前登录用户的 Java 模拟银行只读接口。
      规则命中不是确认盗刷；
      本次没有创建、授权、执行或取消银行订单。
    </p>

  </section>
</template>

<style scoped>
.skill-report {
  width: min(780px, 100%);
  box-sizing: border-box;
  border: 1px solid #dce4ed;
  border-radius: 12px;
  background: #fff;
  padding: 15px;
  font-size: 13px;
  color: #172b46;
}

header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid #edf1f5;
  padding-bottom: 11px;
}

header span,
.note {
  font-size: 12px;
  color: #687b91;
}

.summary {
  line-height: 1.8;
  white-space: pre-wrap;
}

.warning,
.bad {
  color: #b36627;
}

.steps {
  display: grid;
  gap: 7px;
  margin: 14px 0;
}

.steps article {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  background: #f7f9fc;
  border-radius: 7px;
  padding: 9px 11px;
}

.ok {
  color: #23795e;
}

/* D11 新增：详细报告布局 */
.skill-details {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
  margin-top: 14px;
}

.note {
  margin-top: 12px;
  line-height: 1.6;
}
</style>
