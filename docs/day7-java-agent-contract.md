# BankPilot Day 7 — Java ↔ Agent 最终接口契约

**基线：** 用户上传的 `bankpilot-ai-banking-agent-main (1).zip`，以 `agent-service/app/banking_client.py` 和 `mock_day7_backend.py` 为准。**仅本地模拟资金。**

所有受保护接口均要求 Java 验证 `Authorization: Bearer <token>` 并由 Token 推导当前用户；若未登录返回 HTTP 401；非本人资源返回 404/403；业务状态冲突 HTTP 409；敏感业务需 `requestId` 幂等。

## A 认证

| 方法 | URL | 请求 | 关键返回 |
|---|---|---|---|
| POST | `/api/auth/register` | `username,password,fullName,phone` | `{"status":"REGISTERED","userId":3}`（201） |
| POST | `/api/auth/login` | `username,password` | `token,tokenType:"Bearer",expiresInSeconds:int,displayName` |
| GET | `/api/auth/me` | Bearer | `userId:int,username,displayName,phoneMasked` |
| POST | `/api/auth/logout` | Bearer | `{"status":"logged_out"}`，Token 失效 |

新用户注册在事务中生成 `users` / `user_credentials` / `accounts`，模拟余额 `10000.00`，不自动登录。旧用户可选择在测试库中执行环境变量控制的 bootstrap，绝不在代码中放演示密码。

## B 收款人和原转账

| 方法 | URL | 请求与响应 |
|---|---|---|
| GET | `/api/transfers/recipients/search?name=张三` | 返回数组 `[{"recipientId":3,"payeeName":"张三","accountMasked":"****1234"}]` |
| GET | `/api/transfers/recipients/search?phone=13800138001` | 完整手机号精确匹配，数组（0/1） |
| POST | `/api/transfers/recipients/confirm` | `{"recipientId":3}` → `{"id":19,"payeeName":"张三","payeeAccountMasked":"****1234"}` (`id` 即旧 payeeId) |
| POST | `/api/transfers/prepare` | `payeeId,amount,requestId,remark` → `orderId,riskLevel,status,remark,...` |
| GET | `/api/transfers/{id}` | 原订单视图，包含 `remark` |

后续保留 Day 6 订单 `otp/request`、`authorize`、`execute`、`cancel`。日累计超过 ¥1000 的真实转账必须 RED OTP。

## C AA（全部 `/api/aa`）

| 方法 | URL | 用途/字段 |
|---|---|---|
| POST | `/prepare` | `participants:["张三","李四"],amount:"300.00",splitMode:"total_with_self"或"per_person",reason:"聚餐",requestId` → `DRAFT` |
| GET | `/{collectionId}` | 仅发起人查询主单（含 items） |
| POST | `/{collectionId}/publish` | `requestId` → `PUBLISHED`，只有此后付款人可见 |
| POST | `/{collectionId}/cancel-draft` | `requestId` → `CANCELLED`，仅尚未发布的草稿 |
| GET | `/outgoing` | 当前发起人可见非草稿主单的数组 |
| GET | `/inbox` | 仅当前付款人的 AA 明细数组 |
| POST | `/items/{itemId}/payment/prepare` | `requestId` → **原转账订单视图** `orderId,status:"PENDING_APPROVAL",riskLevel` |
| GET | `/items/{itemId}/payment` | 查询已绑定的真实银行转账订单 |
| POST | `/items/{itemId}/otp/request` | 原 RED 转账 OTP |
| POST | `/items/{itemId}/payment/confirm` | `requestId,confirmed:true,otpCode?`；仅真实转账成功返回 `status:"PAID",transferOrderId` |
| POST | `/items/{itemId}/decline` | `requestId` → `status:"DECLINED"`，本人余额不变 |

**AA 主单：** `collectionId` **字符串**、`initiatorId:int`、`initiatorName`、`status:DRAFT/PUBLISHED/PARTIAL/COMPLETED/CANCELLED`、`splitMode`、`reason`、`totalAmount,selfAmount,requestedAmount,receivedAmount`（**金额字符串，精确两位小数**）、`items`。`items` 中 `itemId` **字符串**、`payerId:int`、`payerName`、`amount` 字符串、`status:PENDING/PAYING/PAID/DECLINED/FAILED`、`transferOrderId`（可为 null）。

只有原 `transfer_orders.status=SUCCESS` 且双方对应流水存在后才能 PAID，所有资金操作必须复用 Day 6 的转账事务。

## D 单次预约（全部 `/api/scheduled-transfers`）

| 方法 | URL | 用途/字段 |
|---|---|---|
| POST | `/prepare` | `payeeId,amount:"50.00",executeAt:"2026-11-01T15:00:00+08:00",remark,requestId` |
| GET | `/mine` | 当前用户的预约数组 |
| GET | `/{scheduleId}` | 当前用户预约详情 |
| POST | `/{scheduleId}/otp/request` | **所有金额都需要 OTP**；返回 `scheduleId` 字符串、`expiresInSeconds` 整数 |
| POST | `/{scheduleId}/authorize` | `requestId,confirmed:true,otpCode:"123456"` → `SCHEDULED` |
| POST | `/{scheduleId}/cancel` | `requestId` → `CANCELLED`，仅未执行预约 |

返回至少 `scheduleId` **字符串**、`payeeName,accountMasked,amount`（字符串）、`remark,executeAt`（ISO +08:00）、`status`、`orderId`（成功后关联真实订单号）、`failureReason`。

**最终业务规则：** 无论金额多少均要求预约 OTP；专属预授权绑定具体用户、双边账户、金额、时间、备注，OTP 本身两分钟过期，但**验证后的专属预授权无固定时间到期日**；预约无业务最长天数；Java 持久化等待；只有到期后 60 秒内且授权有效才执行，超窗 `MISSED` 不补扣；余额不足 `FAILED` 不自动重试；异常不明 `UNKNOWN` 不自动重试；重复调度不能重复扣款。

测试环境可在**仅本机、显式开启调试**时使用 `/api/scheduled-transfers/{id}/demo-otp` 读取模拟 OTP；非真实二次认证渠道，不可用于生产。

## 跨端注意

1. 队友需设置 `BANK_API_MODE=java`、`BANK_AUTH_API_BASE`、`BANK_TRANSFER_API_BASE`、`BANK_AA_API_BASE`、`BANK_SCHEDULE_API_BASE` 为 `http://127.0.0.1:8080/api/...`，否则可能 502 连接到 Mock。
2. `Agent /workflow_api.py` 按 Java `/me` 验证的 `userId` 绑定线程；会话仍可能随 Python 进程重启消失，不能将旧审批对象交给其他用户。
3. Java 不接受 LLM 提供的发起人/付款人 userId。`recipientId` 不等于 `payeeId`。
4. AA 付款与定时预约状态不是资金成功的证明，最终以 `transfer_orders`、`transactions` 和两侧 `accounts.balance` 为准。
5. 当前仓库的 Java 工程仍属于本地模拟银行，新增 OTP 演示渠道与内存登录会话不是生产可用身份体系。
