# BankPilot 2.0 — D5 集成测试与验收报告

## 1. 基本信息

| 项目 | 内容 |
| --- | --- |
| 项目名称 | BankPilot — 基于 LangGraph 的金融业务 Agent 与 RAG 智能服务系统 |
| 开发阶段 | D5：LangGraph Checkpoint 持久化与工作流会话登记 |
| 验收日期 | 2026-11-20 |
| 验收方式 | 单机本地集成测试（成员 A 负责联调） |
| 技术栈 | Java 21、Spring Boot 3.5.7、Spring JDBC、MySQL 8、FastAPI、LangGraph、AsyncSqliteSaver、Vue 3 |
| 验收结论 | **PASS — D5 全部测试与验证通过** |

> 本报告依据项目成员确认的本地验收结果编写。未提供原始测试日志、具体全量测试数量、实际线程 ID 和订单 ID，因此不虚构相关数据。本文中的银行业务均为模拟业务，未接入真实银行支付系统。

## 2. 开发目标与交付成果

D5 在 D3 聊天历史持久化、D4 多轮上下文理解与账单分析能力的基础上，解决主动态工作流在 Python 服务重启后丢失执行状态的问题。

本阶段完成以下任务：

- 将主动态 LangGraph 工作流的检查点持久化到 SQLite，保留内存模式用于离线测试。
- 在 MySQL 中持久化工作流与用户、会话、原始 USER 消息之间的关联关系。
- 实现工作流登记、查询、列表读取和生命周期更新接口。
- 实现服务重启后的原工作流只读恢复及银行订单状态核对。
- 保留已有的人机协同审批、风险控制、消息持久化和只读银行工具能力。
- 验证用户归属隔离、重复启动防护、生命周期约束和敏感凭证保护。

## 3. 实现方案与职责分工

### 3.1 成员 A：Java / MySQL

- 新增 `WorkflowSessionController.java`、`WorkflowSessionService.java`。
- 在 `ConversationService.java` 中增加 `requireWorkflowSource()`，复用 D3 的消息脱敏、请求编号和会话归属校验。
- 执行 `database/13_workflow_session_persistence.sql`，在 `agent_workflow_sessions` 中新增 `source_request_id` 和联合唯一索引 `uk_workflow_source_request (conversation_id, source_request_id)`。
- 实现基于用户 Bearer Token 和 `X-Bankpilot-Agent-Key` 的双重校验，以及事务内工作流登记和状态更新。
- 编写 `WorkflowSessionServiceTest.java`，完成专项测试、全量回归和真实 MySQL 接口验证。

### 3.2 成员 B：Python Agent / LangGraph / Vue

- 使用 `AsyncSqliteSaver` 持久化主动态工作流 Checkpoint，通过 FastAPI 生命周期管理数据库连接。
- 对接 Java 工作流登记服务，在调用 Graph 前确认登记成功。
- 保留原有 Planner、工具调用和审批流程，并同步工作流生命周期状态。
- 提供工作流列表、原线程检查点只读查询和历史任务展示能力。
- 完成持久化、恢复、权限控制及原有业务的自动化回归测试。

### 3.3 状态存储边界

| 数据 | 存储位置 | 职责 |
| --- | --- | --- |
| USER / ASSISTANT 文字历史 | MySQL `agent_messages` | 聊天记录恢复与多轮上下文 |
| 工作流归属、生命周期、有效期 | MySQL `agent_workflow_sessions` | 权限验证、登记、重复启动防护 |
| Graph 执行状态、中断位置 | SQLite `checkpoints.sqlite` | 原线程 Checkpoint 持久化 |
| 银行订单、流水、余额 | MySQL 银行业务表 | 银行业务事实及最终状态 |
| Token、OTP、内部密钥 | 请求运行时环境 | 不作为工作流持久化凭证 |
| 交互缓存及进程内锁 | Python 运行时内存 | 单进程任务交互与并发控制 |

