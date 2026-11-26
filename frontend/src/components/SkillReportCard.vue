
<script setup>
import { computed } from 'vue'
import MonthlyAnalyticsCard from './MonthlyAnalyticsCard.vue'
import TransactionAnomalyCard from './TransactionAnomalyCard.vue'
import SkillEvidencePanel from './SkillEvidencePanel.vue'

const props = defineProps({
  data: {
    type: Object,
    required: true
  }
})

// D12：三个已注册 Skill 的固定执行步骤及顺序
const expectedSteps = Object.freeze({
  skill_monthly_finance_review: [
    'monthly_analytics',
    'transaction_anomalies'
  ],
  skill_account_snapshot: [
    'get_balance',
    'get_transactions'
  ],
  skill_subscription_review: [
    'list_subscriptions',
    'get_transactions'
  ]
})

// D12：报告完整性检查
const valid = computed(() => {
  const report = props.data

  const expected = expectedSteps[report?.skillId]

  const steps = Array.isArray(report?.steps)
      ? report.steps
      : []

  return (
      report?.readOnly === true &&
      report?.status === 'COMPLETED' &&
      report?.dataOrigin === 'JAVA_MYSQL_VIA_MCP' &&
      Array.isArray(expected) &&
      steps.length === expected.length &&
      steps.every(
          (step, index) =>
              step?.status === 'SUCCESS' &&
              step?.taskType === expected[index]
      ) &&
      typeof report?.summary === 'string' &&
      report.summary.trim().length > 0 &&
      expected.every(
          taskType =>
              Object.prototype.hasOwnProperty.call(
                  report?.results ?? {},
                  taskType
              ) &&
              report.results[taskType] != null
      )
  )
})
</script>

<template>
  <section
      class="skill-report"
      aria-label="Agent Skill 执行结果"
  >

    <!-- 技能标题 -->
    <header>
      <strong>
        {{ data.title || 'Agent Skill' }}
      </strong>

      <span>
        {{ valid ? 'Skills · MCP 只读' : 'Skills · 未确认' }}
      </span>
    </header>

    <!-- 技能摘要 -->
    <p v-if="valid" class="summary">
      {{ data.summary }}
    </p>

    <!-- 未通过完整性检查 -->
    <p v-else class="warning" role="alert">
      技能结果尚未通过完整性核验；
      请重新检查任务执行状态。
    </p>

    <!-- D11：月度财务体检详细报告 -->
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

    <!-- D12：统一 Skill 执行证据 -->
    <SkillEvidencePanel
        :report="data"
        :report-valid="valid"
    />

    <!-- 风险说明 -->
    <p v-if="valid" class="note">
      以上结论来源于当前登录用户的 Java 模拟银行只读接口。

      <template v-if="data.skillId === 'skill_monthly_finance_review'">
        规则命中不是确认盗刷；
      </template>

      本次 Skill 没有创建、授权、执行或取消银行订单。
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
  align-items: center;
  flex-wrap: wrap;
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

.warning {
  color: #b36627;
  line-height: 1.6;
}

/* D11：详细报告布局 */
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
