<script setup>
import { ref } from 'vue'
const query = ref('查询我的余额')
const response = ref('')
const busy = ref(false)
async function send() {
  if (!query.value.trim()) return
  busy.value = true
  response.value = ''
  try {
    const res = await fetch('/api/agent/chat', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: query.value })
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || '服务异常')
    response.value = data.reply
  } catch (err) { response.value = '请求失败：' + err.message }
  finally { busy.value = false }
}
</script>
<template>
  <main>
    <div class="top"><span>BankPilot</span><span class="tag">本地演示 · 非真实银行</span></div>
    <h1>银行智能体 · Day 1</h1>
    <p>今天先打通网页 → Python → Java → MySQL 的数据查询链路。</p>
    <form @submit.prevent="send">
      <input v-model="query" placeholder="例如：查询我的余额" aria-label="输入银行业务需求"/>
      <button :disabled="busy">{{busy ? '查询中…' : '发送'}}</button>
    </form>
    <div class="answer">{{ response || '输入“查询我的余额”，然后点击发送。' }}</div>
    <small>注意：当前用固定规则判断意图，并不是接入大语言模型。所有账户与金额均为模拟数据。</small>
  </main>
</template>
<style>
*{box-sizing:border-box}body{margin:0;background:#f4f6fa;color:#14253a;font-family:system-ui,-apple-system,'Microsoft YaHei',sans-serif}main{max-width:720px;margin:60px auto;background:#fff;border:1px solid #e0e5ed;border-radius:20px;padding:30px;box-shadow:0 8px 30px #192c4412}.top{display:flex;justify-content:space-between;font-weight:700}.tag{font-size:12px;background:#e7f3ed;color:#207253;padding:5px 10px;border-radius:30px}h1{margin:28px 0 8px}p{color:#67788d}form{display:flex;gap:10px;margin:25px 0}input{flex:1;min-width:0;padding:12px 14px;border:1px solid #cbd5e1;border-radius:9px;font-size:16px}button{border:0;background:#21549d;color:white;border-radius:9px;padding:12px 20px;cursor:pointer}button:disabled{opacity:.6}.answer{background:#f4f7fc;border-radius:12px;padding:20px;min-height:68px;line-height:1.7}small{display:block;margin-top:20px;color:#77869a}@media(max-width:680px){main{margin:15px;padding:20px}form{flex-direction:column}}
</style>
