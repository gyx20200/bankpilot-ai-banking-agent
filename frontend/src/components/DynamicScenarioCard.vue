<script setup>
import {computed} from 'vue'
import MonthlyAnalyticsCard from './MonthlyAnalyticsCard.vue'
const props = defineProps({task:{type:Object,required:true},busy:{type:Boolean,default:false}})
const emit = defineEmits(['decision'])
const waiting = computed(()=>props.task.status==='WAITING_APPROVAL')
const amount = v => new Intl.NumberFormat('zh-CN',{style:'currency',currency:'CNY'}).format(Number(v||0))
const names = {ANALYZED:'查询完成',WAITING_APPROVAL:'等待用户确认',SUCCESS:'银行确认取消成功',DECLINED:'用户拒绝',NEEDS_CLARIFICATION:'需要补充信息',NOT_CONFIRMED:'银行状态未确认'}
const stepName = s => ({SUCCESS:'已完成',WAITING_APPROVAL:'待确认',ANALYZED:'查询完成',DECLINED:'已拒绝',PENDING:'待执行',NEEDS_CLARIFICATION:'待补充',NOT_CONFIRMED:'未确认'})[s] || s
</script>
<template>
 <section class="panel dynamic-panel">
  <div class="heading"><strong>Day 6 · 多任务工作流</strong><span class="state">{{names[task.status]||task.status}}</span></div>
  <p class="meta">任务 {{task.threadId}} · {{task.planningSource==='llm'?'DeepSeek 任务规划':'规则模式任务规划'}} · {{task.mock?'Mock 演示银行':'Java 银行接口'}}</p>
  <div class="task-list">
   <div v-for="(item,i) in task.tasks||[]" :key="item.type" class="task-row">
    <div><b>{{i+1}}. {{item.label}}</b><small v-if="item.month">{{item.month}}</small><small v-if="item.targetName">{{item.targetName}}</small></div>
    <span class="state">{{stepName(item.status)}}</span>
   </div>
  </div>
  <MonthlyAnalyticsCard v-if="task.monthlyAnalytics" :data="task.monthlyAnalytics" />
  <div v-if="(task.tasks||[]).some(t=>t.type==='list_subscriptions')" class="result">
   <strong>银行代扣协议</strong>
   <p v-if="!task.subscriptions?.length">没有查到订阅协议。</p>
   <div v-for="s in task.subscriptions||[]" :key="s.id" class="task-row">
    <div><b>{{s.merchantName}}</b><small>{{s.status}}</small></div>
    <span>{{amount(s.amount)}}</span>
   </div>
  </div>
  <div v-if="task.cancellationOrder" class="result">
   <strong>取消申请：{{task.candidate?.merchantName}}</strong>
   <p>申请编号：{{task.cancellationOrder.orderId}}</p>
   <p>银行申请状态：{{task.cancellationOrder.status}}</p>
   <p>订阅金额：{{amount(task.candidate?.amount)}} / {{task.candidate?.billingCycle||'周期'}}</p>
   <p>风险等级：{{task.cancellationOrder.riskLevel||'由银行判断'}}</p>
  </div>
  <div v-if="waiting && task.cancellationOrder" class="approval">
   <p><strong>请确认是否取消这项模拟银行代扣。</strong> 拒绝后不会执行取消；批准后仍需银行校验并返回实际状态。</p>
   <div class="buttons">
    <button class="primary" type="button" :disabled="busy" @click="emit('decision',{threadId:task.threadId,approved:true})">批准取消</button>
    <button class="secondary" type="button" :disabled="busy" @click="emit('decision',{threadId:task.threadId,approved:false})">拒绝，保留代扣</button>
   </div>
  </div>
  <p v-if="task.details" class="notice">{{task.details}}</p>
  <p class="meta">结果以模拟银行 / Java 后端为准。模型只负责识别任务，不负责授权或修改银行状态。</p>
 </section>
</template>
<style scoped>
.dynamic-panel{display:flex;flex-direction:column;gap:12px;max-width:650px;width:100%;box-sizing:border-box}
.heading,.task-row{display:flex;justify-content:space-between;gap:12px;align-items:center}
.state{font-size:12px;background:#e8f1fa;color:#235785;padding:4px 9px;border-radius:8px;white-space:nowrap}
.meta{font-size:11px;color:#7890ac;overflow-wrap:anywhere;margin:0}
.task-list,.result{border:1px solid #dce6f3;border-radius:10px;padding:12px;display:flex;flex-direction:column;gap:9px}
.task-row{border-bottom:1px solid #eef2f8;padding:5px 0}
.task-row:last-child{border-bottom:0}.task-row div{display:flex;flex-direction:column;gap:2px}
.task-row small{color:#72859d}.result p{margin:1px 0;color:#536a82;font-size:13px}
.approval{padding:12px;background:#fff6dd;border-radius:10px;color:#6d4d16}
.approval p{margin:0 0 9px;font-size:13px}.buttons{display:flex;gap:8px;flex-wrap:wrap}
.buttons button{padding:8px 14px;border-radius:8px;cursor:pointer}
.buttons button:disabled{opacity:.5;cursor:not-allowed}.buttons .primary{background:#367ecb;color:white;border:0}
.buttons .secondary{background:white;border:1px solid #adc0d6;color:#285071}
.notice{padding:9px;border-radius:8px;background:#f2f6fc;color:#29425b;margin:0}
</style>
