<script setup>
import { ref, watch } from 'vue'
const props=defineProps({token:{type:String,default:''}})
const base='/api/agent/cards'
const items=ref([]), applications=ref([]), prompt=ref('申请一张虚拟模拟银行卡')
const flow=ref(null), busy=ref(false), error=ref(''), notice=ref(''), stableRequestId=ref('')
const restrictions=ref({})
const intendedOffline=ref({})
function key(){return crypto.randomUUID().replaceAll('-','')}
async function call(path,method='GET',payload) {
  if(!props.token) throw new Error('请先登录')
  const res=await fetch(base+path,{method,headers:{Authorization:`Bearer ${props.token}`,
    'Content-Type':'application/json'},body:payload===undefined?undefined:JSON.stringify(payload)})
  const value=await res.json().catch(()=>({}))
  if(!res.ok) throw new Error(`银行返回 HTTP ${res.status}。如已建单，请查询原申请，不得盲目重新申请。`)
  return value
}
async function refresh(){
  if(!props.token)return
  busy.value=true;error.value=''
  try{
    const [cards,apps]=await Promise.all([call(''),call('/applications')])
    items.value=cards; applications.value=apps
    const next={};const nextOnline={}
    for(const c of cards){
      next[c.cardId]=String(c.singleTransactionLimit)
      nextOnline[c.cardId]=false
    }
    restrictions.value=next;intendedOffline.value=nextOnline
  }catch(e){error.value=e.message}finally{busy.value=false}
}
async function start(){
  if(busy.value||flow.value?.status==='WAITING_CARD_APPROVAL')return
  busy.value=true;error.value='';notice.value=''
  if(!stableRequestId.value)stableRequestId.value=key()
  try{
    flow.value=await call('/start','POST',{message:prompt.value,requestId:stableRequestId.value})
    if(flow.value.status!=='WAITING_CARD_APPROVAL')stableRequestId.value=''
  }catch(e){error.value=e.message+' 原请求编号已保留；先刷新并核对原申请。'}
  finally{busy.value=false}
}
async function decide(approved){
  if(busy.value||flow.value?.status!=='WAITING_CARD_APPROVAL')return
  busy.value=true;error.value=''
  try{
    flow.value=await call('/resume','POST',{threadId:flow.value.threadId,approved})
    stableRequestId.value='';await loadAfterAction()
  }catch(e){error.value=e.message}
  finally{busy.value=false}
}
async function cancelPending(application){
  if(busy.value || application.status!=='PENDING_APPROVAL')return
  if(!window.confirm(`确认取消原申请 #${application.applicationId}？`))return
  busy.value=true;error.value=''
  try{
    await call(`/applications/${application.applicationId}/cancel`,'POST')
    notice.value='Java 已确认取消原待审批申请。'
    flow.value=null;stableRequestId.value=''
    await loadAfterAction()
  }catch(e){error.value=e.message+' 请核对原申请状态。'}finally{busy.value=false}
}
async function loadAfterAction(){
  const [cards,apps]=await Promise.all([call(''),call('/applications')])
  items.value=cards;applications.value=apps
  for(const c of cards){restrictions.value[c.cardId]=String(c.singleTransactionLimit)}
}
async function narrow(card){
  if(busy.value)return
  const next=String(restrictions.value[card.cardId]).trim()
  if(!/^\d{1,6}(\.\d{1,2})?$/.test(next)||Number(next)<=0||Number(next)>Number(card.singleTransactionLimit)){
    error.value='D14 仅允许收紧单笔模拟限制，不允许增加额度。';return
  }
  const disableOnline=intendedOffline.value[card.cardId]===true
  if(!disableOnline && Number(next)===Number(card.singleTransactionLimit))return
  if(!window.confirm(`确认收紧 ${card.cardAlias} 限制为 ¥${next}${disableOnline?'，并关闭线上使用标志':''}？此操作不会影响真实支付或转账。`))return
  busy.value=true;error.value=''
  try{
    await call(`/${card.cardId}/restrictions`,'POST',{
      singleTransactionLimit:next,disableOnline,requestId:key()})
    notice.value='已由 Java 保存限制配置；它不代表真实支付能力。'
    await loadAfterAction()
    intendedOffline.value[card.cardId]=false
  }catch(e){error.value=e.message+' 如网络异常请先刷新配置再决定。'}
  finally{busy.value=false}
}
function clear(){
  if(flow.value?.status==='WAITING_CARD_APPROVAL')return
  flow.value=null;stableRequestId.value='';error.value='';notice.value=''
}
watch(()=>props.token,()=>{
  items.value=[];applications.value=[];flow.value=null;stableRequestId.value='';error.value='';notice.value=''
  if(props.token)refresh()
},{immediate:true})
</script>

