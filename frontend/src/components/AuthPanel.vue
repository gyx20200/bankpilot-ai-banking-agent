<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  mode: { type: String, default: 'login' },
  busy: { type: Boolean, default: false },
  notice: { type: String, default: '' },
})
const emit = defineEmits(['mode-change', 'login', 'register'])
const username = ref('')
const password = ref('')
const fullName = ref('')
const phone = ref('')
const confirmation = ref('')
const validationError = ref('')
// Presentation only: password visibility never changes authentication payloads.
const passwordVisible = ref(false)
const confirmationVisible = ref(false)

function clearInputs() {
  username.value = ''
  password.value = ''
  confirmation.value = ''
  fullName.value = ''
  phone.value = ''
  validationError.value = ''
  passwordVisible.value = false
  confirmationVisible.value = false
}
watch(() => props.mode, clearInputs)

function switchMode(mode) {
  if (props.busy || mode === props.mode) return
  clearInputs()
  emit('mode-change', mode)
}

function submit() {
  if (props.busy) return
  validationError.value = ''
  const name = username.value.trim()
  if (props.mode === 'login') {
    if (!name || !password.value) {
      validationError.value = '请填写用户名和密码。'
      return
    }
    emit('login', { username: name, password: password.value })
    password.value = ''
    return
  }
  if (!/^[A-Za-z0-9_]{3,32}$/.test(name)) {
    validationError.value = '用户名须为3～32位字母、数字或下划线。'
    return
  }
  if (password.value.length < 8 || password.value.length > 128) {
    validationError.value = '密码长度须为8～128位。'
    return
  }
  if (password.value !== confirmation.value) {
    validationError.value = '两次输入的密码不一致。'
    return
  }
  if (!fullName.value.trim() || fullName.value.trim().length > 50) {
    validationError.value = '姓名不能为空，且不能超过50个字符。'
    return
  }
  if (!/^1[3-9]\d{9}$/.test(phone.value.trim())) {
    validationError.value = '请填写正确的11位手机号。'
    return
  }
  emit('register', {
    username: name,
    password: password.value,
    fullName: fullName.value.trim(),
    phone: phone.value.trim(),
  })
  password.value = ''
  confirmation.value = ''
}
</script>

