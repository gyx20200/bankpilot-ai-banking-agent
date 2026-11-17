# BankPilot 2.0 — D2 会话与记忆 REST API 契约（评审草案）

> 日期：2026-11-17  
> 负责人：成员 A（Java API）  
> 状态：**DRAFT / 尚未实现 / 待与成员 B 确认**  
> 前提：现有 Java 银行业务接口保持不变；本文件不宣称下述路由已上线。

## 1. 基本契约

- Base：Java Spring Boot `/api`；请求/响应 `application/json; charset=utf-8`。
- 除公开注册、登录接口外，新会话 API 必须携带有效 `Authorization: Bearer <token>`。
- 当前用户由 Java 服务端的 `AuthenticatedUser.id()` 得到；**浏览器请求体不得包含用于指定资源归属的 `userId`**。
- JSON 使用 `camelCase`，SQL 列使用 `snake_case`：`conversationId ↔ agent_conversations.id`，`messageId ↔ agent_messages.id`，`threadId ↔ agent_workflow_sessions.thread_id`。
- 会话 ID 为 UUID 字符串；消息 ID 为整数（JSON number；前端如存在精度风险需协商转字符串）；工作流线程 ID 为字符串，`workflowId` 不等于 `threadId`。
- 时间建议统一 UTC 且带时区的 ISO 8601（示例 `2026-11-17T02:00:00Z`），不得把无时区时间混用于不同服务。
- 不在 API、数据库或日志里保存原始密码、Token、OTP、完整银行卡资料；发送消息需先脱敏。

## 2. D2 拟设计的公开只读/元数据接口

| 方法 | 路由 | 成功响应 | 说明 |
|---|---|---|---|
| `POST` | `/api/conversations` | `201 Created` | 创建当前用户的会话 |
| `GET` | `/api/conversations` | `200 OK` | 查询当前用户会话列表（分页） |
| `GET` | `/api/conversations/{id}` | `200 OK` | 查询本人会话元信息 |
| `GET` | `/api/conversations/{id}/messages` | `200 OK` | 以 `beforeId` 游标分页获取消息 |
| `DELETE` | `/api/conversations/{id}` | `204 No Content` | **建议定义为归档/关闭**，非立即物理删除 |
| `GET` | `/api/conversations/{id}/workflows` | `200 OK` | 查询此会话关联的本人任务线程 |

**安全默认：** 找不到资源或不是本人资源，统一返回 `404`，避免暴露其他用户会话是否存在；若仍有待审批/执行工作流，不允许仅靠会话 DELETE 隐式取消，建议返回 `409 CONFLICT`。

## 3. 创建会话

### Request

```http
POST /api/conversations
Authorization: Bearer <token>
Content-Type: application/json
```

```json
{"title":"我的银行智能助手"}
```

- `title` 可选；为空时默认“新会话”。上限 100 字符；去除控制字符、敏感标识与超长输入。
- 请求中不能有 `userId`、`status`、`conversationId` 等服务端拥有的字段；建议未知字段返回 400。

### Response — 201

```json
{
  "conversationId":"550e8400-e29b-41d4-a716-446655440000",
  "title":"我的银行智能助手",
  "status":"ACTIVE",
  "createdAt":"2026-11-17T02:00:00Z",
  "updatedAt":"2026-11-17T02:00:00Z"
}
```

响应 UUID 与时间均为示例数据。

## 4. 查询会话列表与详情

### GET `/api/conversations?limit=20&beforeUpdatedAt=...`（分页方案待定）

```json
{
  "items":[
    {"conversationId":"550e8400-e29b-41d4-a716-446655440000",
     "title":"我的银行智能助手", "status":"ACTIVE",
     "createdAt":"2026-11-17T02:00:00Z", "updatedAt":"2026-11-17T02:01:00Z"}
  ],
  "nextCursor":null
}
```

- 只返回认证用户自己的会话；默认仅 ACTIVE，归档会话是否包含在结果中由双方协商。
- `limit` 建议默认 20、最大 100。可使用不透明 `cursor`，按 `(updated_at, id)` 保证稳定顺序；不能只依赖同秒时间戳避免遗漏。

### GET `/api/conversations/{id}` — 200

返回与列表单项相同的会话元信息。其他用户的 ID 和不存在的 ID 一律返回 404。

## 5. 读取历史消息

### Request

```http
GET /api/conversations/550e8400-e29b-41d4-a716-446655440000/messages?limit=20
Authorization: Bearer <token>
```

也支持 `beforeId=<messageId>` 加载更早消息；`limit` 默认 20，最大 100。

### Response — 200

```json
{
  "conversationId":"550e8400-e29b-41d4-a716-446655440000",
  "items":[
    {"messageId":1,"role":"USER","content":"分析2026年10月的消费","createdAt":"2026-11-17T02:01:00Z"},
    {"messageId":2,"role":"ASSISTANT","content":"已完成10月收支分析。","createdAt":"2026-11-17T02:01:05Z"}
  ],
  "nextBeforeId":null
}
```

- `items` 按消息 ID 升序展示；`beforeId` 读取更早消息的区间。服务端必须先按会话归属筛选，再查询消息。
- 无法从用户请求直接指定角色为 `ASSISTANT`；助手消息只能由可信内部服务写入。

## 6. 会话关闭和工作流关系

### DELETE `/api/conversations/{id}`

