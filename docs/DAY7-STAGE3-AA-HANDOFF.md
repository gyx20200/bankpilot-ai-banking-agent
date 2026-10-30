# BankPilot Day 7 · 阶段 3 AA 收款：Agent/Vue 与 Java 接口交接

> 适用基线：已应用 Day 7 阶段 1（认证 + 模拟后端 + UI）和阶段 2（姓名/手机号/备注转账）。阶段 3 只新增 AA 能力，原有转账审批与账务不变。
>
> 本文中的 `/api/aa/**` 是 **Day 7 建议 Java 接口契约**，当前 Java 尚未实现；`mock_day7_backend.py` 只用于本地模拟，数据在内存中，重启清空。

## 1. 业务规则（双方必须一致）

1. 注册用户拥有独立 Token 与银行账户；每次查询/写操作必须由 Java 验证 Token，禁止浏览器和 LLM 指定付款用户 ID。
2. 接受一次完整自然语言指令，不依赖聊天多轮上下文：`我和张三、李四聚餐300元，三个人AA`；或 `向张三和李四每人收100元`。缺少金额/人员/分摊模式时，拒绝创建并要求用户重新输入完整句子。
3. 模式 `total_with_self`：总费用包括发起人的份额，付款人只有其他参与者。300元三人AA → 各100元，待收200元。金额按人民币**分**处理尾差，全部份额之和必须等于总额。
4. 模式 `per_person`：传入的 `amount` 表示每个指定付款人应付金额，不给发起人分配份额。可用银行已注册手机号作为唯一身份标识；重名无法唯一识别时必须拒绝，并要求提供完整且唯一的身份信息，不能由模型猜测。
5. Agent 先请求银行创建 `DRAFT`，发起人核对明细并点击确认后才 `PUBLISHED`；草稿阶段其他人的 inbox 不可见，不能扣款。拒绝草稿只取消请求。
6. 付款用户登录自己的账户查看 inbox，选择 **付款** 或 **拒绝**。付款需先建立与该 AA item 关联的银行转账订单，再走 **付款人本人** 的 YELLOW 确认／RED OTP。发起人无法替他授权。
7. **只有银行执行转账 SUCCESS，且付款人扣款、发起人入账与双方流水一致时，AA item 才能置 PAID。** 一个 item 最多成功付款一次，不能重复扣款。
8. 无 AA 请求自动过期；付款人可独立处理，拒绝一人不影响其他人。发起人查询 outgoing 时可看到 `receivedAmount` 与各人状态。无需 WebSocket，手动刷新即可。
9. 如果付款订单已建单但页面刷新，必须根据 itemId 读取原转账订单，不新建订单。网络状态不明时先查询原订单，不盲目重试。
10. 所有端点记录发起用户/操作用户、原 `requestId`、AA 单/明细、转账订单、资金流水及审计，禁止记录明文密码和 OTP。

## 2. Java 必须实现的接口

统一前缀 `http://<java-host>/api/aa`，所有接口都要求 `Authorization: Bearer <Java Token>`，只有当前登录用户能访问有权限的记录。传递金额使用精确两位的十进制字符串。

| 请求 | 作用 | 权限 | 核心字段 |
|---|---|---|---|
| `POST /prepare` | 创建待确认草稿 | 发起人 | `participants: string[]`, `amount`, `splitMode`, `reason`, `requestId` |
| `GET /{collectionId}` | 查询本人发起的收款单及进度 | 发起人 | path id |
| `POST /{collectionId}/publish` | 确认并正式发布 | 发起人 | `requestId` |
| `POST /{collectionId}/cancel-draft` | 拒绝未发布草稿 | 发起人 | `requestId` |
| `GET /outgoing` | 查看我已发布的收款单 | 发起人 | — |
| `GET /inbox` | 查看发给我的付款请求 | 付款人 | — |
| `POST /items/{itemId}/payment/prepare` | 创建/找回关联的实际转账订单 | 对应付款人 | `requestId` |
| `GET /items/{itemId}/payment` | 恢复/核对原银行转账订单 | 对应付款人 | path id |
| `POST /items/{itemId}/otp/request` | RED 付款申请 OTP | 对应付款人 | — |
| `POST /items/{itemId}/payment/confirm` | 本人明确确认；必要时 OTP；调用统一转账执行 | 对应付款人 | `requestId`, `confirmed:true`, `otpCode?` |
| `POST /items/{itemId}/decline` | 拒绝未付款请求；若已有待审订单则取消原订单 | 对应付款人 | `requestId` |