<template>
  <div class="auth-landing" aria-label="BankPilot 用户认证入口">
    <!-- Decorative scene. Business state, authentication calls and form validation stay untouched. -->
    <div class="auth-ambient auth-ambient-one" aria-hidden="true"></div>
    <div class="auth-ambient auth-ambient-two" aria-hidden="true"></div>
    <div class="auth-scene" aria-hidden="true">
      <svg viewBox="0 0 620 490" role="presentation" focusable="false">
        <defs>
          <linearGradient id="scene-floor" x1="0" y1="0" x2="0.9" y2="1">
            <stop offset="0" stop-color="#fbfdff" stop-opacity=".92" />
            <stop offset="1" stop-color="#8ebcff" stop-opacity=".17" />
          </linearGradient>
          <linearGradient id="scene-glass" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stop-color="#ffffff" stop-opacity=".88" />
            <stop offset=".53" stop-color="#d6e9ff" stop-opacity=".45" />
            <stop offset="1" stop-color="#478ee9" stop-opacity=".35" />
          </linearGradient>
          <linearGradient id="scene-bars" x1="0" y1="1" x2="1" y2="0">
            <stop offset="0" stop-color="#2572ef" />
            <stop offset="1" stop-color="#94caff" />
          </linearGradient>
          <linearGradient id="scene-column" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stop-color="#8bbfff" stop-opacity=".62" />
            <stop offset="1" stop-color="#e7f4ff" stop-opacity=".03" />
          </linearGradient>
          <filter id="scene-blur"><feGaussianBlur stdDeviation="13" /></filter>
          <filter id="scene-shadow" x="-50%" y="-50%" width="200%" height="200%">
            <feDropShadow dx="0" dy="18" stdDeviation="14" flood-color="#5b95dd" flood-opacity=".24" />
          </filter>
        </defs>
        <ellipse cx="315" cy="395" rx="250" ry="61" fill="#70aaff" opacity=".19" filter="url(#scene-blur)" />
        <g opacity=".72">
          <rect x="91" y="176" width="35" height="188" rx="5" fill="url(#scene-column)" />
          <rect x="135" y="133" width="31" height="228" rx="5" fill="url(#scene-column)" />
          <rect x="176" y="187" width="31" height="180" rx="5" fill="url(#scene-column)" />
          <rect x="455" y="106" width="34" height="265" rx="5" fill="url(#scene-column)" />
          <rect x="502" y="156" width="29" height="218" rx="5" fill="url(#scene-column)" />
        </g>
        <ellipse cx="330" cy="385" rx="232" ry="70" fill="url(#scene-floor)" stroke="white" stroke-opacity=".97" stroke-width="4" />
        <path d="M99 385v22c0 41 100 75 231 75s232-34 232-75v-22" fill="url(#scene-floor)" stroke="#ffffff" stroke-width="3" />
        <ellipse cx="330" cy="407" rx="230" ry="71" fill="none" stroke="#8cbcff" stroke-opacity=".27" stroke-width="2" />
        <g transform="translate(232 105)" filter="url(#scene-shadow)">
          <rect x="4" y="6" width="189" height="233" rx="25" fill="#83bbff" fill-opacity=".26" />
          <rect x="0" y="0" width="185" height="232" rx="24" fill="url(#scene-glass)" stroke="white" stroke-width="3" />
          <path d="M27 31h128" stroke="white" stroke-opacity=".55" stroke-width="3" stroke-linecap="round" />
          <path d="M29 199h123" stroke="#aed6ff" stroke-opacity=".63" stroke-width="2" stroke-linecap="round" />
          <rect x="32" y="132" width="26" height="57" rx="6" fill="url(#scene-bars)" stroke="#d9efff" stroke-width="2" />
          <rect x="72" y="98" width="26" height="91" rx="6" fill="url(#scene-bars)" stroke="#d9efff" stroke-width="2" />
          <rect x="112" y="68" width="26" height="121" rx="6" fill="url(#scene-bars)" stroke="#d9efff" stroke-width="2" />
          <path d="M44 132v54M84 99v86M124 70v115" stroke="white" stroke-opacity=".33" stroke-width="3" stroke-linecap="round" />
        </g>
        <path d="M14 395C92 345 136 348 201 384" stroke="white" stroke-opacity=".9" stroke-width="4" fill="none" />
        <path d="M450 374c71-31 102-24 163 8" stroke="white" stroke-opacity=".83" stroke-width="4" fill="none" />
        <circle cx="121" cy="133" r="5" fill="#fff" opacity=".85" />
        <circle cx="504" cy="92" r="4" fill="#fff" opacity=".85" />
      </svg>
    </div>

    <section class="auth-hero" aria-label="BankPilot 产品介绍">
      <div class="auth-hero-eyebrow"><span class="auth-eyebrow-line"></span> 智能银行 · 安心托付</div>
      <h2>更智能的<br /><span>银行服务体验</span></h2>
      <p class="auth-hero-description">用 AI 让复杂的银行事务<br class="auth-hero-break" />变得简单、高效、有条理。</p>
      <div class="auth-hero-rule" aria-hidden="true"></div>
      <div class="auth-features">
        <div class="auth-feature">
          <div class="auth-feature-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none"><path d="M13.5 2.5 5.5 13h6l-1 8.5L19 10h-6l.5-7.5Z" fill="currentColor" /></svg>
          </div>
          <div><strong>智能问答</strong><p>一句话，让金融操作更从容</p></div>
        </div>
        <div class="auth-feature">
          <div class="auth-feature-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none"><rect x="3" y="12" width="4" height="9" rx="1" fill="currentColor" opacity=".65"/><rect x="10" y="7" width="4" height="14" rx="1" fill="currentColor"/><rect x="17" y="3" width="4" height="18" rx="1" fill="currentColor" opacity=".82"/></svg>
          </div>
          <div><strong>账户分析</strong><p>轻松掌握每一笔收支动态</p></div>
        </div>
        <div class="auth-feature">
          <div class="auth-feature-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none"><path d="m12 2 8 3.7v6.1c0 5.2-3.5 8.4-8 10.2-4.5-1.8-8-5-8-10.2V5.7L12 2Z" fill="currentColor"/><path d="m8.6 11.8 2.4 2.4 4.6-4.8" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </div>
          <div><strong>安全可靠</strong><p>敏感操作由你亲自确认</p></div>
        </div>
      </div>
    </section>

    <section class="auth-panel" aria-label="银行用户认证">
      <div class="auth-topline"><span class="auth-topline-dot"></span> BANKPILOT <span class="auth-topline-separator">/</span> DAY 07</div>
      <h1>{{ mode === 'login' ? '登录模拟银行账户' : '注册模拟银行账户' }}</h1>
      <p class="auth-subtitle">{{ mode === 'login' ? '登录后即可使用你的专属银行账户与 AI 助手。' : '每人拥有独立模拟账户，注册完成后请自行登录。' }}</p>

      <div class="auth-tabs" role="group" aria-label="选择注册或登录">
        <button type="button" :class="{ active: mode === 'login' }" :aria-pressed="mode === 'login'" :disabled="busy" @click="switchMode('login')">登录</button>
        <button type="button" :class="{ active: mode === 'register' }" :aria-pressed="mode === 'register'" :disabled="busy" @click="switchMode('register')">注册</button>
      </div>

      <form class="auth-form" @submit.prevent="submit">
        <div class="auth-field">
          <label for="bank-username">用户名</label>
          <div class="auth-input-wrap">
            <svg class="auth-input-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="8" r="3.3" stroke="currentColor" stroke-width="1.8"/><path d="M5.5 20v-2a6.5 6.5 0 0 1 13 0v2H5.5Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>
            <input id="bank-username" v-model="username" name="username" autocomplete="username" maxlength="32" required :disabled="busy" placeholder="请输入用户名" />
          </div>
        </div>
        <template v-if="mode === 'register'">
          <div class="auth-field">
            <label for="bank-full-name">姓名</label>
            <div class="auth-input-wrap">
              <svg class="auth-input-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="3" y="4.5" width="18" height="15" rx="2.5" stroke="currentColor" stroke-width="1.8"/><circle cx="8.3" cy="10" r="2" stroke="currentColor" stroke-width="1.5"/><path d="M5.5 16c.5-2.2 5.1-2.2 5.7 0M14 9h4M14 13h4M14 16h3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
              <input id="bank-full-name" v-model="fullName" autocomplete="name" maxlength="50" required :disabled="busy" placeholder="模拟银行账户姓名" />
            </div>
          </div>
          <div class="auth-field">
            <label for="bank-phone">手机号</label>
            <div class="auth-input-wrap">
              <svg class="auth-input-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="6.5" y="2.5" width="11" height="19" rx="2.3" stroke="currentColor" stroke-width="1.8"/><path d="M10 18h4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>
              <input id="bank-phone" v-model="phone" type="tel" inputmode="numeric" autocomplete="tel" maxlength="11" required :disabled="busy" placeholder="11位手机号码" />
            </div>
          </div>
        </template>
        <div class="auth-field">
          <label for="bank-password">密码</label>
          <div class="auth-input-wrap">
            <svg class="auth-input-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="5" y="10.5" width="14" height="11" rx="2" stroke="currentColor" stroke-width="1.8"/><path d="M8 10.5V7a4 4 0 0 1 8 0v3.5" stroke="currentColor" stroke-width="1.8"/><circle cx="12" cy="16" r="1" fill="currentColor"/></svg>
            <input id="bank-password" v-model="password" :type="passwordVisible ? 'text' : 'password'" :autocomplete="mode === 'login' ? 'current-password' : 'new-password'" :minlength="mode === 'register' ? 8 : 1" maxlength="128" required :disabled="busy" placeholder="请输入密码" />
            <button type="button" class="auth-visibility" :aria-label="passwordVisible ? '隐藏密码' : '显示密码'" :aria-pressed="passwordVisible" :disabled="busy" @click="passwordVisible = !passwordVisible">
              <svg v-if="passwordVisible" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M2.5 12S6 6.5 12 6.5 21.5 12 21.5 12 18 17.5 12 17.5 2.5 12 2.5 12Z" stroke="currentColor" stroke-width="1.7"/><circle cx="12" cy="12" r="2.7" stroke="currentColor" stroke-width="1.7"/></svg>
              <svg v-else viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M3 3 21 21M10.4 6.7c.5-.1 1-.2 1.6-.2 6 0 9.5 5.5 9.5 5.5a15 15 0 0 1-3 3.2M6.1 8.1C3.7 9.8 2.5 12 2.5 12S6 17.5 12 17.5c1.5 0 2.8-.3 4-.9M9.9 9.9a3 3 0 0 0 4.2 4.2" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </button>
          </div>
        </div>
        <template v-if="mode === 'register'">
          <div class="auth-field">
            <label for="bank-confirm-password">确认密码</label>
            <div class="auth-input-wrap">
              <svg class="auth-input-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="5" y="10.5" width="14" height="11" rx="2" stroke="currentColor" stroke-width="1.8"/><path d="M8 10.5V7a4 4 0 0 1 8 0v3.5" stroke="currentColor" stroke-width="1.8"/><circle cx="12" cy="16" r="1" fill="currentColor"/></svg>
              <input id="bank-confirm-password" v-model="confirmation" :type="confirmationVisible ? 'text' : 'password'" autocomplete="new-password" minlength="8" maxlength="128" required :disabled="busy" placeholder="再次输入密码" />
              <button type="button" class="auth-visibility" :aria-label="confirmationVisible ? '隐藏确认密码' : '显示确认密码'" :aria-pressed="confirmationVisible" :disabled="busy" @click="confirmationVisible = !confirmationVisible">
                <svg v-if="confirmationVisible" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M2.5 12S6 6.5 12 6.5 21.5 12 21.5 12 18 17.5 12 17.5 2.5 12 2.5 12Z" stroke="currentColor" stroke-width="1.7"/><circle cx="12" cy="12" r="2.7" stroke="currentColor" stroke-width="1.7"/></svg>
                <svg v-else viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M3 3 21 21M10.4 6.7c.5-.1 1-.2 1.6-.2 6 0 9.5 5.5 9.5 5.5a15 15 0 0 1-3 3.2M6.1 8.1C3.7 9.8 2.5 12 2.5 12S6 17.5 12 17.5c1.5 0 2.8-.3 4-.9M9.9 9.9a3 3 0 0 0 4.2 4.2" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
            </div>
          </div>
        </template>
        <p v-if="validationError" class="auth-error" role="alert">{{ validationError }}</p>
        <p v-if="notice" class="auth-notice" role="status">{{ notice }}</p>
        <button type="submit" class="auth-submit" :disabled="busy">
          <span>{{ busy ? '请稍候…' : (mode === 'login' ? '登录' : '注册账户') }}</span>
          <svg v-if="!busy" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M4 12h16m-6-6 6 6-6 6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
          <span v-if="busy" class="auth-button-spinner" aria-hidden="true"></span>
        </button>
      </form>
      <div class="auth-mode-switch">
        {{ mode === 'login' ? '还没有账户？' : '已经有账户？' }}
        <button type="button" :disabled="busy" @click="switchMode(mode === 'login' ? 'register' : 'login')">{{ mode === 'login' ? '立即注册' : '返回登录' }}</button>
      </div>
      <div class="auth-card-divider"></div>
      <p class="auth-footnote">仅供模拟银行演示 <span>·</span> 登录凭证不会写入浏览器本地存储</p>
    </section>
  </div>
</template>
