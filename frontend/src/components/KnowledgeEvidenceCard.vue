<script setup>
import { computed } from 'vue'

const props = defineProps({
  data: { type: Object, required: true },
})

// Only a grounded public-knowledge result can present sources as supporting evidence.
const grounded = computed(
  () => props.data?.grounded === true && props.data?.dataOrigin === 'PUBLIC_OFFICIAL',
)
const citations = computed(() =>
  grounded.value && Array.isArray(props.data?.citations) ? props.data.citations : [],
)

// These codes are returned by the D9 RAG backend; never infer evidence status from text.
const refusalMessages = {
  NO_EVIDENCE: {
    reason: '当前已审核的公开资料中，没有检索到足以回答该问题的相关证据。这并不意味着相反结论已经成立。',
    action: '请查看相关主管部门或官方机构发布的最新原始资料。',
  },
  NO_RANKED_EVIDENCE: {
    reason: '虽然检索到候选资料，但经相关性筛选和重排后，没有保留足以支持确定结论的证据。',
    action: '可核对问题所涉及的具体政策、机构或官方文件。',
  },
  UNSUPPORTED_NUMERIC_FACT: {
    reason: '生成回答中存在无法从检索证据正文核实的数字，因此系统阻止了该回答作为事实展示。',
    action: '涉及金额、比例、年份等信息时，请以官方原文为准。',
  },
  UNVERIFIED_BANKPILOT_CLAIM: {
    reason: '生成内容涉及尚未核实的 BankPilot 机构资质、存款保障或收益承诺；一般金融法规不能证明这些具体事实。',
    action: '请区分真实投保机构的法定保障与 BankPilot 模拟账户的演示数据。',
  },
  INSTITUTION_STATUS_UNVERIFIED: {
    reason: '现有公开资料介绍的是存款保险制度的一般规则，缺少能够证明 BankPilot 具体投保资格或保障状态的机构级证据。',
    action: '不能仅凭模拟账户余额或一般法规认定 BankPilot 已投保；如需核实真实机构，请查阅该机构及监管部门的官方信息。',
  },
  MODEL_GENERATED_URL: {
    reason: '生成内容包含未经审核的来源链接，系统没有将该链接视为可信证据。',
    action: '请通过经过核实的官方发布渠道查找原文。',
  },
  EMPTY_ANSWER: {
    reason: '本次模型未生成可用的回答，无法进行可靠的证据核验。',
    action: '可稍后重新进行公开知识查询，或直接查阅官方资料。',
  },
}

const refusalInfo = computed(() => {
  const code = props.data?.quality?.reasonCode
  return refusalMessages[code] || {
    reason: '当前没有足够且通过校验的证据支持确定结论，系统没有将未经核实的内容当作事实。',
    action: '请核对相关机构的最新官方资料。',
  }
})

function safeUrl(url) {
  try {
    const parsed = new URL(url)
    const allow = ['xzfg.moj.gov.cn', 'wzdt.pbc.gov.cn', 'www.pbccrc.org.cn', 'www.moj.gov.cn']
    return parsed.protocol === 'https:' && allow.includes(parsed.hostname) ? parsed.href : null
  } catch {
    return null
  }
}
</script>

<template>
  <section class="rag-evidence" aria-label="公开金融资料检索结果">
    <header class="rag-header">
      <strong>银行公开知识问答</strong>
      <span>公开来源 · RAG</span>
    </header>

    <p class="answer">{{ data.answer || '本次未生成可供核实的知识答复。' }}</p>

    <div v-if="!grounded" class="evidence-notice" role="status">
      <strong class="notice-title">当前结论尚未核实</strong>
      <p><span class="notice-label">原因：</span>{{ refusalInfo.reason }}</p>
      <p><span class="notice-label">建议：</span>{{ refusalInfo.action }}</p>
      <p class="notice-boundary">证据不足不等于事实已被否定，也不能据此认定某项保障或资格已经成立。</p>
    </div>

    <div v-if="citations.length" class="sources">
      <strong>参考资料（{{ citations.length }}）</strong>
      <article
        v-for="(item, index) in citations"
        :key="`${item.sourceId}-${item.section}-${index}`"
      >
        <div class="source-title">[{{ index + 1 }}] {{ item.title }}</div>
        <p class="meta">{{ item.issuer }} · {{ item.section }} · 核对日期 {{ item.checkedAt }}</p>
        <p class="snippet">{{ item.snippet }}</p>
        <a
          v-if="safeUrl(item.url)"
          :href="safeUrl(item.url)"
          target="_blank"
          rel="noopener noreferrer"
        >查看官方原文</a>
      </article>
    </div>

    <p class="footnote">
      公开金融制度知识不等同于 BankPilot 模拟账户或银行产品规则。请以最新官方原文为准。
    </p>
  </section>
</template>

<style scoped>
.rag-evidence {
  border: 1px solid #dce4f0;
  border-radius: 12px;
  padding: 16px;
  background: #fff;
  color: #203552;
  font-size: 13px;
  max-width: 760px;
}
.rag-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid #eef1f5;
}
.rag-header span,
.meta,
.footnote {
  font-size: 12px;
  color: #66788f;
}
.answer {
  line-height: 1.8;
  white-space: pre-wrap;
  margin: 12px 0;
  overflow-wrap: anywhere;
}
.evidence-notice {
  margin: 12px 0;
  border-left: 3px solid #d4a458;
  border-radius: 6px;
  padding: 10px 12px;
  background: #fffbf3;
  color: #69502a;
  line-height: 1.7;
}
.notice-title {
  display: block;
  margin-bottom: 5px;
}
.evidence-notice p {
  margin: 5px 0 0;
}
.notice-label {
  font-weight: 600;
}
.notice-boundary {
  font-size: 12px;
  color: #7d6540;
}
.sources {
  border-top: 1px solid #e8edf3;
  padding-top: 10px;
}
.sources article {
  border: 1px solid #edf1f6;
  border-radius: 9px;
  padding: 11px;
  margin-top: 10px;
}
.source-title {
  font-weight: 600;
}
.snippet {
  color: #4c617a;
  line-height: 1.6;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.rag-evidence a {
  color: #2168b2;
  text-decoration: underline;
}
.footnote {
  margin-top: 14px;
  line-height: 1.6;
}
</style>
