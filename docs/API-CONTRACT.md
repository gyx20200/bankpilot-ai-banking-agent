# 与 Java 队友约定的 Day 2 API 合同

> 注意：均为 **本地只读 Demo** 接口，继续沿用 Day 1 固定演示账户，仅能在本机验证；从 Day 3 起加入正式身份认证与资源归属校验。

地址默认为 `http://127.0.0.1:8080/api/demo`。所有接口均应返回 `200 OK` 和 JSON。找不到数据时，列表返回 `[]`，不能返回虚构流水；无可用账户时应返回恰当错误码。

## 1. GET /balance

```json
{"userName":"张小明","accountNoMasked":"****6688","balance":"12580.50","currency":"CNY"}
```

## 2. GET /transactions

```json
[
 {"id":2,"direction":"OUT","amount":"35.00","category":"餐饮","merchantName":"美团外卖","description":"午餐","occurredAt":"2026-10-05 12:00:00"},
 {"id":1,"direction":"IN","amount":"8000.00","category":"工资","merchantName":"公司","description":"十月工资","occurredAt":"2026-10-03 09:00:00"}
]
```

- `direction`: `IN` 入账、`OUT` 支出。
- `amount`: 金额为正数，建议 Java BigDecimal 或两位小数字符串；不由 LLM 加减。
- 默认最多返回 100 条、按 `occurredAt` 倒序；后续引入用户身份、分页和时间范围。

## 3. GET /payees

```json
[{"id":1,"payeeName":"李四","payeeAccountMasked":"****5291"}]
```

- 仅返回脱敏账户信息，不将完整银行卡号发送给模型或页面。

## 4. GET /subscriptions

```json
[{"id":1,"merchantName":"视频会员","amount":"25.00","billingCycle":"MONTHLY","status":"ACTIVE","nextPayDate":"2026-11-08"}]
```

- 状态示例：`ACTIVE` / `CANCELLED`。本阶段只有查询权限。
- 银行代扣协议状态与商户订阅合同状态不是同一概念。

## Python -> 前端

`POST /api/agent/chat` 请求：

```json
{"message":"我的余额是多少"}
```

响应（`data` 的结构由 `intent` 决定）：

```json
{
 "reply":"张小明，您的模拟账户 ****6688 当前余额为 ¥12,580.50。",
 "intent":"balance",
 "source":"bank-api",
 "requestId":"示例请求编号",
 "data":{"userName":"张小明","accountNoMasked":"****6688","balance":"12580.50","currency":"CNY"}
}
```

Agent 服务调用 Java 失败时返回 HTTP `502`（不是模型随意编写的“查询成功”）。

## Day 3 起必须更改

- 当前基于固定 `user_id=1` 的演示 API 不适用于可操作转账的正式系统。
- 登录信息经 Spring Security 验证，跨服务以安全凭证或受信任服务身份传递，不从 LLM 文字提取用户 ID。
- 新增转账工具时仅向 Agent 提供 `prepare_transfer` 创建订单，不授予不经审批的写权限。
