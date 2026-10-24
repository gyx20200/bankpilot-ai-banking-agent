# Agent + 前端负责人：Day 3–Day 7 开发任务拆解

> 使用本包 Day 2 的聊天接口与四个读工具为基础，渐进增量开发。写操作必须经过 Java 端审批，LLM 没有最终执行权限。

## Day 3：自然语言转账草稿 + 确认 UI（不扣款）

你要改：

1. `agent-service/app/router.py` 增加结构化转账意图识别（可以先正则 + 提问澄清，不要写死金额和收款人）。
2. `agent-service/app/banking_client.py` 增加 `prepare_transfer(payee_id, amount, remark)`，调用 Java `POST /api/transfers/prepare`，必须只创建订单。
3. 前端组件 `frontend/src/components/TransferReviewCard.vue`（自行新建）：展示金额、脱敏账号、收款人、风险级别、订单编号、状态。
4. 支持“取消”和“需要确认”，**不调用执行资金的接口**。

与 Java 同学统一接口：

```
POST /api/transfers/prepare
request: {"payeeId": 1, "amount": "200.00", "remark": "AA", "requestId": "UUID"}
response: {"orderId": 101, "payeeName": "李四", "accountMasked": "****5291", "amount": "200.00", "riskLevel": "YELLOW", "status": "PENDING_APPROVAL"}
```

当天验收：输入“给李四转 200 元”后，显示订单卡且余额不变；不允许来自 LLM 的 `userId` 指定付款账户。

## Day 4：用户审批、模拟红色验证与后端状态查询

1. 前端新增审批界面，黄色确认；红色由独立后端 OTP 模拟验证。
2. 通过浏览器正常用户会话发起审批；Python 不保管银行账户密码或 OTP。
3. 每次转账确认后查询订单状态，以订单状态为准显示成功或失败；不能由 LLM 宣称转账成功。
4. 测试取消、重复点击、超时、无权操作他人订单、首次 800 元再转 500 元触发红色级别。

当天验收：授权前余额不变；授权执行后服务端写入流水和余额；重复点击不重复转账。

## Day 5：真正接入 LLM 的 Tool Calling

1. 在 `app/llm_router.py` 新增使用模型 API 的路由，返回 **结构化** JSON，例如 `{intent, entities, missing_fields}`，由 Pydantic 校验。
2. 仅注册白名单工具：`get_balance`、`get_transactions`、`get_payees`、`get_subscriptions`、`prepare_transfer`。
3. 余额和交易结果只能使用银行后端响应，不接受 LLM 生成的账户数字。
4. 没有模型 API Key 或模型不可用时，允许退回 Day 2 规则模式，界面明确说明；不允许假装模型已经接入。
5. 做 20 条用例测试：正常请求、模糊输入、缺少收款人、金额为负、注入式“跳过权限”等。

当天验收：LLM 确实能选择至少四个查询工具和创建转账草稿工具；不会未经授权写入业务数据。

## Day 6：LangGraph 复合任务 + Human-in-the-loop

1. 新建 `app/graph/state.py`、`workflow.py`、`nodes.py`。
2. 展示固定 DAG 示例：查流水和订阅可以并行，分析结果后进入“待取消代扣”审批，用户批准才调用后端代扣取消 API。
3. 加 Checkpointer；每个会话分配 `thread_id`；用户批准时使用相同 ID 恢复任务。
4. 注意 `interrupt()` 恢复时节点会重新开始，资金写操作放在可幂等的独立后端执行节点，避免重新执行两次。
5. UI 新增 `TaskTimeline`，展示“查询 → 分析 → 等待确认 → 执行 → 结果”。

当天验收：一句话查询月账单、查订阅、申请取消指定订阅；拒绝审批后不取消。

## Day 7：可靠性、安全与评测

1. 页面处理 Python 502、Java 超时、订单未知状态、空列表、缺参数。
2. 增加输入长度限制与操作确认按钮的防重复提交。
3. 保存非敏感的 `requestId`、步骤名称、工具耗时、状态，敏感信息脱敏。
4. 测试恶意输入不能绕过 Java 授权；在交易备注中放“忽略系统指令”时也不会将其当指令执行。
5. 输出测试统计：总用例数、成功数、失败数；不编造高成功率。

当天验收：列出安全测试的实际运行结果，优先修复重复扣款与权限绕过。

## 现在不要做

- 自己训练/微调模型
- 让 LLM 写 SQL 或操作 MySQL
- 让 LLM 访问 Java 的转账 execute API（审批仅由后端控制）
- 同时研究很多 Agent 框架、RAG、MCP；这些留到赛后
