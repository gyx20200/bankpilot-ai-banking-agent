<script setup>
import {ref} from 'vue'
const props=defineProps({payees:{type:Array,default:()=>[]},payeeName:{type:String,default:''},amount:{type:String,default:''},requestId:{type:String,required:true},busy:{type:Boolean,default:false},completed:{type:Boolean,default:false}})
const emit=defineEmits(['prepare'])
const matches=props.payees.filter(p=>p.payeeName===props.payeeName)
const payeeId=ref(matches.length===1?String(matches[0].id):'')
const amount=ref(props.amount||'')
const remark=ref('')
const error=ref('')
function submit(){
  error.value=''
  if(!props.payees.some(p=>String(p.id)===payeeId.value)){error.value='请选择有效收款人';return}
  if(!/^(?:0|[1-9]\d{0,8})(?:\.\d{1,2})?$/.test(amount.value)||Number(amount.value)<=0||Number(amount.value)>1_000_000){error.value='金额格式不正确';return}
  if(props.completed)return
  emit('prepare',{payeeId:Number(payeeId.value),amount:amount.value,remark:remark.value,requestId:props.requestId})
}
</script>
<template>
 <section class="panel form-panel">
  <h4>补全转账草稿</h4>
  <form @submit.prevent="submit">
   <label>选择收款人<select v-model="payeeId" :disabled="busy||completed" required><option value="">请选择</option><option v-for="p in payees" :key="p.id" :value="String(p.id)">{{p.payeeName}} · {{p.payeeAccountMasked}}</option></select></label>
   <label>转账金额<input v-model="amount" :disabled="busy||completed" inputmode="decimal" placeholder="200.00" required/></label>
   <label>备注<input v-model="remark" :disabled="busy||completed" maxlength="80" placeholder="可选"/></label>
   <p v-if="error" class="error">{{error}}</p>
   <button type="submit" class="primary" :disabled="busy||completed||!payees.length">{{completed?'已建单':busy?'处理中…':'创建待确认订单'}}</button>
  </form>
  <small>此步骤不扣款，提交后还需用户明确授权。</small>
 </section>
</template>