核心执行顺序：验证用户和来源消息 → 登记工作流 → 执行 LangGraph → 保存 Checkpoint → 同步生命周期 → 保存 ASSISTANT 回复。恢复查询只读取已有状态，不重新启动 Graph。

## 4. 联调环境

| 服务 | 本地配置 |
| --- | --- |
| Vue | `http://127.0.0.1:5173` |
| FastAPI | `http://127.0.0.1:8000` |
| Spring Boot | `http://127.0.0.1:8080` |
| MySQL | `bankpilot_day7_test` |
| Checkpoint 模式 | `BANKPILOT_CHECKPOINT_MODE=sqlite` |
| Checkpoint 文件 | `agent-service/data/checkpoints.sqlite` |
| Python 运行方式 | 单 Uvicorn Worker，重启测试期间不使用自动 reload |

Java 与 FastAPI 使用一致的内部服务密钥；密钥、Token、OTP、数据库密码不写入测试报告或代码仓库。

## 5. 自动化测试与构建结果

| 编号 | 测试项目 | 验收结果 |
| --- | --- | --- |
| AUTO-01 | D5 Java Service 专项 JUnit（8 个测试方法） | PASS |
| AUTO-02 | Java 全量 Maven 回归测试 | PASS |
| AUTO-03 | Python 工作流、Checkpoint 与恢复专项 pytest | PASS |
| AUTO-04 | Python 全量 pytest 回归测试 | PASS |
| AUTO-05 | Python 依赖兼容性检查 | PASS |
| AUTO-06 | Vue 生产构建 `npm run build` | PASS |
| AUTO-07 | Git 差异格式检查 `git diff --check` | PASS |

复现命令（项目根目录，PowerShell）：

```powershell
mvn -f .\banking-backend\pom.xml "-Dtest=WorkflowSessionServiceTest" test
mvn -f .\banking-backend\pom.xml test

$py = ".\agent-service\.venv\Scripts\python.exe"
& $py -m pip check
& $py -m pytest -q tests/agent/workflows
& $py -m pytest -q

cd .\frontend
npm run build
cd ..

git diff --check
```

全量测试的具体执行数量和耗时以本地原始日志为准。

## 6. Java / MySQL 接口验收

以下接口均须验证当前用户身份和内部服务密钥。

| 编号 | 测试场景 | 预期及验收结果 | 结论 |
| --- | --- | --- | --- |
| API-01 | `POST /api/workflow-sessions` 正常登记 | HTTP 201，初始状态 RUNNING | PASS |
| API-02 | `GET /api/workflow-sessions/{threadId}` | HTTP 200，返回本人工作流 | PASS |
| API-03 | `GET /api/workflow-sessions?conversationId=...` | HTTP 200，返回本人会话下的任务 | PASS |
| API-04 | `PATCH /api/workflow-sessions/{threadId}/status` | 合法状态更新成功 | PASS |
| API-05 | 同一来源消息或 threadId 重复登记 | HTTP 409，不重复创建记录 | PASS |
| API-06 | 找不到来源 USER 消息、角色或内容不匹配 | 拒绝登记 | PASS |
| API-07 | 访问其他用户的会话或工作流 | HTTP 404 | PASS |
| API-08 | 无有效登录凭证 | HTTP 401 | PASS |
| API-09 | 内部服务密钥缺失或错误 | HTTP 403（服务端密钥未配置时为 503） | PASS |
| API-10 | 终态工作流重新设置为 RUNNING | HTTP 409 | PASS |
| API-11 | 过期工作流查询与状态变更 | 可只读查询；改变状态返回 HTTP 410 | PASS |
| API-12 | 来源消息脱敏及凭证检查 | 复用 D3 校验规则 | PASS |
| API-13 | MySQL 持久化关联与有效期核对 | 用户、会话、来源 requestId 正确；默认有效期 30 分钟 | PASS |

