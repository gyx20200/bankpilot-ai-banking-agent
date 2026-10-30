# BankPilot Day 7 — 阶段 2 Agent / Vue 交付说明

> 目标：在阶段 1（多用户登录 + UI 美化 + 独立模拟银行）基线上，增加按注册姓名、按手机号和带备注的普通转账。**不改变 Day 6 的转账审批、OTP、取消、资金执行安全逻辑。**

## 1. 开发基线和应用范围

- 工作分支：`feature/day7-agent`。
- **必须先应用**：Day 7 阶段 1 完整开发补丁、登录注册 UI 视觉优化补丁、阶段 1 独立模拟后端补丁；本阶段补丁以三者都已应用的源码为基础。
- 前端依然保持 Vue → FastAPI → 银行服务的调用路径。
- 真实 Java 尚未实现阶段 2 收款人搜索/绑定接口；可先使用 `mock_day7_backend.py` 测试。正式 Java 联调必须按下节接口契约实现。
- 文件中不包含任何凭据或 `.env`；不要将本地 `.env` 提交到 Git。

## 2. 功能与安全流转

### 姓名转账

1. 用户发出“给张三转200元”。DeepSeek 输出 `transfer_prepare`，包含 `payee_name="张三"`、`amount="200"`。
2. Planner 校验姓名确实在用户原文中，金额出现于转账动作后，不接受模型虚构账户 ID。
3. Agent 使用当前登录 Token 调用银行收款人目录。目录搜索范围为**所有已注册用户**（不只是当前用户保存的常用收款人）。
4. 若找不到则结束；若只有一名则继续；若出现同名多人，LangGraph 先暂停并返回 `WAITING_RECIPIENT_SELECTION` 和银行候选脱敏资料，此时**没有创建资金订单**。
5. 用户在 Vue 候选卡中选择银行 `recipientId`，FastAPI 对当前已认证 `userId`、工作流归属、原候选集合再次验证，再调用 Java 收款人确认/绑定接口，得到当前用户可用的 `payeeId`。
6. Java 返回的 `payeeName`、脱敏账户必须与已选择的候选完全一致，否则停止。
7. 进入原有 `transfer_prepare` → LangGraph 人工审批 → Java YELLOW / RED 及 OTP → 执行/核实。

### 手机号转账

- 输入“给13800138000转200元”，任务使用 `payee_phone`，手机号需要满足大陆 11 位格式且来自用户原文。
- Java 按**已绑定的唯一手机号**确定账户；若未注册则结束，不生成银行账户号。
- 如果同时提供姓名和手机号，Java 搜索时**两项同时匹配同一用户**，否则未找到。

### 带备注转账

- 输入“给李四转200元，备注聚餐”。任务增加可选 `remark`；最多 80 字符、不能含控制字符、必须原样出现于用户当前指令。
- 新增参数沿原银行客户端 `prepare_transfer(..., remark=...)` 传给 Java；建单响应必须回显备注，Agent 验证返回值与用户原文一致，不一致停止继续审批。
- Vue 审批订单卡显示备注；原普通审批流程的订单查询、授权、执行和最终核查若用户提供了备注，也验证该字段未被更改。
- 成功转账的双方交易流水由 Java 生成；模拟银行已展示备注字段。

## 3. 新增 Java 接口契约（建议双方一致采用）

### GET `/api/transfers/recipients/search`

认证：`Authorization: Bearer <Java token>`，用户从 Token 识别，不接收付款 userId。

查询参数：`name`（可选，精确匹配）、`phone`（可选，精确匹配，注册手机号），至少其一。两者同时传时要求属于同一用户。搜索可见全部已注册账户，但要**排除当前用户本人**；仅返回必要脱敏字段。

200 示例（**数组**，不是 `{data:...}`）：

```json
[
  {"recipientId": 2, "payeeName": "张三", "accountMasked": "****6602"},
  {"recipientId": 3, "payeeName": "张三", "accountMasked": "****6603"}
]
```

- 无匹配返回 `[]`；**不能由模型选择候选**。
- 同名过多时返回明确业务错误，请用户改用手机号定位，不能静默截断候选后错误地认为唯一。
- `recipientId` 是银行返回的内部注册用户标识，不等于允许 LLM 自己指定付款用户。

### POST `/api/transfers/recipients/confirm`

认证：同上。请求：

```json
{"recipientId": 2}
```

Java 需再次校验目标用户存在、不是本人，**在当前付款用户的 payees 中建立或复用绑定**，返回：

```json
{"id": 19, "payeeName": "张三", "payeeAccountMasked": "****6602"}
```

`id` **是现有转账 prepare 接口能够使用的 `payeeId`**，不是固定等于注册用户 ID。Mock 中两者相等只是模拟简化，真实 Java 应按旧表和账户关系确定。

### 保留 POST `/api/transfers/prepare`

