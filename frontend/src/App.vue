<script setup>
import {ref,nextTick,onMounted} from 'vue'
import TransferForm from './components/TransferForm.vue'
import TransferOrderCard from './components/TransferOrderCard.vue'
const messages=ref([{id:'welcome',role:'assistant',reply:'你好，我是 BankPilot。本地模拟银行支持账户查询和带审批的模拟转账。',intent:'welcome'}])
const input=ref('')
const token=ref('')  // Developer demo only; in-memory, never localStorage
const mode=ref('java')
const connected=ref(false)
const busy=ref(false)
const completedForms=ref([])
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
async function checkHealth(){try{const x=await req('/api/agent/health');mode.value=x.bankMode==='mock'?'mock':'java';connected.value=true}catch{connected.value=false}}
async function send(text){const s=String(text||input.value).trim();if(!s||busy.value)return;input.value='';busy.value=true;messages.value.push({id:crypto.randomUUID(),role:'user',reply:s});await scroll();try{addMessage(await req('/api/agent/chat','POST',{message:toSay[s]||s,requestId:crypto.randomUUID()}))}catch(e){errorMessage(e)}finally{busy.value=false;await scroll()}}
async function prepare(form){if(busy.value||completedForms.value.includes(form.requestId))return;busy.value=true;try{const data=await req('/api/agent/transfers/prepare','POST',form);completedForms.value.push(form.requestId);addMessage(data)}catch(e){errorMessage(e)}finally{busy.value=false;await scroll()}}
async function doAction(action,orderId,payload={}){
 if(busy.value)return
 busy.value=true
 try{const r=await req(`/api/agent/transfers/${encodeURIComponent(String(orderId))}/${action}`,'POST',{requestId:crypto.randomUUID(),...payload});replaceOrder(r.data);addMessage({reply:r.reply,intent:'event',action:r.action})}catch(e){errorMessage(e)}finally{busy.value=false;await scroll()}
}
async function refresh(orderId){if(busy.value)return;busy.value=true;try{const r=await req(`/api/agent/transfers/${encodeURIComponent(String(orderId))}`);replaceOrder(r.data)}catch(e){errorMessage(e)}finally{busy.value=false;await scroll()}}
const money=x=>new Intl.NumberFormat('zh-CN',{style:'currency',currency:'CNY'}).format(Number(x))
const merchant=x=>x.merchantName??x.merchant_name??'—'
const when=x=>x.occurredAt??x.occurred_at??'—'
onMounted(checkHealth)
</script>
<template>
<div class="layout">
 <aside class="side"><div class="logo"><b>B</b><span>BankPilot<small>AI Banking Agent</small></span></div><div class="nav-title">开发里程碑</div><p>✓ Day 1 · 四层联通</p><p>✓ Day 2 · 银行查询</p><p>✓ Day 3 · 转账建单</p><p class="active">● Day 4 · 授权执行</p><div class="side-foot">比赛演示环境<br/>全部账户、金额与转账为模拟数据</div></aside>
 <main>
  <header><div><h1>银行智能助手</h1><span>自然语言转账 · 权限确认 · 强验证</span></div><span class="online" :class="connected?'ok':'bad'">● {{connected?'Agent 服务已连接':'Agent 服务未连接'}}</span></header>
  <section class="dev-token"><div><strong>本地开发登录凭证</strong><span class="pill">{{mode==='mock'?'Mock：不连接 MySQL':'Java：真实接口联调'}}</span></div><div class="token-line"><input type="password" v-model="token" autocomplete="off" placeholder="填入 Java 登录 Token（不含 Bearer 前缀）"/><button v-if="mode==='mock'" @click="token='mock-day4-token'">填入 Mock 测试令牌</button></div><small>仅在当前页面内存保存，不要使用真实银行卡、密码或 OTP。Mock 令牌不具备真实认证能力。</small></section>
  <section class="main-content">
   <div class="intro"><span class="eyebrow">BANKPILOT · DAY 04</span><h2>你好，今天需要办理什么？</h2><p>支持银行查询、转账建单、用户授权、红色模拟验证码和模拟资金执行。</p><div class="chips"><button v-for="q in queries" :key="q" :disabled="busy" @click="send(q)">{{q}}</button></div></div>
   <section class="chat" aria-live="polite">
    <div v-for="m in messages" :key="m.id" class="msg" :class="m.role"><div class="avatar">{{m.role==='assistant'?'B':'我'}}</div><div class="msg-content"><div class="bubble">{{m.reply}}</div>
      <div v-if="m.intent==='balance'&&m.data" class="panel balance"><small>模拟账户余额 · {{m.data.accountNoMasked}}</small><strong>{{money(m.data.balance)}}</strong></div>
      <div v-if="m.intent==='transactions'&&Array.isArray(m.data)" class="panel"><h4>交易流水</h4><p v-if="!m.data.length">暂无流水</p><div v-for="t in m.data" :key="t.id" class="list-item"><div>{{merchant(t)}}<small>{{t.category}} · {{when(t)}}</small></div><strong>{{t.direction==='IN'?'+':'-'}}{{money(t.amount)}}</strong></div></div>
      <div v-if="m.intent==='payees'&&Array.isArray(m.data)" class="panel"><h4>常用收款人</h4><p v-if="!m.data.length">暂无记录</p><div v-for="p in m.data" :key="p.id" class="list-item"><strong>{{p.payeeName}}</strong><span>{{p.payeeAccountMasked}}</span></div></div>
      <div v-if="m.intent==='subscriptions'&&Array.isArray(m.data)" class="panel"><h4>订阅代扣</h4><p v-if="!m.data.length">暂无协议</p><div v-for="s in m.data" :key="s.id" class="list-item"><div>{{merchant(s)}}<small>{{s.status}} · {{s.billingCycle}}</small></div><strong>{{money(s.amount)}}</strong></div></div>
      <TransferForm v-if="m.intent==='transfer'&&m.action==='needs_input'&&m.data" :payees="m.data.payees" :payee-name="m.data.payeeName" :amount="m.data.amount" :request-id="m.data.requestId" :busy="busy" :completed="completedForms.includes(m.data.requestId)" @prepare="prepare"/>
      <TransferOrderCard v-if="m.intent==='transfer'&&m.data?.orderId" :order="m.data" :busy="busy" @authorize="d=>doAction('authorize',d.orderId,{confirmation:d.confirmation,otpCode:d.otpCode})" @execute="id=>doAction('execute',id)" @cancel="id=>doAction('cancel',id)" @refresh="refresh"/>
      <div v-if="m.source==='mock-api'" class="mock-warning">⚠ 当前使用 Mock 假银行，仅用于前端演示，未执行真实数据库事务。</div>
      <div v-if="m.requestId" class="req-id">请求 ID：{{m.requestId}}</div>
    </div></div>
    <p v-if="busy" class="thinking">正在调用银行服务…</p><div ref="lastRef"></div>
   </section>
  </section>
  <footer><form @submit.prevent="send()"><input v-model="input" :disabled="busy" placeholder="例如：给李四转200元" maxlength="300" aria-label="输入银行指令"/><button type="submit" :disabled="busy||!input.trim()">发送 ↗</button></form><small>Day4：规则路由，无真实 LLM；所有操作遵循银行后端结果，禁止在聊天文本中直接执行转账。</small></footer>
 </main>
</div>
</template>
