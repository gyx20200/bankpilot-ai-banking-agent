<script setup>
import {computed} from 'vue'
const props = defineProps({task:{type:Object,required:true},busy:{type:Boolean,default:false}})
const emit = defineEmits(['decision'])
const money=v=>new Intl.NumberFormat('zh-CN',{style:'currency',currency:'CNY'}).format(Number(v))
const waiting = computed(()=>props.task.status==='WAITING_APPROVAL')
const statuses={ANALYZED:'分析完成（只读）',WAITING_APPROVAL:'等待用户确认',DECLINED:'用户拒绝，未取消',CANCELLED:'银行确认代扣已取消',NOT_CONFIRMED:'取消结果未确认',NOT_EXECUTED:'未执行'}
</script>
<template>
 <section class="panel cross-panel">
  <h4>跨场景任务 · {{statuses[task.status]||task.status}}</h4>
  <div class="workflow-steps">
   <span v-for="step in task.steps" :key="step">✓ {{step}}</span>
  </div>
  <div v-if="task.report" class="cross-report">
   <p>统计区间：{{task.report.period}}</p>
   <div class="cross-total">近 30 天支出：{{money(task.report.totalExpense)}}</div>
   <p>支出交易 {{task.report.transactionCount}} 笔</p>
   <div v-for="cat in task.report.categories" :key="cat.name" class="cross-row"><span>{{cat.name}}</span><strong>{{money(cat.amount)}}</strong></div>
  </div>
  <h4>当前银行代扣协议</h4>
  <div v-for="s in task.subscriptions" :key="s.id" class="cross-row"><span>{{s.merchantName}}（{{s.status}}）</span><strong>{{money(s.amount)}}</strong></div>
  <div v-if="waiting && task.candidate" class="cross-approval">
   <strong>申请取消：{{task.candidate.merchantName}}</strong>
   <p>确认后仍需 Java 银行后端检查本人身份与代扣协议状态。无法确认成功时将显示“未确认”，不会假装已取消。</p>
   <div class="actions"><button class="primary" :disabled="busy" @click="emit('decision',{threadId:task.threadId,approved:true})">确认申请取消</button><button class="secondary" :disabled="busy" @click="emit('decision',{threadId:task.threadId,approved:false})">保留代扣</button></div>
  </div>
  <p v-if="task.details" class="workflow-note">{{task.details}}</p>
  <small>所有金额来自银行流水并通过 Decimal 计算，不由大模型生成。</small>
 </section>
</template>
