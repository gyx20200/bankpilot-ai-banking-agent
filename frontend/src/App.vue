<script setup>
import {ref,nextTick,onMounted} from 'vue'
import TransferForm from './components/TransferForm.vue'
import TransferOrderCard from './components/TransferOrderCard.vue'
import CrossScenarioCard from './components/CrossScenarioCard.vue'
const messages=ref([{id:'welcome',role:'assistant',reply:'你好，我是 BankPilot。本地模拟银行支持账户查询和带审批的模拟转账。',intent:'welcome'}])
const input=ref('')
const token=ref('')  // Developer demo only; in-memory, never localStorage
const loginPassword=ref('')
const loginMessage=ref('')
const mode=ref('java')
const routerMode=ref('rules')
const modelConfigured=ref(false)
const modelName=ref('')
const connected=ref(false)
const busy=ref(false)
const completedForms=ref([])
const workflowText=ref('分析最近30天消费，查一下订阅，并取消视频会员代扣')
const lastRef=ref(null)
const queries=['查询余额','最近交易','常用收款人','订阅代扣','给李四转200元','给李四转1500元','给李四转']
const toSay={'查询余额':'我的余额是多少','最近交易':'查询最近交易','常用收款人':'我的常用收款人','订阅代扣':'有哪些自动扣费'}
async function scroll(){await nextTick();lastRef.value?.scrollIntoView({behavior:'smooth',block:'end'})}
function headers(){const h={'Content-Type':'application/json'};if(token.value.trim())h.Authorization=`Bearer ${token.value.trim()}`;return h}
async function req(url,method='GET',body){const options={method,headers:headers(),signal:AbortSignal.timeout(14000)};if(body)options.body=JSON.stringify(body);const r=await fetch(url,options);const data=await r.json().catch(()=>({}));if(!r.ok)throw Error(data.detail||`HTTP ${r.status}`);return data}
function addMessage(obj){messages.value.push({id:crypto.randomUUID(),role:'assistant',...obj})}
function errorMessage(e){addMessage({intent:'error',reply:`处理异常：${e.message}。请通过“刷新订单状态”检查是否已执行，勿盲目重复提交。`})}
function replaceOrder(newData){
 const id=String(newData.orderId)
 for(const m of messages.value){if(m.intent==='transfer'&&m.data?.orderId&&String(m.data.orderId)===id){m.data={...newData};m.action='status'}}
}
async function checkHealth(){try{const x=await req('/api/agent/health');mode.value=x.bankMode==='mock'?'mock':'java';routerMode.value=x.mode==='llm-day5'?'llm':'rules';modelConfigured.value=!!x.modelConfigured;modelName.value=x.modelName||'';connected.value=true}catch{connected.value=false}}
async function send(text){const s=String(text||input.value).trim();if(!s||busy.value)return;input.value='';busy.value=true;messages.value.push({id:crypto.randomUUID(),role:'user',reply:s});await scroll();try{addMessage(await req('/api/agent/chat','POST',{message:toSay[s]||s,requestId:crypto.randomUUID()}))}catch(e){errorMessage(e)}finally{busy.value=false;await scroll()}}
async function prepare(form){if(busy.value||completedForms.value.includes(form.requestId))return;busy.value=true;try{const data=await req('/api/agent/transfers/prepare','POST',form);completedForms.value.push(form.requestId);addMessage(data)}catch(e){errorMessage(e)}finally{busy.value=false;await scroll()}}
async function doAction(action,orderId,payload={}){
 if(busy.value)return
 busy.value=true
 try{const r=await req(`/api/agent/transfers/${encodeURIComponent(String(orderId))}/${action}`,'POST',{requestId:crypto.randomUUID(),...payload});replaceOrder(r.data);addMessage({reply:r.reply,intent:'event',action:r.action})}catch(e){errorMessage(e)}finally{busy.value=false;await scroll()}
}
async function demoLogin(){
 if(busy.value || !loginPassword.value)return
 busy.value=true; loginMessage.value=''
 try {
  const data=await req('/api/agent/auth/demo-login','POST',{password:loginPassword.value})
  token.value=data.token
  loginMessage.value=`已登录：${data.displayName||'模拟用户'}`
 }catch(e){loginMessage.value=`登录失败：${e.message}`}
 finally{loginPassword.value='';busy.value=false}
}
async function requestOtp(orderId){
 if(busy.value)return
 busy.value=true
 try{
  const data=await req(`/api/agent/transfers/${encodeURIComponent(String(orderId))}/otp/request`,'POST')
  addMessage({intent:'event',reply:`模拟验证码申请已受理，有效期 ${data.expiresInSeconds??120} 秒。请从银行演示验证渠道获取验证码。`})
 }catch(e){errorMessage(e)}finally{busy.value=false;await scroll()}
}
async function startWorkflow(){
 if(busy.value)return
 busy.value=true
 try {
  const res=await req('/api/agent/workflows/start','POST',{message:workflowText.value})
  messages.value.push({id:crypto.randomUUID(),role:'assistant',intent:'workflow',reply:'跨场景查询已完成，请核对报告和授权候选。',data:res})
 }catch(e){errorMessage(e)}finally{busy.value=false;await scroll()}
}
async function decideWorkflow({threadId,approved}){
 if(busy.value)return
 busy.value=true
 try {
  const res=await req('/api/agent/workflows/resume','POST',{threadId,approved})
  const item=messages.value.find(m=>m.intent==='workflow'&&m.data?.threadId===threadId)
  if(item){item.data=res;item.reply=approved?'已提交审批结果；请核对后端实际状态。':'已拒绝取消申请。'}
 }catch(e){errorMessage(e)}finally{busy.value=false;await scroll()}
}
async function refresh(orderId){if(busy.value)return;busy.value=true;try{const r=await req(`/api/agent/transfers/${encodeURIComponent(String(orderId))}`);replaceOrder(r.data)}catch(e){errorMessage(e)}finally{busy.value=false;await scroll()}}
const money=x=>new Intl.NumberFormat('zh-CN',{style:'currency',currency:'CNY'}).format(Number(x))
const merchant=x=>x.merchantName??x.merchant_name??'—'
const when=x=>x.occurredAt??x.occurred_at??'—'
onMounted(checkHealth)
</script>
<template>
<div class="layout">
 <aside class="side"><div class="logo"><b>B</b><span>BankPilot<small>AI Banking Agent</small></span></div><div class="nav-title">开发里程碑</div><p>✓ Day 1 · 四层联通</p><p>✓ Day 2 · 银行查询</p><p>✓ Day 3 · 转账建单</p><p>✓ Day 4 · 授权执行</p><p>✓ Day 5 · LLM Tool Calling</p><p class="active">● Day 6 · 跨场景工作流</p><div class="side-foot">比赛演示环境<br/>全部账户、金额与转账为模拟数据</div></aside>
 <main>
  <header><div><h1>银行智能助手</h1><span>LLM 工具调用 · 受控转账 · 权限确认</span></div><span class="online" :class="connected?'ok':'bad'">● {{connected?'Agent 服务已连接':'Agent 服务未连接'}}</span></header>
  <section class="dev-token"><div class="mode-indicators"><strong>本地开发登录凭证</strong><span class="pill" :class="routerMode==='llm'?'llm-label':''">{{routerMode==='llm'? (modelConfigured ? `LLM 已配置 · ${modelName}` : 'LLM 尚未配置') : '规则模式（不调用模型）'}}</span><span class="pill">{{mode==='mock'?'Mock：不连接 MySQL':'Java：真实接口联调'}}</span></div>
   <div v-if="mode==='java'" class="token-line"><input type="password" v-model="loginPassword" autocomplete="current-password" placeholder="输入本地 DEMO_LOGIN_PASSWORD"/><button :disabled="busy||!loginPassword" @click="demoLogin">模拟银行登录</button></div><small v-if="loginMessage">{{loginMessage}}</small>
   <div class="token-line"><input type="password" v-model="token" autocomplete="off" placeholder="填入 Java 登录 Token（不含 Bearer 前缀）"/><button v-if="mode==='mock'" @click="token='mock-day4-token'">填入 Mock 测试令牌</button></div><small>仅在当前页面内存保存，不要使用真实银行卡、密码或 OTP。Mock 令牌不具备真实认证能力。</small></section>
  <section class="main-content">
   <div class="intro"><span class="eyebrow">BANKPILOT · DAY 06</span><h2>你好，今天需要办理什么？</h2><p>支持大模型选择受限银行工具、查询、转账建单及原有安全审批（启用模型需配置服务端 API Key）。</p><div class="chips"><button v-for="q in queries" :key="q" :disabled="busy" @click="send(q)">{{q}}</button></div></div>
   <section class="workflow-entry">
    <label for="workflowText">LangGraph 跨场景指令</label>
    <div class="token-line"><input id="workflowText" v-model="workflowText" maxlength="300" placeholder="分析消费、查询订阅、申请取消视频会员代扣"/><button type="button" :disabled="busy" @click="startWorkflow">启动跨场景任务</button></div>
    <small>此入口运行固定受控 DAG；单轮普通聊天继续使用 Day 5 工具路由。</small>
   </section>
   <section class="chat" aria-live="polite">
    <div v-for="m in messages" :key="m.id" class="msg" :class="m.role"><div class="avatar">{{m.role==='assistant'?'B':'我'}}</div><div class="msg-content"><div class="bubble">{{m.reply}}</div>
      <div v-if="m.intent==='balance'&&m.data" class="panel balance"><small>模拟账户余额 · {{m.data.accountNoMasked}}</small><strong>{{money(m.data.balance)}}</strong></div>
      <div v-if="m.intent==='transactions'&&Array.isArray(m.data)" class="panel"><h4>交易流水</h4><p v-if="!m.data.length">暂无流水</p><div v-for="t in m.data" :key="t.id" class="list-item"><div>{{merchant(t)}}<small>{{t.category}} · {{when(t)}}</small></div><strong>{{t.direction==='IN'?'+':'-'}}{{money(t.amount)}}</strong></div></div>
      <div v-if="m.intent==='payees'&&Array.isArray(m.data)" class="panel"><h4>常用收款人</h4><p v-if="!m.data.length">暂无记录</p><div v-for="p in m.data" :key="p.id" class="list-item"><strong>{{p.payeeName}}</strong><span>{{p.payeeAccountMasked}}</span></div></div>
      <div v-if="m.intent==='subscriptions'&&Array.isArray(m.data)" class="panel"><h4>订阅代扣</h4><p v-if="!m.data.length">暂无协议</p><div v-for="s in m.data" :key="s.id" class="list-item"><div>{{merchant(s)}}<small>{{s.status}} · {{s.billingCycle}}</small></div><strong>{{money(s.amount)}}</strong></div></div>
      <CrossScenarioCard v-if="m.intent==='workflow'&&m.data" :task="m.data" :busy="busy" @decision="decideWorkflow"/>
      <TransferForm v-if="m.intent==='transfer'&&m.action==='needs_input'&&m.data" :payees="m.data.payees" :payee-name="m.data.payeeName" :amount="m.data.amount" :request-id="m.data.requestId" :busy="busy" :completed="completedForms.includes(m.data.requestId)" @prepare="prepare"/>
      <TransferOrderCard v-if="m.intent==='transfer'&&m.data?.orderId" :order="m.data" :busy="busy" @authorize="d=>doAction('authorize',d.orderId,{confirmation:d.confirmation,otpCode:d.otpCode})" @otp-request="requestOtp" @execute="id=>doAction('execute',id)" @cancel="id=>doAction('cancel',id)" @refresh="refresh"/>
      <div v-if="m.source==='mock-api'" class="mock-warning">⚠ 当前使用 Mock 假银行，仅用于前端演示，未执行真实数据库事务。</div>
      <div v-if="m.routing==='llm'" class="routing-label">↗ 由大模型选择工具，银行数据以 Java 返回为准</div><div v-else-if="m.routing==='rules'&&m.intent!=='event'" class="routing-label">规则模式</div>
      <div v-if="m.requestId" class="req-id">请求 ID：{{m.requestId}}</div>
    </div></div>
    <p v-if="busy" class="thinking">正在调用银行服务…</p><div ref="lastRef"></div>
   </section>
  </section>
  <footer><form @submit.prevent="send()"><input v-model="input" :disabled="busy" placeholder="例如：给李四转200元" maxlength="300" aria-label="输入银行指令"/><button type="submit" :disabled="busy||!input.trim()">发送 ↗</button></form><small>Day5：仅在后端配置 API Key 后启用 LLM。模型只能查询或建单，授权/执行/取消始终由用户按钮和银行后端控制。</small></footer>
 </main>
</div>
</template>
