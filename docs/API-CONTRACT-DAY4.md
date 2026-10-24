# Day 4 Java ↔ Agent API 合同（发给 Java 队友）

**原则：资金变更仅发生在 Java 银行业务服务，Python 不访问银行数据库、不修改余额、不生成授权凭证。**

目前浏览器通过 `Authorization: Bearer <银行登录令牌>` 调用 Python，Python仅转发给 Java。Java 必须对每一个写接口独立验证身份、订单归属与授权状态。Day 4 前端的手工输入 Token 只适用于本地调试，生产版建议改为安全会话/BFF 模式。

## 0. 沿用 Day 3

- `GET /api/demo/balance`、`/transactions`、`/payees`、`/subscriptions`。
- `POST /api/transfers/prepare`，返回至少：

```json
{"orderId":101,"payeeName":"李四","accountMasked":"****5291","amount":"200.00","riskLevel":"YELLOW","status":"PENDING_APPROVAL"}
```

金额使用 JSON **字符串** 和 Java `BigDecimal`。`prepare` 不能转账，只写入待审批订单。

## 1. 黄色确认 / 红色强验证

`POST /api/transfers/{orderId}/authorize`

```json
{"confirmation":true,"otpCode":null,"requestId":"auth-uuid-001"}
```

黄色订单可使用 `otpCode: null`，红色订单必须提供后端独立验证的一次性挑战响应。演示 Mock 暂时使用固定的 `246810` 来模拟 **验证机制**，这不是安全认证，正式 Java 服务必须使用生成的、短时有效、限次数的验证码，绑定用户+订单+金额+收款人。**不能通过提示词、Python 返回文本或客户端标志绕过它。**

成功（HTTP 200）：

```json
{"orderId":101,"payeeName":"李四","accountMasked":"****5291","amount":"200.00","riskLevel":"YELLOW","status":"AUTHORIZED"}
```

常见失败：401 未认证、403 OTP 错误/无权限、409 订单状态不允许授权、429 过多尝试。错误不能被 Python 翻译成成功。

## 2. 执行转账

`POST /api/transfers/{orderId}/execute`

```json
{"requestId":"execute-uuid-001"}
```

后端必须再次校验：

- 请求用户是否拥有付款账户和订单；收款人是否正确；收付账户状态、余额是否可用。
- 是否存在与订单具体内容绑定的授权；红色是否满足后端强验证。
- 当日**已执行 + 在途**订单累计额度是否仍满足原验证等级。风险上升时拒绝并要求加强验证，不能直接执行。
- 订单 `AUTHORIZED` 才能执行；`SUCCESS` 重试返回同一交易结果；其他状态按业务拒绝。
- 单个 MySQL 本地模拟资金账本中，使用数据库事务完成付款扣减、收款增加、流水及订单更新，配合行锁/条件更新和唯一幂等约束防止并发重复扣款。
- 如果未来引入外部支付系统，超时状态标记为 `UNKNOWN` 并查询/对账，不能自动重复执行。

成功响应：

```json
{"orderId":101,"payeeName":"李四","accountMasked":"****5291","amount":"200.00","riskLevel":"YELLOW","status":"SUCCESS","transferId":"TXN-2026-0001","balanceAfter":"12380.50"}
```

## 3. 查询订单

`GET /api/transfers/{orderId}`

查询必须进行身份/订单归属校验。返回与上述一致的订单对象，支持 `PENDING_APPROVAL`、`AUTHORIZED`、`SUCCESS`、`FAILED`、`UNKNOWN`、`CANCELLED` 等状态。

## 4. 取消未执行订单

`POST /api/transfers/{orderId}/cancel`

```json
{"requestId":"cancel-uuid-001"}
```

仅允许 `PENDING_APPROVAL`、`AUTHORIZED` 的订单取消。已成功转账不得取消为未执行。返回 `status: CANCELLED`。

## 5. Python 到 Vue 路由（已实现）

| 操作 | 前端请求路径 | 方法 |
|---|---|---|
| 聊天与识别 | `/api/agent/chat` | POST |
| 补全转账建单 | `/api/agent/transfers/prepare` | POST |
| 订单状态 | `/api/agent/transfers/{id}` | GET |
| 用户批准 | `/api/agent/transfers/{id}/authorize` | POST |
| 用户执行 | `/api/agent/transfers/{id}/execute` | POST |
| 用户取消 | `/api/agent/transfers/{id}/cancel` | POST |

注意：`authorize`、`execute`、`cancel` 这些 Python 网关入口只由用户交互触发，**不作为聊天机器人可调用的 AI Tools 注册**。Java 对实际请求做最终授权，不能仅因为“请求来自 Python”就放行。

## 6. 需双方统一的分歧

- `orderId` 可以是 Java `Long` 或字符串，但接口路由需兼容二者。
- 红色 OTP 是随授权提交还是先调用 `/challenge` 创建认证挑战？本次演示为了十天内联调，先约定授权接口接受 `otpCode`；如果 Java 已设计 `/challenge`，需同步调整前端。
- `balanceAfter` 为可选展示字段，不应因其缺失导致转账状态被认定失败。
- 请采用同一时区定义“当日”，并在并发条件下计算累计转账。Mock 使用服务器本地日期，只用于演示。
