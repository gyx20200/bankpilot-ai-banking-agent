<script setup>
import { computed } from 'vue'

const props = defineProps({ data: { type: Object, required: true } })
const citations = computed(() => Array.isArray(props.data?.citations) ? props.data.citations : [])
const grounded = computed(() => props.data?.grounded === true && props.data?.dataOrigin === 'PUBLIC_OFFICIAL')
function safeUrl(url) {
  try {
    const parsed = new URL(url)
    const allow = ['xzfg.moj.gov.cn', 'wzdt.pbc.gov.cn', 'www.pbccrc.org.cn', 'www.moj.gov.cn']
    return parsed.protocol === 'https:' && allow.includes(parsed.hostname) ? parsed.href : null
  } catch { return null }
}
</script>

<template>
  <section class="rag-evidence" aria-label="公开金融资料检索结果">
    <header><strong>银行公开知识问答</strong><span>公开来源 · RAG</span></header>
    <p class="answer">{{ data.answer || '未生成知识答复。' }}</p>
    <p v-if="!grounded" class="warning">资料不足，当前问题未获得可核实的知识答案。</p>
    <div v-if="citations.length" class="sources">
      <strong>参考资料（{{ citations.length }}）</strong>
      <article v-for="(item, index) in citations" :key="item.sourceId + item.section + index">
        <div class="source-title">[{{ index + 1 }}] {{ item.title }}</div>
        <p class="meta">{{ item.issuer }} · {{ item.section }} · 核对日期 {{ item.checkedAt }}</p>
        <p class="snippet">{{ item.snippet }}</p>
        <a v-if="safeUrl(item.url)" :href="safeUrl(item.url)" target="_blank" rel="noopener noreferrer">查看官方原文</a>
      </article>
    </div>
    <p class="footnote">公开金融制度知识不等同于 BankPilot 模拟账户或银行产品规则。请以最新官方原文为准。</p>
  </section>
</template>

<style scoped>
.rag-evidence{border:1px solid #dce4f0;border-radius:12px;padding:16px;background:#fff;color:#203552;font-size:13px;max-width:760px}
header{display:flex;justify-content:space-between;align-items:center;gap:12px;padding-bottom:10px;border-bottom:1px solid #eef1f5}
header span,.meta,.footnote{font-size:12px;color:#66788f}.answer{line-height:1.8;white-space:pre-wrap;margin:12px 0}.sources{border-top:1px solid #e8edf3;padding-top:10px}.sources article{border:1px solid #edf1f6;border-radius:9px;padding:11px;margin-top:10px}.source-title{font-weight:600}.snippet{color:#4c617a;line-height:1.6}.rag-evidence a{color:#2168b2;text-decoration:underline}.footnote{margin-top:14px;line-height:1.6}.warning{color:#a16a12}
</style>