- 建议语义：当前用户**归档**会话（`status=ARCHIVED`），HTTP 204；不是对银行订单的删除/撤销，也不是隐私数据彻底擦除。
- 若存在 `WAITING_APPROVAL`、`RUNNING` 等未决线程，建议返回 409 并说明需先在原工作流处理订单；不能隐式授权、拒绝或再次执行。
- 如以后需要真实数据删除，应另行设计删除请求、留存期与独立银行审计记录的处理策略。

### GET `/api/conversations/{id}/workflows` — 200

```json
{
  "conversationId":"550e8400-e29b-41d4-a716-446655440000",
  "items":[
    {"threadId":"1d776fb4-f25a-49c2-ae10-c3bc659920ab",
     "workflowId":null,"status":"WAITING_APPROVAL",
     "createdAt":"2026-11-17T02:01:06Z",
     "expiresAt":"2026-11-17T02:31:06Z"}
  ]
}
```

- 一个 `conversationId` 可以映射多个 `threadId`。
- `workflowId` 仅表示可选的旧业务计划 ID，实际查询必须同时验证 `userId`。
- 映射表只描述关联，不代表持久化了 LangGraph Checkpoint；若 Python 重启丢失 Checkpoint，不得自动重放资金类操作。

## 7. 消息写入：D2 的安全决策（暂不开放公共接口）

**今天不设计可被浏览器随意调用的 `POST /messages`（含任意 `role`）接口。** 若 D3 需要写入：

- 浏览器用户消息：只能提交 `content`，后端依据认证身份强制写 `USER`，不能指定 `ASSISTANT`。
- Agent 助手消息：由 FastAPI 经**独立验证的服务间身份**写入 Java 受保护内部 API；Java 校验来源权限、关联会话归属、内容脱敏/长度、幂等性及审计。
- 不允许“只要带有用户 Bearer Token 就能写任意角色”，避免用户伪造模型回答。
- 服务间认证可用 mTLS 或单独的短期服务凭据；D3 明确部署与密钥轮换，不把服务密钥提交 Git。
- OTP、Bearer Token、密码、完整银行卡号等只可存在短期执行所需受控上下文，**不得写入**消息、长期记忆、日志或 Checkpoint。

## 8. 长期记忆：D2 仅定约束，不开放 CRUD

`agent_user_memories` 用于用户**明确确认**的长期偏好，D2 不暴露创建/修改/读取 API。D3 应设计：用户同意记录、白名单 `memoryKey`、撤销/删除、过期、不含敏感金融数据，以及用户归属校验。聊天内容不得默认转换为长期记忆。

## 9. 错误响应契约（建议，需对齐现有项目错误结构）

| HTTP | `errorCode` | 场景 |
|---|---|---|
| 400 | `INVALID_REQUEST` | 无效 UUID、参数越界、未知字段 |
| 401 | `UNAUTHORIZED` | Bearer Token 缺失/失效 |
| 404 | `CONVERSATION_NOT_FOUND` | 会话不存在或不属于当前用户 |
| 409 | `PENDING_WORKFLOW` | 会话仍有待处理工作流，不能关闭 |
| 413 | `CONTENT_TOO_LARGE` | 消息过长、超出允许大小 |
| 422 | `SENSITIVE_CONTENT` | 内容不满足脱敏/合规要求（是否使用 400 待统一） |

建议响应结构：

```json
{"errorCode":"CONVERSATION_NOT_FOUND","message":"会话不存在或无权访问","traceId":"d2-example-trace"}
```

注意：这是**拟新增接口的推荐格式**，现有 BankPilot 错误体未全部统一；最终应复用项目现有异常处理规范并与成员 B 协调，不能假设已上线。

## 10. D3 前的接口安全测试（建议）

| 用例 | 预期 |
|---|---|
| 不带 Token 创建或读取会话 | 401 |
| 用户 B 访问用户 A 的 `conversationId` | 404（或团队统一的隐蔽性策略） |
| 前端伪造 `userId` | 忽略/拒绝，不能越权 |
| 前端提交 `role=ASSISTANT` | 不接受 |
| 访问归档会话的消息 | 依归档策略，服务端统一限制 |
| 按 `beforeId` 分页 | 结果不重复、不越界，稳定排序 |
| 会话含待审批线程时关闭 | 409，不改变银行订单状态 |
| FastAPI 重启丢失 Checkpoint | 不盲目重建旧订单或重复执行 |
| 输入包含 OTP/Token | 不写入消息、数据库审计明文或应用日志 |
| 跨用户 `threadId` | 拒绝，Python 与 Java 均校验归属 |

## 11. 成员 A 给成员 B 的交接摘要

1. `conversationId`：Java 生成的 UUID 字符串；`threadId`：Python Graph 线程字符串；一会话多线程。
2. `userId`：Java 验证 Bearer Token 后取得；前端不能指定会话归属。
3. D2 仅定义六个公开会话元数据/查询接口；消息写入与长期记忆 API 暂不对外开放。
4. Python 需在创建工作流前检查会话归属；存储 `threadId → conversationId → userId` 时必须防止跨租户关联。
5. Graph Checkpoint 持久化单独设计；当前 `InMemorySaver` 无重启恢复能力。
6. 不改变现有转账、AA、订阅与预约审批接口；D3/D4 再逐步集成。
7. 请确认 JSON 字段名：`conversationId`、`messageId`、`threadId`、`role`、`content`、`createdAt`、`status`。

**评审状态：待成员 B 确认后定稿。**