<template>
  <section class="bp-cards" aria-label="D14 模拟卡片中心">
    <h3>卡片中心（D14 · 仅模拟）</h3>
    <p>仅模拟虚拟借记卡的申请和限制元数据；不生成真实卡号、CVV，不支持支付、授信或转账额度调整。</p>
    <button type="button" :disabled="busy||!token" @click="refresh">刷新卡片及申请</button>
    <p v-if="error" role="alert">{{error}}</p>
    <p v-if="notice">{{notice}}</p>
    <h4>本人模拟卡片</h4>
    <p v-if="!items.length">暂无模拟卡片</p>
    <article v-for="c in items" :key="c.cardId" class="bp-card">
      <strong>{{c.cardAlias}} · {{c.status}}</strong>
      <p>类型：模拟虚拟借记卡；演示每日参考上限：¥{{c.dailyCeiling}}；当前单笔配置：¥{{c.singleTransactionLimit}}</p>
      <p>线上标志：{{c.onlineEnabled?'未关闭':'已关闭'}}（仅存储配置，无支付通道）</p>
      <label>降低单笔配置 <input v-model="restrictions[c.cardId]" inputmode="decimal" :disabled="busy" /></label>
      <label><input type="checkbox" v-model="intendedOffline[c.cardId]" :disabled="busy||!c.onlineEnabled" />关闭线上使用标志</label>
      <button type="button" :disabled="busy||c.status!=='ACTIVE'" @click="narrow(c)">确认保存限制</button>
    </article>
    <h4>自然语言申请（独立审批工作流）</h4>
    <textarea v-model="prompt" rows="2" :disabled="busy||flow?.status==='WAITING_CARD_APPROVAL'" />
    <div>
      <button type="button" :disabled="busy||!token||flow?.status==='WAITING_CARD_APPROVAL'" @click="start">分析 / 创建待确认申请</button>
      <button type="button" :disabled="busy||flow?.status==='WAITING_CARD_APPROVAL'" @click="clear">新请求</button>
    </div>
    <p v-if="flow">状态：{{flow.status}}；{{flow.details}}</p>
    <div v-if="flow?.status==='WAITING_CARD_APPROVAL'">
      <strong>待确认申请 #{{flow.application?.applicationId}}</strong>
      <p>只创建一张模拟虚拟卡，不扣款。请本人核对后审批。</p>
      <button type="button" :disabled="busy" @click="decide(true)">我确认申请</button>
      <button type="button" :disabled="busy" @click="decide(false)">拒绝申请</button>
    </div>
    <pre v-if="flow?.result">{{JSON.stringify(flow.result,null,2)}}</pre>
    <h4>最近申请（由 Java 返回）</h4>
    <div v-for="a in applications" :key="a.applicationId">
      #{{a.applicationId}} · {{a.cardType}} · {{a.status}}
      <button v-if="a.status==='PENDING_APPROVAL'" type="button" :disabled="busy" @click="cancelPending(a)">取消原待审批申请</button>
    </div>
  </section>
</template>
<style scoped>
.bp-cards{border:1px solid #d6dce4;border-radius:12px;padding:16px;margin:12px 0;display:grid;gap:8px}
.bp-cards button{margin-right:8px;padding:6px 10px}
.bp-cards textarea{width:100%;font:inherit}
.bp-card{border:1px solid #e5e7eb;border-radius:8px;padding:12px;display:grid;gap:6px}
.bp-card p{margin:4px 0}
.bp-card label{display:flex;align-items:center;gap:8px}
</style>