生命周期状态为 `RUNNING`、`WAITING`、`COMPLETED`、`REJECTED`、`ENDED`、`NOT_CONFIRMED`。相同状态更新为无副作用操作，不延长有效期。D5 不允许终态直接重新进入运行状态。

## 7. LangGraph 持久化与重启恢复验收

### 7.1 关键测试过程

1. 启动 MySQL、Spring Boot、FastAPI 和 Vue，确认实际 Checkpoint 模式为 SQLite。
2. 新建会话，发送“查询我的余额”，验证普通工作流能够执行、登记、保存检查点和历史回复。
3. 在新会话中发送模拟转账指令，例如“给李四转10元，备注D5恢复测试”。确认收款对象存在，等待原银行订单进入审批阶段，不点击确认、不申请 OTP。
4. 记录重启前的 `conversationId`、`threadId`、`orderId`、等待节点、订单状态及账户余额，核对 MySQL 工作流登记状态为 `WAITING`。
5. 正常停止 FastAPI，保留 SQLite 文件与 MySQL 数据，使用相同 Checkpoint 路径重新启动 Python 服务。
6. 重新登录原测试账号，打开原历史会话，通过任务中心或恢复接口查询原工作流。
7. 比较重启前后线程编号、订单编号、等待节点、真实订单状态与余额，验证查询恢复不会创建新订单或执行扣款。

### 7.2 端到端验收结果

| 编号 | 验收项目 | 验收结果 |
| --- | --- | --- |
| E2E-01 | 健康检查确认实际启用 SQLite Checkpointer | PASS |
| E2E-02 | SQLite 文件生成并存在真实线程检查点 | PASS |
| E2E-03 | 普通只读查询成功，MySQL 登记及聊天消息落库 | PASS |
| E2E-04 | 模拟转账工作流正常进入待审批中断 | PASS |
| E2E-05 | Python 服务停止并重新启动后读取原 Checkpoint | PASS |
| E2E-06 | 重新登录后查询到原会话关联工作流 | PASS |
| E2E-07 | 恢复出的 threadId 与重启前一致 | PASS |
| E2E-08 | 恢复出的银行订单 ID 与重启前一致 | PASS |
| E2E-09 | 能够读取原等待审批节点 | PASS |
| E2E-10 | 银行订单状态通过原业务接口核实 | PASS |
| E2E-11 | 恢复查询不重复建单、不自动扣款 | PASS |
| E2E-12 | 重启后的任务只读展示，禁止直接继续审批 | PASS |

**核心结果：** 主动态工作流在 Python 服务重启后仍可根据原线程编号读取持久化检查点，并关联原银行订单。恢复前后任务身份保持一致，未发现恢复查询导致的重复建单或余额变化。

### 7.3 异常与安全验证

| 编号 | 测试场景 | 预期及验收结果 | 结论 |
| --- | --- | --- | --- |
| SEC-01 | 工作流登记失败或未确认 | 不启动新的 Graph | PASS |
| SEC-02 | 重复提交同一个 USER requestId | 不创建第二个工作流或银行订单 | PASS |
| SEC-03 | 未授权或其他用户读取 Checkpoint | 拒绝访问 | PASS |
| SEC-04 | MySQL 登记存在但 Checkpoint 缺失 | 明确提示不能恢复 | PASS |
| SEC-05 | Checkpoint 存在但缺少有效归属记录 | 拒绝访问 | PASS |
| SEC-06 | 过期工作流 | 只读查看，不继续执行 | PASS |
| SEC-07 | 重启后直接 resume、申请 OTP 或选择收款人 | 阻止交互执行路径 | PASS |
| SEC-08 | 生命周期或银行业务状态不一致 | 标记未确认，不自动执行 | PASS |
| SEC-09 | 凭证持久化检查 | 不将 Token、OTP 或内部密钥作为持久化运行凭证 | PASS |
| SEC-10 | 原有同进程审批机制 | 原授权、风险和幂等约束保持有效 | PASS |

