# BankPilot 2.0 — D2 记忆与会话数据模型设计（评审草案）

> 日期：2026-11-17  
> 负责人：成员 A（Java / MySQL）  
> 状态：**DESIGN DRAFT / 未执行迁移 / 待成员 B 联合评审**  
> 目标测试库：`bankpilot_day7_test`（**仅作设计参照，D2 不执行 DDL**）

## 1. 目标与范围

在不修改已有转账、AA、预约转账、账户、资金流水等表的前提下，定义可持久化的用户会话、消息、经用户同意的长期偏好，以及会话与 LangGraph 工作流线程的关联。

**D2 仅产出设计文档和 SQL 草稿，不实现 Controller/Service，不调用业务写接口，也不运行迁移 SQL。** 正式迁移拟在 D3 经评审后建立为 `database/12_agent_conversations.sql`。

四个逻辑实体：

| 表 | 职责 | 是否保存金融执行状态 / Checkpoint |
|---|---|---|
| `agent_conversations` | 用户可见的对话元数据及归属 | 否 |
| `agent_messages` | 经脱敏的用户/助手消息 | 否 |
| `agent_user_memories` | 经用户明确确认的长期偏好 | 否 |
| `agent_workflow_sessions` | 对话、用户及 Graph 线程的映射和生命周期 | **仅映射与状态摘要，不保存 Checkpoint** |

## 2. 已有系统基线（根据 main 分支与 D1 结果）

- D1：`bankpilot_day7_test` 共 21 张表；`users.id` 为 `BIGINT`。
- 已存在 `agent_workflow_runs(id BIGINT, user_id BIGINT, workflow_id VARCHAR(64), plan_hash CHAR(64), created_at DATETIME(6))`，旧版迁移中具有 `UNIQUE(user_id, workflow_id)`；它记录经过验证的计划，不存聊天和 Graph Checkpoint。
- `agent_workflow_tasks` 通过 `run_id` 与旧业务计划表关联，不应因本次设计重命名/删除。
- Java `Day7AuthController.me()` 使用 `AuthenticatedUser.id()`；新 API 应沿用从已验证登录身份读取 `userId` 的方式。
- Python `workflow_api.py` 当前采用进程内 `_sessions` 映射，Graph 使用 `InMemorySaver`；**只新增本方案四张表也不会让 Graph Checkpoint 在重启后自动恢复**。
- 现有 Python Graph `threadId` 是工作流执行标识，不等于对话 `conversationId`；一个对话可以关联多个 `threadId`。

D2 的只读数据库核验（尚需在本机执行并归档结构结论）：

```sql
USE bankpilot_day7_test;
SELECT DATABASE();
SHOW CREATE TABLE users;
SHOW CREATE TABLE agent_workflow_runs;
SHOW CREATE TABLE agent_workflow_tasks;
```

**待核验项：** 现有库中字段长度、字符集/排序规则、实际外键/唯一约束与索引；以上 Git 迁移定义不能替代本机 `SHOW CREATE TABLE` 的实际结果。

## 3. ID 和信任边界

| 标识 | 建议类型 / 格式 | 生成方与用途 |
|---|---|---|
| `userId`（DB: `user_id`） | `BIGINT` | Java 从有效 Bearer Token 解析；浏览器/LLM **不得指定他人 userId** |
| `conversationId`（DB: `id`） | UUID 字符串 `CHAR(36)` | Java 创建会话时生成，永久标识一段对话 |
| `messageId`（DB: `id`） | `BIGINT` 自增 | Java/数据库生成，仅用于排序、分页和定位 |
| `threadId`（DB: `thread_id`） | `VARCHAR(128)` | Python LangGraph 工作流生成；同一会话可关联多个线程 |
| `workflowId`（DB: `workflow_id`） | `VARCHAR(64)`、可空 | 既有 Java 计划登记 ID；不保证跨用户单独唯一 |

基本关系：

```text
users (1)
  ├── (N) agent_conversations (1) ── (N) agent_messages
  │                             └── (N) agent_workflow_sessions
  └── (N) agent_user_memories

agent_workflow_sessions.workflow_id -- 可选、用户范围内的逻辑关联 -->
  agent_workflow_runs.(user_id, workflow_id)
```

**禁止**仅凭 `conversationId`、`threadId` 或 `workflowId` 存在，就绕过 Java 用户归属校验。所有查询需以认证后 `user_id` 作为限制条件；线程继续执行时 Python 也应重新向 Java 验证用户身份与线程归属。

## 4. 详细表定义

### 4.1 `agent_conversations`

