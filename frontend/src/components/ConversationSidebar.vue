<script setup>
import { computed } from "vue";

const props = defineProps({
  conversations: {
    type: Array,
    default: () => [],
  },

  activeConversationId: {
    type: String,
    default: null,
  },

  loading: {
    type: Boolean,
    default: false,
  },

  error: {
    type: String,
    default: "",
  },
});

const emit = defineEmits(["create", "select"]);

const hasConversations = computed(() => props.conversations.length > 0);

function formatTime(value) {
  if (!value) return "";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "";
  }

  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}
</script>

<template>
  <aside class="conversation-sidebar" aria-label="历史会话">
    <div class="conversation-header">
      <h2>历史会话</h2>

      <button type="button" :disabled="loading" @click="emit('create')">
        + 新建会话
      </button>
    </div>

    <p v-if="loading" class="conversation-state">正在加载会话...</p>

    <p v-else-if="error" class="conversation-error" role="alert">
      {{ error }}
    </p>

    <p v-else-if="!hasConversations" class="conversation-state">暂无历史会话</p>

    <ul v-else class="conversation-list">
      <li v-for="item in props.conversations" :key="item.conversationId">
        <button
          type="button"
          class="conversation-item"
          :class="{
            active: item.conversationId === activeConversationId,
          }"
          :disabled="loading"
          :aria-current="
            item.conversationId === activeConversationId ? 'page' : undefined
          "
          @click="emit('select', item.conversationId)"
        >
          <span class="conversation-title">
            {{ item.title || "未命名会话" }}
          </span>

          <span class="conversation-time">
            {{ formatTime(item.updatedAt || item.createdAt) }}
          </span>
        </button>
      </li>
    </ul>
  </aside>
</template>

<style scoped>
.conversation-sidebar {
  width: 240px;
  height: 100%;
  padding: 16px;
  background: #f8fafc;
  border-right: 1px solid #e5eaf1;
  overflow-y: auto;
}

.conversation-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 18px;
}

.conversation-header h2 {
  font-size: 15px;
  color: #263f5d;
  margin: 0;
}

.conversation-header button {
  border: 0;
  border-radius: 7px;
  background: #2e79ca;
  color: white;
  padding: 7px 9px;
  font-size: 11px;
}

.conversation-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: grid;
  gap: 7px;
}

.conversation-item {
  display: flex;
  flex-direction: column;
  gap: 5px;
  width: 100%;
  padding: 11px;
  text-align: left;
  border: 1px solid transparent;
  border-radius: 9px;
  background: transparent;
  color: #3b526d;
}

.conversation-item:hover,
.conversation-item.active {
  background: white;
  border-color: #dce7f4;
}

.conversation-title {
  font-size: 12px;
  font-weight: 650;
  overflow-wrap: anywhere;
}

.conversation-time,
.conversation-state {
  color: #91a0b1;
  font-size: 10px;
}

.conversation-error {
  color: #b45353;
  font-size: 11px;
}
</style>