## 8. 持久化证据与复现查询

### 8.1 MySQL 工作流登记

```sql
USE bankpilot_day7_test;

SELECT thread_id, conversation_id, source_request_id,
       user_id, status, created_at, expires_at
FROM agent_workflow_sessions
ORDER BY created_at DESC
LIMIT 20;
```

### 8.2 来源消息关联

```sql
SELECT s.thread_id, s.conversation_id, s.user_id,
       m.role, m.request_id, s.status
FROM agent_workflow_sessions s
JOIN agent_messages m
  ON m.conversation_id = s.conversation_id
 AND m.request_id = s.source_request_id
ORDER BY s.created_at DESC
LIMIT 20;
```

D5 新登记任务应与当前会话中的 USER 消息正确关联。

### 8.3 银行订单核对

```sql
SELECT id, user_id, amount, risk_level, status, created_at
FROM transfer_orders
ORDER BY id DESC
LIMIT 10;
```

核对同一笔模拟订单重启前后的编号、状态、金额，并确认没有因读取历史而产生新的转账订单。

### 8.4 SQLite Checkpoint 核对

```powershell
$py = ".\agent-service\.venv\Scripts\python.exe"
& $py -c "import sqlite3; c=sqlite3.connect('file:agent-service/data/checkpoints.sqlite?mode=ro', uri=True); print(c.execute('SELECT thread_id, COUNT(*) FROM checkpoints GROUP BY thread_id').fetchall()); c.close()"
```

此命令仅读取线程编号和检查点数量，不输出完整序列化 State。数据库文件、完整 Checkpoint 数据及敏感日志不纳入 Git 提交。

## 9. D3 / D4 回归验收

| 编号 | 回归功能 | 结果 |
| --- | --- | --- |
| REG-01 | 多会话管理、USER / ASSISTANT 文字历史恢复 | PASS |
| REG-02 | 月度账单连续续问与年份继承 | PASS |
| REG-03 | 重新登录后利用持久化会话上下文 | PASS |
| REG-04 | 年度收支、消费分类与月度趋势 | PASS |
| REG-05 | 大额支出和疑似重复扣费检测 | PASS |
| REG-06 | 多工具复合只读任务 | PASS |
| REG-07 | 原有转账审批、订阅、AA 和预约业务回归 | PASS |

## 10. 已知边界与后续开发

D5 全部验收通过，当前没有阻塞进入 D6 的已知问题。但以下内容不属于本阶段完成范围：

- 重启后的原任务仅支持只读恢复，不代表可以安全恢复资金操作。D6 需要实现银行业务状态核对、重新授权、OTP 处理、幂等继续执行及不确定结果处置。
- MySQL 工作流登记与 SQLite Checkpoint 属于两个独立存储，不具备跨库原子事务。发生进程异常或状态同步失败时，必须采取保守恢复策略，不盲目重放任务。
- 当前 SQLite 和进程内锁方案面向单机、单进程模拟演示，尚不承诺多 Worker 或分布式并发审批安全。
- D5 持久化范围为主动态工作流；旧版兼容 Graph 不纳入本次恢复承诺。
- D3 历史记录当前主要恢复文字摘要，不要求恢复全部结构化业务卡片。
- 长期用户记忆、RAG、MCP、Agent Skills、完整 Evaluation 与 Trace 属于后续开发阶段，不计入本次验收。

## 11. 最终验收结论

**D5：PASS（全部通过）**。

BankPilot 已完成基于 SQLite 的主动态 LangGraph Checkpoint 持久化，以及基于 MySQL 的工作流登记和生命周期管理。通过单机服务重启、重新登录、原线程读取、银行订单核查和安全回归测试，验证了工作流状态可持久保存、可按用户归属查询、可只读恢复，并且不会因恢复查询而重复执行模拟资金操作。

本阶段开发目标达成，可进入 D6：工作流安全恢复、人工审批续接、银行订单对账与幂等执行。