| 字段 | 建议类型 | 约束 / 语义 |
|---|---|---|
| `id` | `CHAR(36)` | PK，Java 生成 UUID |
| `user_id` | `BIGINT` | NOT NULL，FK → `users.id` |
| `title` | `VARCHAR(100)` | NOT NULL，默认 `新会话`；应清洗控制字符与敏感信息 |
| `status` | `VARCHAR(20)` | NOT NULL，`ACTIVE` / `ARCHIVED` |
| `created_at` | `DATETIME(6)` | NOT NULL；**约定存 UTC** |
| `updated_at` | `DATETIME(6)` | NOT NULL；**约定存 UTC**，写入消息时事务性刷新 |

- 索引：`(user_id, updated_at)` 支持当前用户列表排序；`(id, user_id)` 可供未来组合外键做同用户归属约束（D3 定稿）。
- 不能依据 `status=ARCHIVED` 推断所有关联工作流已被银行取消。

### 4.2 `agent_messages`

| 字段 | 建议类型 | 约束 / 语义 |
|---|---|---|
| `id` | `BIGINT AUTO_INCREMENT` | PK；稳定游标分页 |
| `conversation_id` | `CHAR(36)` | NOT NULL，FK → `agent_conversations.id` |
| `role` | `VARCHAR(20)` | `USER` / `ASSISTANT`，加 CHECK |
| `content` | `TEXT` | NOT NULL，仅保存经过审核的、脱敏的文本 |
| `created_at` | `DATETIME(6)` | NOT NULL，存 UTC |

- 索引：`(conversation_id, id)`，按 `id` 排序与 `beforeId` 游标分页。
- 写入前从会话查归属 `WHERE id=? AND user_id=?`，避免跨用户插入。
- **浏览器不能选择 `role=ASSISTANT`**；助手消息只能由经过认证与授权的服务端内部写入。D2 不开放任意角色写入的公共接口。
- 在消息表中不保存原始 OTP、银行卡密码、Bearer Token、完整银行卡号等。脱敏失败须拒绝落库，不得把原文先写进日志。
- 若 D3 需要请求幂等，评审可补 `client_request_id`/`message_request_id` 及对应唯一索引；不要直接复用转账 `request_id` 的语义。

### 4.3 `agent_user_memories`（D2 只做结构设计，暂不写 DDL）

| 字段 | 建议类型 | 约束 / 语义 |
|---|---|---|
| `id` | `BIGINT AUTO_INCREMENT` | PK |
| `user_id` | `BIGINT` | NOT NULL，FK → `users.id` |
| `memory_key` | `VARCHAR(100)` | NOT NULL；白名单类别，如 `language_preference` |
| `memory_value` | `TEXT` | NOT NULL；用户**明确确认**的非敏感偏好 |
| `confirmed_at` | `DATETIME(6)` | NOT NULL；用户确认时间（UTC） |
| `expires_at` | `DATETIME(6) NULL` | 过期后不可作为有效偏好读取 |

- 初步唯一约束：`UNIQUE(user_id, memory_key)`，D3 评审是否允许单类型多条/版本化。
- 索引：`(user_id, expires_at)`，便于查询本用户有效记忆。
- 添加、修改、撤销、删除必须由用户明确触发或明确确认；不能从聊天内容自动推定同意。
- 严禁保存密码、Token、OTP、完整银行卡资料、身份证号或其他不必要的金融敏感数据。

### 4.4 `agent_workflow_sessions`（D2 只做结构设计，暂不写 DDL）

| 字段 | 建议类型 | 约束 / 语义 |
|---|---|---|
| `thread_id` | `VARCHAR(128)` | PK，全局唯一；LangGraph 线程标识 |
| `conversation_id` | `CHAR(36)` | NOT NULL；所属会话 |
| `user_id` | `BIGINT` | NOT NULL；所属 Java 认证用户 |
| `workflow_id` | `VARCHAR(64) NULL` | 可选既有业务计划登记 ID |
| `status` | `VARCHAR(32)` | 例如 `RUNNING`、`WAITING_APPROVAL`、`COMPLETED`、`FAILED`、`EXPIRED`（待统一） |
| `created_at` | `DATETIME(6)` | NOT NULL，UTC |
| `expires_at` | `DATETIME(6)` | 有效期，UTC |