原字段 `payeeId`、`amount`、`requestId` 不变；已有 Java 请求支持可选 `remark`，本阶段要求 **建单响应、GET 订单、审批/执行后返回的订单视图包含 `remark`**（未提供时为空字符串）。

```json
{"payeeId": 19, "amount": "200.00", "requestId": "uuid-stable", "remark": "聚餐"}
```

响应继续保留 `orderId`、`payeeName`、`accountMasked`、`amount`、`riskLevel`、`status`；并返回 `remark`。Java 继续执行**当前付款方扣款、实际收款方入账、双方流水、幂等、当前用户归属、RED OTP**。

## 4. 新增 FastAPI 操作

- 原 `POST /api/agent/workflows/dynamic/start` 不变：可能返回 `WAITING_RECIPIENT_SELECTION`，新增 `recipientChoices` 数组。
- `POST /api/agent/workflows/dynamic/recipient/select`：`{"threadId":"...","recipientId":2}`，只处理当前登录用户自己、仍在等待候选选择的线程，并且 `recipientId` 必须在原候选列表中。
- `POST /api/agent/workflows/dynamic/recipient/cancel`：`{"threadId":"..."}`；在**未创建转账订单**时放弃候选选择，终态 `REJECTED`；不接触银行资金。
- 原 `dynamic/resume`、`transfer/otp/request`、`dynamic/{thread}` 完全保留；候选选择和金额审批是两次**不同**用户动作。

## 5. 修改文件

| 文件 | 改动 | 不变的业务 |
|---|---|---|
| `app/graph/task_planner.py` | 提取/校验手机号、备注 | Planner 不直接调用银行 |
| `app/graph/task_registry.py` | 转账允许新参数 | 一次最多一项敏感任务 |
| `app/banking_client.py` | 注册用户搜索、确认绑定 API | 原建单/授权/执行 API |
| `app/graph/dynamic_cancellation_workflow.py` | 新增候选解析、同名选择、银行绑定节点 | 原 transfer/cancel 审批链 |
| `app/workflow_api.py` | 工作流选择/放弃接口与选择状态 | Java 身份与线程归属校验 |
| `app/graph/transfer_prepare.py` | 传递并校验非空备注 | 原收款金额一致性校验 |
| `app/graph/transfer_approval_nodes.py` | 原订单备注一致性检查 | OTP 与幂等 |
| `mock_day7_backend.py` | 模拟银行搜索/确认及双方备注流水 | 原多用户双边记账 |
| `frontend/src/App.vue` | 用户选择事件、摘要、待处理状态 | 认证、Token、其他业务 |
| `frontend/src/components/DynamicWorkflowCard.vue` | 银行候选卡、备注字段 | 转账 YELLOW/RED 审批卡 |
| `tests/` | 新测与改动接口相关旧测 | 非相关旧测试 |

## 6. 测试说明

### 自动化（不需要模型 API）

在 `agent-service` 下：

```powershell
python -m pytest -q tests/test_day7_stage2_recipient.py tests/test_day7_mock_backend.py tests/test_day7_auth_proxy.py tests/test_task_planner.py tests/test_task_registry.py tests/test_transfer_prepare_helper.py tests/test_transfer_parser.py tests/test_mock_monthly_analytics.py tests/test_subscription_cancellation_client.py tests/test_mock_subscription_cancellation.py
```

### 浏览器端到端（需要你本地已安装 LangGraph、DeepSeek 配置）

保持阶段 1 模拟银行三服务启动方式；先注册“付款方张小明”“张三”“另一名张三”“李四”，用三个**不同的手机号**。

1. 登录张小明，输入“给李四转200元，备注聚餐”。确认建单卡显示备注，再确认；查询双方余额、流水、备注。
2. 输入“给[李四手机号]转300元”，确定只匹配李四；转账成功后核查余额。
3. 输入“给张三转100元”应先出现同名选择卡，**此时没有订单，也未扣款**；选择正确账户后，进入标准转账审批；可另测试“放弃本次转账”。
4. 创建超过日累计1000元的普通转账时，原有 RED OTP 仍应出现。模拟 OTP 只能本地使用 `246810`。
5. 退出并切换用户，不能恢复他人转账审批；旧余额、月度分析、订阅取消仍可使用。
6. 一句话复合查询 + 转账、缺少姓名/金额或伪造备注都应正确处理。

### 环境限制

本次容器没有可加载的 LangGraph 完整依赖，故**没有宣称完成 LangGraph 端到端执行测试**；浏览器完整 `npm run build` 也需要你本机恢复对应平台的 Rollup 原生依赖。已运行 Python 不依赖图的单元/模拟测试，且 Vue 单文件组件脚本、模板、样式编译通过。真实 Java / MySQL 联调待队友实现上述接口。

### 回滚

在应用前提交现有阶段 1 稳定代码；若尚未提交本阶段改动，使用 `git apply -R "...patch"` 撤销。不要盲目覆盖已有个人修改。