**Java 实现提示：** `payment/prepare` 应通过付款人自己的收款人绑定机制获取发起人的可信账户，再创建 `transfer_orders`。不要把全局 userId 当成 Day 6 旧 `payeeId`。`payment/confirm` 必须调用统一资金执行服务，确保 `transfer_orders`、双方账户余额、交易流水与 AA item 状态具有同一事务保证和幂等控制；若状态未知，需通过原订单对账，而不是重新创建转账。

## 3. 完整 JSON 示例

### 创建草稿

`POST /api/aa/prepare`

```json
{"participants":["张三","李四"],"amount":"300.00","splitMode":"total_with_self","reason":"聚餐","requestId":"aa-prepare-unique-001"}
```

返回（金额与 ID 仅为示例）：

```json
{
  "collectionId":"AA-001", "initiatorId":1, "initiatorName":"张小明", "status":"DRAFT",
  "splitMode":"total_with_self", "reason":"聚餐",
  "totalAmount":"300.00", "selfAmount":"100.00", "requestedAmount":"200.00", "receivedAmount":"0.00",
  "items":[
    {"itemId":"AA-ITEM-001","collectionId":"AA-001","payerId":2,"payerName":"张三","amount":"100.00","status":"PENDING","transferOrderId":null},
    {"itemId":"AA-ITEM-002","collectionId":"AA-001","payerId":3,"payerName":"李四","amount":"100.00","status":"PENDING","transferOrderId":null}
  ]
}
```

`POST /api/aa/AA-001/publish` 请求 `{"requestId":"aa-publish-unique-001"}`，返回同结构，`status` 变 `PUBLISHED`。只有此后付款人 inbox 才看得到请求。

### 付款人登录，查询 inbox

`GET /api/aa/inbox`

```json
[{"itemId":"AA-ITEM-001","collectionId":"AA-001","payerId":2,"payerName":"张三","amount":"100.00","status":"PENDING","transferOrderId":null,"initiatorName":"张小明","reason":"聚餐"}]
```

`POST /api/aa/items/AA-ITEM-001/payment/prepare` 返回**现有转账订单形态**：

```json
{"orderId":"TF-001","payeeName":"张小明","accountMasked":"****6601","amount":"100.00","remark":"AA:聚餐","riskLevel":"YELLOW","status":"PENDING_APPROVAL"}
```

RED 时另外调用 `POST /api/aa/items/AA-ITEM-001/otp/request`，返回示例 `{"orderId":"TF-001","expiresInSeconds":120,"status":"OTP_REQUESTED"}`。用户本人在卡片输入 OTP 后调用：

`POST /api/aa/items/AA-ITEM-001/payment/confirm`

```json
{"requestId":"aa-pay-unique-001","confirmed":true,"otpCode":null}
```

成功返回关联 item，`status=PAID`、`transferOrderId=TF-001`。发起人刷新 outgoing，`receivedAmount` 增加 100元，张三 item 状态变为 `PAID`。没有真实转账成功绝不能返回 `PAID`。

### 状态定义

- collection：`DRAFT`（不公开）、`PUBLISHED`、`PARTIAL`、`COMPLETED`、`CANCELLED`（仅未发布草稿）。
- item：`PENDING`、`PAYING`、`PAID`、`DECLINED`、`FAILED`。
- 银行转账 order：继续使用 Day 6 的 `PENDING_APPROVAL`、`AUTHORIZED`、`SUCCESS`、`FAILED` 等状态和风险分级，**不要把 AA 的业务状态当成付款授权**。

## 4. 你的 Agent/Vue 侧新增改动