- 索引：`(conversation_id, created_at)`、`(user_id, status)`；按需增加 `(user_id, workflow_id)`（**不应默认唯一**）。
- 必须保证 `agent_workflow_sessions.user_id` 与关联 `agent_conversations.user_id` 相同。D3 优先评审**组合外键** `(conversation_id, user_id) → agent_conversations(id, user_id)`，需在父表建立可被引用的组合唯一索引；同时在应用层双重校验。
- 旧 `agent_workflow_runs.workflow_id` 不是全局唯一，不能仅以该单列建跨表 FK。若建立引用需以 `(user_id, workflow_id)` 为键并处理空值及生命周期。
- 此表**不保存** OTP、Bearer Token、Graph State 原文或 Checkpoint bytes；保留一条映射并不等于 Python 重启后可恢复执行。丢失 Checkpoint 时只能提示核实已有银行订单，不能盲目创建重复转账。

## 5. 生命周期、保留与删除策略（D3 需定稿）

1. **会话创建：** Java 根据当前认证用户创建 UUID 和 `ACTIVE` 会话；前端不能传 `userId`。
2. **消息追加：** 服务端验证会话属于当前用户，执行脱敏，再插入消息并更新会话 `updated_at`；敏感内容直接拒绝持久化。
3. **会话归档/关闭：** `DELETE /api/conversations/{id}` 在当前草案中建议定义为**逻辑归档**（`ARCHIVED`，HTTP 204），不是物理删除。前端必须清楚这一点；若产品需要真正删除，需单独定义数据擦除流程。
4. **未完成审批：** 若会话存在未决银行业务，不得因删除聊天就自动视为已拒绝、已取消或已执行；建议先返回 409 并要求显式处理工作流。
5. **消息清理：** 默认不启用 `ON DELETE CASCADE`；用户发起数据删除时按事务与保留政策清理会话数据。银行法定/安全审计记录独立处理，不与聊天级联删除。
6. **长期记忆：** 仅存明确确认的偏好；支持查询、更正、撤销、过期；过期记忆不可再用于提示。
7. **线程过期/重启：** 工作流超期后状态可标记 `EXPIRED`；Python 当前 `InMemorySaver` 不支持重启恢复。可靠 Checkpoint 存储和与会话数据的一致性作为 D3/D4 专题。
8. **时区统一：** MySQL `DATETIME(6)` 不自带时区，Java 写入时统一按 UTC，API 返回带 `Z` 的 ISO 8601 时间；若最终使用本地时间，须双方明确并更改文档与测试。

## 6. 数据一致性与安全验收清单

- [ ] 4 张表的主键、唯一键、外键、索引、清理语义经双方评审。
- [ ] 对所有 `GET/DELETE/POST` 增加 Java 已认证用户归属校验。
- [ ] 前端传入伪造 `userId` 或跨用户会话 ID 时拒绝访问。
- [ ] 历史消息游标分页、排序与长度限制已明确。
- [ ] 浏览器不可伪造 `ASSISTANT` 角色消息。
- [ ] Token、OTP、密码、敏感个人金融内容不得持久化到消息、记忆、Checkpoint 和日志。
- [ ] 不把“删除会话”当作“银行撤销订单”。
- [ ] Python 重启后只可安全查询银行订单，不能因线程信息存在而自动恢复资金操作。
- [ ] 正式 DDL 迁移须在隔离的 MySQL 测试库通过建表、约束和回滚预案验证。

## 7. A/B 当日必须确认的议题

| 议题 | 建议结论 | 评审状态 |
|---|---|---|
| 会话 ID | `conversationId`，UUID，Java 生成 | 待成员 B 确认 |
| Graph 线程 | `threadId`，Python 生成；一会话对应多个线程 | 待成员 B 确认 |
| 用户归属 | Java Bearer Token → `AuthenticatedUser.id()` | 待成员 B 确认 |
| 谁存消息 | Java/MySQL 统一存储；Python 调用受保护的内部写入通道 | 待明确认证协议 |
| 助手角色写入 | 浏览器禁止；内部服务可信身份且带会话归属校验 | 待设计 |
| 工作流审批 | 保留现有 Python / Java 二次授权，不通过消息接口绕过 | 已有约束，待联调 |
| `workflowId` | 可空、用户范围内标识，与 `threadId` 区分 | 待确认 |
| 会话关闭 | 建议归档；待审批业务不自动关闭 | 待确认 |
| Checkpoint 持久化 | 不属于 D2 这四张表直接解决的问题 | D3/D4 决策 |

## 8. D2 交付范围

- 本文档：`docs/v2-memory-data-design.md`
- SQL 草稿：`docs/sql-drafts/12_agent_conversations_DRAFT.sql`（只有前两张表；**禁止在现有测试库执行**）
- API 草案：`docs/v2-memory-api-contract.md`
- D3 执行前需补充：正式 DDL、完整 DTO、鉴权及会话安全测试用例、服务间身份认证方案。
