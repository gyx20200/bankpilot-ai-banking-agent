<script setup>
import {ref,watch} from 'vue'
const props=defineProps({order:{type:Object,required:true},busy:{type:Boolean,default:false}})
const emit=defineEmits(['authorize','execute','cancel','refresh','otpRequest'])
const confirmed=ref(false)
const otp=ref('')
const error=ref('')
watch(()=>props.order.status,()=>{otp.value='';error.value='';confirmed.value=false})
function approve(){
  error.value=''
  if(!confirmed.value){error.value='请先确认收款人、金额和账户信息';return}
  if(props.order.riskLevel==='RED'&&!/^\d{6}$/.test(otp.value)){error.value='请输入6位模拟验证码';return}
  emit('authorize',{orderId:props.order.orderId,otpCode:props.order.riskLevel==='RED'?otp.value:null,confirmation:true})
  otp.value=''
}
const labels={PENDING_APPROVAL:'待确认',AUTHORIZED:'已授权，待执行',SUCCESS:'模拟转账成功',CANCELLED:'已取消',FAILED:'失败',LOCKED:'验证锁定',UNKNOWN:'待核验'}
const statusLabel=v=>labels[v]||v
const money=v=>new Intl.NumberFormat('zh-CN',{style:'currency',currency:'CNY'}).format(Number(v))
</script>
<template>
  <section class="panel order-panel">
   <div class="order-head"><strong>模拟转账订单</strong><span class="risk" :class="order.riskLevel==='RED'?'red':'yellow'">{{order.riskLevel==='RED'?'红色 · 强验证':'黄色 · 明确确认'}}</span></div>
   <div class="sum">{{money(order.amount)}}</div>
   <dl>
    <div><dt>收款人</dt><dd>{{order.payeeName}}</dd></div>
    <div><dt>收款账号</dt><dd>{{order.accountMasked}}</dd></div>
    <div><dt>订单编号</dt><dd>{{order.orderId}}</dd></div>
    <div><dt>当前状态</dt><dd class="state">{{statusLabel(order.status)}}</dd></div>
    <div v-if="order.transferId"><dt>交易流水号</dt><dd>{{order.transferId}}</dd></div>
    <div v-if="order.balanceAfter"><dt>模拟转出后余额</dt><dd>{{money(order.balanceAfter)}}</dd></div>
   </dl>
   <div v-if="order.status==='PENDING_APPROVAL'" class="approval">
     <label class="check"><input type="checkbox" v-model="confirmed" :disabled="busy"/> 我已核对收款人、账号和金额，确认授权这笔模拟转账</label>
     <div v-if="order.riskLevel==='RED'" class="otp-help"><button class="secondary" :disabled="busy" @click="emit('otpRequest',order.orderId)">向银行申请模拟验证码</button><small>Java 后端负责生成与校验。验证码不由模型生成。</small></div>
     <label v-if="order.riskLevel==='RED'" class="otp-label">模拟 OTP 验证码<input v-model="otp" type="password" inputmode="numeric" maxlength="6" autocomplete="one-time-code" placeholder="请输入 6 位验证码" :disabled="busy"/></label>
     <p v-if="error" class="error">{{error}}</p>
     <div class="actions"><button class="primary" :disabled="busy||!confirmed" @click="approve">{{busy?'处理中…':order.riskLevel==='RED'?'强验证并授权':'确认并授权'}}</button><button class="secondary" :disabled="busy" @click="emit('cancel',order.orderId)">取消订单</button></div>
   </div>
   <div v-else-if="order.status==='AUTHORIZED'" class="approval">
     <p>银行后端已经确认授权，资金尚未转移。请点击执行以提交模拟银行事务。</p>
     <div class="actions"><button class="primary" :disabled="busy" @click="emit('execute',order.orderId)">{{busy?'处理中…':'执行模拟转账'}}</button><button class="secondary" :disabled="busy" @click="emit('cancel',order.orderId)">取消订单</button></div>
   </div>
   <div v-else-if="order.status==='SUCCESS'" class="success">✓ 银行模拟交易已返回成功，请勿再次发起同一笔转账。</div>
   <div v-else class="muted">最终结果以银行后端的订单查询为准。</div>
   <button class="refresh" :disabled="busy" @click="emit('refresh',order.orderId)">↻ 刷新订单状态</button>
  </section>
</template>
