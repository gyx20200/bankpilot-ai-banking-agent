
<script setup>
import { computed } from 'vue'

const props = defineProps({
  report: {
    type: Object,
    required: true
  },
  reportValid: {
    type: Boolean,
    required: true
  }
})

// 当前三个已注册 Skill 的固定步骤数量
const expectedStepCounts = Object.freeze({
  skill_monthly_finance_review: 2,
  skill_account_snapshot: 2,
  skill_subscription_review: 2
})

// 执行步骤中文名称
const stepNames = Object.freeze({
  monthly_analytics: '月度收支分析',
  transaction_anomalies: '异常规则检测',
  get_balance: '账户余额',
  get_transactions: '交易流水',
  list_subscriptions: '订阅代扣列表'
})

// 安全获取执行步骤
const steps = computed(() => {
  return Array.isArray(props.report?.steps)
      ? props.report.steps
      : []
})

// 当前 Skill 应执行的步骤数量
const expectedStepCount = computed(() => {
  return expectedStepCounts[props.report?.skillId] ?? 0
})

// 实际成功执行的步骤数量
const successfulStepCount = computed(() => {
  return steps.value.filter(
      step => step?.status === 'SUCCESS'
  ).length
})

// D12：证据面板完整性检查
// 父组件已经负责步骤名称、顺序以及结果字段检查
// 此处必须遵循父组件的报告校验结果
const verified = computed(() => {
  const report = props.report

  return (
      props.reportValid === true &&
      report?.status === 'COMPLETED' &&
      report?.readOnly === true &&
      report?.dataOrigin === 'JAVA_MYSQL_VIA_MCP' &&
      expectedStepCount.value > 0 &&
      steps.value.length === expectedStepCount.value &&
      steps.value.every(
          step =>
              step?.status === 'SUCCESS' &&
              typeof step.taskType === 'string' &&
              step.taskType.length > 0
      ) &&
      new Set(
          steps.value.map(step => step.taskType)
      ).size === expectedStepCount.value
  )
})

// 执行状态展示文案
const statusText = computed(() => {
  return verified.value
      ? '只读查询执行完成'
      : '执行证据不完整'
})
</script>

<template>
  <section
      class="skill-evidence"
      aria-label="Skill 执行证据"
  >

    <!-- 执行证据标题及状态 -->
    <div class="evidence-header">
      <strong>执行证据</strong>

      <span
          class="status-tag"
          :class="verified ? 'success' : 'failed'"
      >
        {{ statusText }}
      </span>
    </div>

    <!-- 执行元数据 -->
    <div class="evidence-meta">

      <!-- 执行模式 -->
      <div class="meta-row">
        <span>执行模式</span>

        <strong>
          {{ report.readOnly === true ? '只读' : '未确认' }}
        </strong>
      </div>

      <!-- 执行步骤统计 -->
      <div class="meta-row">
        <span>执行步骤</span>

        <strong>
          {{ successfulStepCount }}/{{ expectedStepCount }}
        </strong>
      </div>

      <!-- 数据来源：仅核验通过时显示 -->
      <div v-if="verified" class="meta-row">
        <span>数据来源</span>

        <strong>Java / MySQL via MCP</strong>
      </div>

    </div>

    <!-- 可折叠的 MCP 执行步骤 -->
    <details
        v-if="steps.length > 0"
        class="step-details"
    >

      <summary>
        查看 MCP 执行步骤
      </summary>

      <div
          v-for="(step, index) in steps"
          :key="`${step?.taskType}-${index}`"
          class="step-item"
      >

        <!-- 步骤执行状态图标 -->
        <span
            :class="[
              'step-icon',
              step?.status === 'SUCCESS' ? 'ok' : 'error'
            ]"
        >
          {{ step?.status === 'SUCCESS' ? '✓' : '!' }}
        </span>

        <!-- 步骤详细信息 -->
        <div class="step-info">

          <!-- 中文业务名称 -->
          <strong>
            {{ stepNames[step?.taskType] || '未知查询步骤' }}
          </strong>

          <!-- Task Type -->
          <small>
            Task: {{ step?.taskType || 'UNKNOWN' }}
          </small>

          <!-- MCP Tool -->
          <small>
            MCP: {{ step?.mcpTool || '未提供工具名称' }}
          </small>

        </div>

        <!-- 步骤状态 -->
        <span
            class="step-status"
            :class="
              step?.status === 'SUCCESS'
                ? 'status-ok'
                : 'status-error'
            "
        >
          {{ step?.status || 'UNKNOWN' }}
        </span>

      </div>

    </details>

    <!-- 未获取执行步骤 -->
    <p
        v-if="steps.length === 0"
        class="warning-note"
    >
      未获取到可展示的 Skill 执行步骤。
    </p>

    <!-- 成功说明 -->
    <p v-if="verified" class="evidence-note">
      本次 Skill 通过受控 MCP 获取银行数据，
      未执行资金写入操作。
    </p>

    <!-- 失败说明 -->
    <p v-else class="warning-note" role="alert">
      当前执行结果未满足完整性要求，
      不应将其视为已完成的银行数据报告。
    </p>

  </section>
</template>

<style scoped>
.skill-evidence {
  margin-top: 12px;
  padding: 14px 16px;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: #f8fafc;
  font-size: 13px;
  color: #334155;
}

/* 标题区域 */
.evidence-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.evidence-header > strong {
  font-size: 13px;
  font-weight: 600;
}

/* 执行状态标签 */
.status-tag {
  padding: 4px 9px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
}

.status-tag.success {
  background: #dcfce7;
  color: #166534;
}

.status-tag.failed {
  background: #fee2e2;
  color: #991b1b;
}

/* 执行元数据 */
.evidence-meta {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.meta-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.meta-row > span {
  color: #64748b;
}

.meta-row > strong {
  font-size: 12px;
  text-align: right;
  overflow-wrap: anywhere;
}

/* MCP 执行步骤 */
.step-details {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #e2e8f0;
}

.step-details summary {
  cursor: pointer;
  color: #475569;
  font-size: 12px;
  user-select: none;
}

.step-details summary:hover {
  color: #2563eb;
}

.step-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 0;
}

.step-item + .step-item {
  border-top: 1px solid #e9eef4;
}

/* 步骤状态图标 */
.step-icon {
  width: 22px;
  height: 22px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  font-size: 12px;
  font-weight: 600;
}

.step-icon.ok {
  color: #15803d;
  background: #dcfce7;
}

.step-icon.error {
  color: #b91c1c;
  background: #fee2e2;
}

/* 步骤信息 */
.step-info {
  display: flex;
  flex: 1;
  min-width: 0;
  flex-direction: column;
  gap: 3px;
  overflow-wrap: anywhere;
}

.step-info > strong {
  font-size: 12px;
  color: #334155;
}

.step-info small {
  color: #64748b;
  font-size: 11px;
  line-height: 1.5;
}

/* 步骤状态 */
.step-status {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 500;
}

.status-ok {
  color: #15803d;
}

.status-error {
  color: #b91c1c;
}

/* 执行说明 */
.evidence-note {
  margin: 12px 0 0;
  color: #64748b;
  font-size: 12px;
  line-height: 1.6;
}

.warning-note {
  margin: 12px 0 0;
  color: #b91c1c;
  font-size: 12px;
  line-height: 1.6;
}
</style>
