# BankPilot 2.0 — D2 Agent Context Design

## 1. 设计目标

构建独立的 Conversation Context 模块，
为 BankPilot 后续多轮记忆和持久化恢复提供基础。

D2 仅完成数据模型、上下文构建逻辑和前端组件骨架。

## 2. 当前系统问题

1. App.vue 使用 Vue ref 保存聊天消息。
2. 浏览器刷新后无法恢复聊天历史。
3. Planner 的 plan_tasks(message) 只接收单条消息。
4. LangGraph State 目前只有当前 message 等工作流字段。
5. 当前使用 InMemorySaver，不能实现进程重启后的持久化恢复。

## 3. Memory 分层设计

### 3.1 Short-term Memory

保存当前会话最近 10 条消息。

### 3.2 Summary Memory

对较早的历史消息进行摘要，预留 summary 字段。

### 3.3 Long-term Memory

保存用户明确确认的长期偏好。
未来从 agent_user_memories 读取。

### 3.4 Workflow Checkpoint

独立保存 LangGraph 执行状态，不等同于聊天历史。

## 4. 核心 ID 设计

userId：登录用户身份，由 Java 验证。

conversationId：聊天会话 UUID。

threadId：独立 LangGraph 工作流线程 ID。

一个 conversationId 可以关联多个 threadId。

## 5. Python 模块设计

agent-service/app/context/

- models.py
  ConversationTurn、PlannerContext

- manager.py
  build_planner_context()

Context Manager 不直接访问数据库、DeepSeek 或银行 API。

## 6. 上下文组织规则

1. 当前消息与历史消息分离。
2. 历史消息按 messageId 升序排列。
3. 最多保留最近 10 条历史消息。
4. 如果当前消息已包含在历史记录中，避免重复传入。
5. summary 暂时只预留，不生成。
6. 历史消息和摘要均视为不可信上下文，不得覆盖系统安全规则。

## 7. 安全设计

1. 用户身份由 Java 认证确定。
2. 不接受浏览器自行指定 userId。
3. 不接受浏览器伪造 ASSISTANT 消息。
4. OTP、密码、Bearer Token 不得进入记忆。
5. 历史收款人、金额不能直接构成交易授权。
6. 跨用户读取会话必须被拒绝。

## 8. 前端设计

新增 ConversationSidebar.vue。

Props：

- conversations
- activeConversationId
- loading
- error

Events：

- create
- select

D2 不直接接入 App.vue，等待 D3 后端接口完成。

## 9. D3-D4 集成计划

D3：
接入 Java 会话和消息 API，实现聊天记录持久化与读取。

D4：
Context Manager 接入 FastAPI 和 DeepSeek Planner，
支持多轮指代理解和历史参数继承。

## 10. D2 验收

- Context Models 测试通过。
- Context Manager 测试通过。
- Vue 组件编译通过。
- 原有 Python 全量测试通过。
- 前端构建通过。