| 文件 | 责任 |
|---|---|
| `app/graph/task_planner.py` | DeepSeek 新 AA 任务参数 `aa_participants`, `aa_mode`, `amount`, `aa_reason`；一条指令验证完整性 |
| `app/graph/task_registry.py` | 注册 `create_aa_collection` 敏感写任务，继续限制一次最多一项独立写业务 |
| `app/graph/dynamic_cancellation_workflow.py` | AA 准备草稿 → LangGraph interrupt → 发起人审批 → 发布/撤销及银行核实 |
| `app/workflow_api.py` | 识别 AA 等待审批，按 Java userId 校验后恢复，银行状态对账 |
| `app/banking_client.py` | 与 Java 约定的 AA HTTP 接口、响应验证和认证透传 |
| `app/aa_api.py`（新增） | 当前登录用户查询本人 AA 列表及本人付款/拒绝的受控代理 |
| `main.py` | 注册 AA 路由 |
| `frontend/src/App.vue` | 接入 AA 入口与发起确认状态 |
| `frontend/src/components/DynamicWorkflowCard.vue` | 展示待确认 AA 明细与发布/取消草稿按钮 |
| `frontend/src/components/AaCenter.vue`（新增） | 本人付款请求、RED OTP、拒绝、进度列表和刷新 |
| `mock_day7_backend.py` | 本地仅内存 AA 单、发起人/付款人归属、双边资金与状态校验 |

## 5. Windows 本地运行（使用模拟银行，不需要等 Java）

修改 `agent-service/.env`，在原阶段1 mock配置上**增加**：

```ini
BANK_AA_API_BASE=http://127.0.0.1:18080/api/aa
```

三个终端分别运行：

```powershell
# 终端1，进入 agent-service
$env:BANKPILOT_STAGE1_MOCK="1"
python -m uvicorn mock_day7_backend:app --host 127.0.0.1 --port 18080

# 终端2，进入 agent-service；请保留原 DeepSeek 配置
python -m uvicorn main:app --host 127.0.0.1 --port 8000

# 终端3，进入 frontend
npm run dev
```

**注意：** 即使模拟银行可运行，聊天中的 AA Planner 仍需 DeepSeek API 配置。只是注册登录、inbox 及模拟后端接口不依赖大模型。

## 6. 手工测试（必须实际在前端验证）

1. 注册“张小明”“张三”“李四”3 个不同用户，每人初始 10000 元；使用张小明登录。
2. 发完整指令 `我和张三、李四聚餐300元，三个人AA，帮我收款`，Agent 应生成草稿并暂停；此时余额不变，其他账号看不到。
3. 张小明点击确认发布；退出并使用张三登录，展开“AA 收付款”看到100元待付款。
4. 张三点击准备付款、勾选明确确认并支付；银行实际转账成功，张三余额 9900 元；重新登录张小明后余额 10100 元，AA 列表张三“已支付”。
5. 使用李四登录，拒绝100元请求；李四余额仍 10000 元。张小明刷新看到张三已支付、李四已拒绝，实收100元。
6. 用另一笔AA测试超过1000元的付款，必须由该付款人申请OTP并通过后付款。**模拟 OTP `246810` 仅限本地 Mock，不要放进 Java 正式实现。**
7. 重复支付已完成的 item，应拒绝重复扣款；刷新/重登录后原 PAYING 订单可恢复，不允许另建新订单。
8. 发不完整指令 `我和张三李四聚餐帮我AA`，应提示重新提交完整指令，不要求用户在下一轮只回复金额。
9. 回归余额、流水、普通转账、订阅取消、多任务审批，确保未被破坏。

## 7. 已知限制与迁移边界

- Mock 进程内存无持久化，重启后所有测试用户及 AA 单消失。Java 正式环境必须由 MySQL 持久化。
- AA 不支持自动过期、多轮聊天补全、分摊修改、WebSocket 实时通知、跨行收款。
- 当前环境缺少可运行的 LangGraph / Linux Rollup，无法在这里实际完成端到端 LangGraph + Vue Vite 完整打包。这里通过可运行的 pytest 业务测试、Python 编译及 Vue 单文件组件编译；你本地必须实际运行完整聊天审批和构建。
- 交付补丁**只能**用于已应用阶段 1+UI+模拟后端+阶段 2 的源码，切勿在未经核对的其他版本上强行覆盖。
