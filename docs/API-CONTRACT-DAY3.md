# Day 3 Agent ↔ Java 接口合同（必须发给 Java 队友）

> 使用 Day 2 已跑通的账户和 payees 数据。所有金额采用十进制**字符串**（`BigDecimal`）；系统只允许**建单**，不得在本接口中扣减账户余额。Java 是最终权限/身份/事务控制方。

## 1. 沿用的只读接口

- `GET /api/demo/balance`
- `GET /api/demo/transactions`
- `GET /api/demo/payees`
- `GET /api/demo/subscriptions`

Python 默认向上述接口转发 `Authorization: Bearer <登录令牌>`（如浏览器提供了令牌）。Day 3 开始，正式银行 API **必须校验用户会话和数据归属**，不要继续依靠 Day 1 的固定用户 `user_id=1` 做真实业务鉴权。

**收款人数组必须采用以下结构：**

```json
[{"id":1,"payeeName":"李四","payeeAccountMasked":"****5291"}]
```

`id` 是数字，绝对不要将完整收款账户传给 Agent。Java 必须独立验证 payeeId 归属当前已登录用户。

## 2. 新增 `POST /api/transfers/prepare`

请求头：

```http
Authorization: Bearer <Java 银行后端签发、有效的用户登录令牌>
Content-Type: application/json
```

请求体：

```json
{
  "payeeId": 1,
  "amount": "200.00",
  "requestId": "d9cc6a2d-51fb-4a92-a88b-9e9ae57a7909",
  "remark": "AA晚餐"
}
```

说明：`requestId` 来自浏览器并传递到 Java，但 Java 不可仅凭它放行；应为 `(authenticated_user_id, request_id)` 设置唯一约束，用来防止重复建单。

成功响应 HTTP 200 / 201：

```json
{
  "orderId": 101,
  "payeeName": "李四",
  "accountMasked": "****5291",
  "amount": "200.00",
  "riskLevel": "YELLOW",
  "status": "PENDING_APPROVAL"
}
```

必须包含六个字段：`orderId`、`payeeName`、`accountMasked`、`amount`、`riskLevel`、`status`。

`riskLevel` 只允许 `YELLOW` 或 `RED`；`status` 在 Day 3 只允许 `PENDING_APPROVAL`。对于转账，不允许因为大模型提示而返回 `SUCCESS`。如风控拒绝，则返回明确 4xx 错误，不应创建订单。

Java 端必须处理：

1. **认证**：Spring Security 验证有效用户身份；Python 转发的 Token 不等于信任 Python 自身。
2. **资源归属**：确认付款账户为当前用户，`payeeId` 存在且属于当前用户的收款人列表。
3. **金额校验**：`BigDecimal` 解析及两位小数、金额正数、余额/账户状态校验；并发累计额度判定应以 Java 的事务状态为准。
4. **风险分级**：计算当日已执行和未完成的在途转账累计，≤1000 为黄色、>1000 为红色；并发场景需要在执行前复核。
5. **幂等性**：相同用户 + requestId + 相同参数，返回同一订单；相同键但参数不同，返回 409。
6. **无资金变更**：`prepare` 只能写 `transfer_orders`；不能更新 `accounts.balance`、创建成功的资金流水，不能直接执行转账。
7. **敏感信息**：响应仅包含脱敏账户，不返回账户完整卡号、短信验证码、身份令牌。

建议错误码：

| 状态 | 含义 |
|---|---|
| 400 | 参数错误或不允许的收款人 |
| 401 | 未登录或 Token 失效 |
| 403 | 已登录但无操作权限 |
| 404 | 收款人不存在 |
| 409 | 重复键与不一致订单参数冲突 |
| 422 | 金额不符合业务规则 |
| 429 | 频率限制 |
| 5xx | 后端暂不可用 |

`400/401/403` 等拒绝是**正常安全行为**，不应该让 Python 因为后端拒绝而捏造成功结果。

## 3. 前端 ↔ Python 接口

保留 Day 2：

`POST /api/agent/chat`

```json
{"message":"给李四转200元","requestId":"d9cc6a2d-51fb-4a92-a88b-9e9ae57a7909"}
```

如果已登录且已存在唯一收款人，Python 调用 Java `/api/transfers/prepare`，返回：

```json
{
  "reply":"已创建待确认转账订单。尚未扣款，请查看下方订单预览。",
  "intent":"transfer",
  "action":"prepared",
  "data":{
    "orderId":101,
    "payeeName":"李四",
    "accountMasked":"****5291",
    "amount":"200.00",
    "riskLevel":"YELLOW",
    "status":"PENDING_APPROVAL"
  },
  "source":"bank-api",
  "requestId":"d9cc6a2d-51fb-4a92-a88b-9e9ae57a7909"
}
```

如果金额缺失、收款人不匹配、重名或未提供 Token，则返回 `action: "needs_input"` 和 `data.payees` 列表。Vue 展示受限收款人下拉框和金额输入框；确认要建单后，请求：

`POST /api/agent/transfers/prepare`

```json
{
  "payeeId":1,
  "amount":"200.00",
  "requestId":"d9cc6a2d-51fb-4a92-a88b-9e9ae57a7909",
  "remark":"AA晚餐"
}
```

前端随上述请求转发 `Authorization: Bearer <Java 登录令牌>` 给 Python；Python **只转发**给 Java，不自己给它签名或判断是否有效。

> 注意：本地演示的 Bearer Token 输入框不属于生产登录系统，不存 localStorage。Day 3 的 Java API 没有 OAuth/JWT 前，请先运行 Mock 演示，不要用固定公共令牌假装实现了真正身份认证。

## 4. Day 4 才实现

- `POST /api/transfers/{id}/authorize` 与红色 OTP 强验证
- `POST /api/transfers/{id}/execute` 与数据库事务
- 前端黄色确认 / 红色验证弹框
- 超时后查询订单、幂等执行、审计详情

**Day 3 的 Python 和本地 Mock 都没有 `/execute` 端点。**
