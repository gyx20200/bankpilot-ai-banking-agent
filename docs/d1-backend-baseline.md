# BankPilot 2.0 — D1 后端基线报告

> **日期：** 2026-11-16  
> **负责人：** 成员 A  
> **项目：** BankPilot AI Banking Agent  
> **Git 基础提交：** `7ff9b1f`  
> **工作分支：** `feature/v2-d1-baseline-member-a`  
> **任务范围：** Git 基线、MySQL 备份及业务状态核查、Java 自动化测试、后端 API 与数据结构梳理。

## 1. D1 结论摘要

| 检查项目 | 结果 | 状态 |
|---|---|---|
| Git 基线 | `7ff9b1f`；独立功能分支；检查时工作区干净 | 完成 |
| 开发环境 | JDK 21.0.12.1；Maven 3.10.0；MySQL 8.0.46 | 完成 |
| 数据库备份 | `bankpilot` 与 `bankpilot_day7_test` 均已导出非空 SQL 文件 | 初步完成；未恢复验证 |
| 数据库核查 | `bankpilot_day7_test` 共 21 张基础表 | 完成只读盘点 |
| 自动化测试 | 57 项通过，失败 0、错误 0、跳过 0，`BUILD SUCCESS` | 完成 |
| API 路由盘点 | 16 个 Controller、45 个方法级路由映射 | 完成静态扫描 |
| 接口契约/真实 MySQL E2E | 尚未逐项核对请求与响应字段、权限及真实库端到端行为 | 待后续验收 |

**总体结论：** 当前代码基线可作为 D2 设计起点。D1 已发现并解决测试登录配置问题；但自动化测试通过不能代替真实 MySQL 环境下的端到端验收，数据库中的异常预约状态也需要保留并分析。

## 2. Git 基线

- 项目根目录：`C:\Users\Username\Projects\bankpilot-ai-banking-agent`
- 当前分支：`feature/v2-d1-baseline-member-a`
- 基础提交短 SHA：`7ff9b1f`
- 检查时 `git status -sb` 仅显示当前分支，无未提交修改。
- D1 工作原则：保留现有业务代码与数据库状态，只提交经过核对的文档和非敏感辅助清单。
- **推送状态：** 目前没有收到本次文档 `git commit` / `git push` 的成功输出，暂不标记为已推送。

核验命令：

```powershell
git branch --show-current
git rev-parse --short HEAD
git status -sb
```

## 3. 开发环境

| 工具/服务 | 已确认版本或状态 | 说明 |
|---|---|---|
| 操作系统 | Windows 11 | VS Code PowerShell 终端 |
| Java | Oracle JDK `21.0.12.1` | 符合当前项目要求 |
| Maven | `3.10.0` | 可正常运行项目测试 |
| Spring Boot | `3.5.7` | 从测试启动日志确认 |
| MySQL Server | `8.0.46` | `MySQL80` 服务状态为 `Running` |
| mysql 客户端 | `8.0.46` | 命令已恢复可用 |
| mysqldump | `8.0.46` | 命令已恢复可用 |

**环境问题与处理：** 初次执行 `mysql`、`mysqldump` 时 PowerShell 提示找不到命令。已定位 MySQL Server `bin` 目录并临时加入当前终端的 `PATH`，命令可以正常执行。永久 PATH 配置尚未核验。

```powershell
$mysqlBin = "C:\Program Files\MySQL\MySQL Server 8.0\bin"
$env:Path = "$mysqlBin;$env:Path"
mysql --version
mysqldump --version
```

## 4. MySQL 数据库基线

### 4.1 数据库及连接配置

本机已确认存在两个数据库：

- `bankpilot`：基础演示数据库。
- `bankpilot_day7_test`：Day 7 多用户业务测试数据库，本次数据统计以此库为准。

在 `banking-backend/src/main/resources/application.properties` 中，默认连接配置为：

```properties
spring.datasource.url=jdbc:mysql://127.0.0.1:3306/bankpilot
spring.datasource.username=bankpilot_app
spring.datasource.password=${DB_PASSWORD}
spring.sql.init.mode=never
```

核查时当前 PowerShell 中 `SPRING_DATASOURCE_URL` 无输出。**注意：** 此信息仅表示当前检查终端未设置覆盖项，不足以证明此前或其他终端启动的 Java 进程实际连接哪一个数据库，须以启动配置为准。

本次未执行 `database/01` 至 `database/11` 初始化或迁移脚本，未修改原有余额、订单或业务状态。

### 4.2 备份记录

备份目录（Git 仓库外）：

`C:\Users\Username\BankPilotBackups\D1-20261116`

| 数据库 | SQL 文件 | 文件大小 | 文件修改时间 |
|---|---|---:|---|
| `bankpilot` | `bankpilot.sql` | 50,223 B | 2026-11-16 18:15:24 |
| `bankpilot_day7_test` | `bankpilot_day7_test.sql` | 102,051 B | 2026-11-16 18:15:20 |

备份使用 `mysqldump --single-transaction --routines --triggers --events --databases ... --result-file=...`。两份文件均已生成且非空，终端未显示导出错误。**这只能确认逻辑导出初步成功，尚未在隔离环境验证可恢复性。**

安全要求：SQL 备份、数据库凭证、Token、OTP、带个人信息的明细日志均不得提交到 GitHub。

### 4.3 核心业务数据量

统计时间：2026-11-16，检查库：`bankpilot_day7_test`。

| 检查指标 | 实际数量 |
|---|---:|
| 基础数据表（`BASE TABLE`） | **21** |
| `users`（用户） | **5** |
| `accounts`（账户） | **5** |
| `transfer_orders`（转账订单） | **37** |
| `aa_collections`（AA 收款单） | **4** |
| `scheduled_transfers`（预约转账单） | **12** |

此处是数据库记录条数，不代表对应功能已全部成功执行，也不代表数据质量已验收。

### 4.4 预约转账状态

| 状态 | 数量 | 基线备注 |
|---|---:|---|
| `CANCELLED` | 8 | 已取消记录；需结合具体业务原因判断 |
| `SUCCESS` | 2 | 标记为成功 |
| `MISSED` | 1 | 需要后续核查触发/调度原因 |
| `UNKNOWN` | 1 | 需要后续核查执行结果与状态一致性 |
| **合计** | **12** | 与预约单总数一致 |

本次查询中未出现 `FAILED` 状态。`MISSED` 与 `UNKNOWN` **不是自动判定为程序缺陷**，但属于后续验收必须关注的记录。D1 不修改状态，不重放订单，不执行可能影响资金的修复操作。

### 4.5 现有 21 张数据表

以下按业务分组记录。字段名来自 `information_schema.COLUMNS` 的只读查询；其中 `PRI`、`UNI`、`MUL` 为数据库索引标记，**不能仅凭它们判定外键约束已经存在**。

| 业务分组 | 数据表 | 主要用途及关键字段 |
|---|---|---|
| 用户与账户 | `users` | 用户主体：`id`, `display_name`, `phone`, `phone_verified`, `status` |
| 用户与账户 | `user_credentials` | 登录凭证：`user_id`, `username`, `password_hash`, `failed_login_count`, `locked_until` |
| 用户与账户 | `accounts` | 账户：`id`, `user_id`, `account_no`, `balance`, `status` |
| 用户与账户 | `payees` | 收款人：`id`, `user_id`, `payee_name`, `payee_account_id` |
| 流水与转账 | `transactions` | 交易流水：`id`, `account_id`, `direction`, `amount`, `category`, `occurred_at`, `transfer_order_id` |
| 流水与转账 | `transfer_orders` | 转账订单：`id`, `user_id`, `sender_account_id`, `receiver_account_id`, `amount`, `request_id`, `risk_level`, `status` |
| 流水与转账 | `approval_records` | 转账授权：`order_id`, `user_id`, `auth_method`, `approval_status`, `expires_at`, `authorized_at` |
| 流水与转账 | `audit_events` | 转账/业务审计：`user_id`, `order_id`, `action`, `result`, `created_at` |
| AA 收款 | `aa_collections` | AA 主单：`id`, `initiator_user_id`, `request_id`, `split_mode`, `total_amount`, `status` |
| AA 收款 | `aa_collection_items` | AA 明细：`id`, `collection_id`, `payer_user_id`, `amount`, `status`, `transfer_order_id` |
| 预约转账 | `scheduled_transfers` | 预约单：`id`, `owner_user_id`, `scheduled_at_utc`, `display_timezone`, `status`, `last_error_code`, `transfer_order_id` |
| 预约转账 | `scheduled_otp_challenges` | OTP 挑战：`schedule_id`, `user_id`, `otp_hash`, `failed_attempts`, `expires_at` |
| 预约转账 | `scheduled_transfer_authorizations` | 预约授权：`schedule_id`, `user_id`, `auth_method`, `scope_hash`, `valid_until`, `status` |
| 订阅 | `subscriptions` | 订阅记录：`id`, `user_id`, `merchant_name`, `amount`, `billing_cycle`, `status`, `next_pay_date` |
| 订阅 | `subscription_cancel_orders` | 取消订单：`id`, `user_id`, `subscription_id`, `request_id`, `workflow_id`, `status` |
| 订阅 | `subscription_cancel_events` | 取消事件：`order_id`, `user_id`, `action`, `result`, `created_at` |
| Agent/审计 | `agent_tool_events` | 工具调用审计：`user_id`, `request_id`, `tool_name`, `http_method`, `http_status` |
| Agent/审计 | `agent_workflow_runs` | 工作流实例：`id`, `user_id`, `workflow_id`, `plan_hash`, `created_at` |
| Agent/审计 | `agent_workflow_tasks` | 工作流任务：`run_id`, `task_type`, `month_value`, `merchant_name` |
| Agent/审计 | `business_audit_events` | 统一业务审计：`actor_user_id`, `business_type`, `business_id`, `action`, `result`, `trace_id` |
| 基础设施 | `day7_id_sequences` | ID 序列：`entity`, `next_id` |

**已核验的字段类型要点：** `id` / 用户或订单关联字段主要使用 `bigint`；金额与余额使用 `decimal`；业务状态使用 `varchar`；多数事件时间为 `datetime`，`users.created_at` 为 `timestamp`；`subscriptions.next_pay_date` 为 `date`；`scheduled_transfers.scheduled_at_utc` 为 `datetime`。字段是否 `NOT NULL`、默认值、精度、实际外键与唯一约束，还应通过 `SHOW CREATE TABLE` 进一步核查。

### 4.6 D2 数据模型复用建议

- **年度账单：** 优先复用 `transactions` 的 `account_id`、`direction`、`amount`、`category`、`occurred_at`，通过 `accounts.user_id` 做用户范围过滤；先判断现有交易覆盖范围和统计口径，再决定是否建汇总表。
- **异常交易检测：** 可使用 `transactions`、`transfer_orders` 作为候选输入；风控结果、规则版本、告警与用户处置记录宜独立建模，不能直接用转账订单的 `risk_level` 替代全部异常检测结果。
- **订阅识别：** 复用 `transactions.merchant_name`、`occurred_at`、`amount` 与 `subscriptions`，但识别结果需要区分“算法建议”和“用户确认的订阅”。
- **对话管理：** 当前 21 张表中未发现显式的会话历史/消息表，建议 D2 单独设计会话与消息模型，并与已有 `agent_workflow_runs.workflow_id` 建立逻辑关联。
- **事件及预算预留：** 现有 `scheduled_transfers` 是预约转账，不等同于通用事件或预算预留；需单独定义预算冻结/释放的语义，避免混淆实际余额与可支配余额。
- **卡片与理财：** 当前表清单未见专门的银行卡管理或理财持仓表，设计前先确认产品范围和数据模拟策略。

## 5. Java 自动化测试

### 5.1 测试执行

从项目根目录执行：

```powershell
mvn -f .\banking-backend\pom.xml test
```

- Spring Boot：`3.5.7`
- Maven Surefire Plugin：`3.5.4`
- 测试日志显示相关测试使用 H2 内存库，例如 `jdbc:h2:mem:bankpilotday2`、`jdbc:h2:mem:bankpilotworkflow`。

### 5.2 首次失败记录与根因

第一次完整执行（2026-11-16 18:20）：

| Tests run | Passed | Failures | Errors | Skipped | 结果 |
|---:|---:|---:|---:|---:|---|
| 57 | 20 | 37 | 0 | 0 | `BUILD FAILURE` |

多个测试在 `/api/auth/demo-login` 阶段失败：期望 HTTP 200（负向用例期望 401），实际为 HTTP 503；响应信息提示演示登录密码必须至少 12 字符。

根因已通过 `DemoLoginController.java` 源码定位：控制器读取的配置项为 `@Value("${bankpilot.demo.login.password:}")`，而最初设置的环境变量 `DEMO_LOGIN_PASSWORD` 未对应该配置项。改用 `BANKPILOT_DEMO_LOGIN_PASSWORD` 并设置测试专用密码后，配置正确生效。

该处理**仅调整本地测试运行环境**，未修改业务代码、MySQL 数据或关闭认证校验；测试密码及其他凭证不写入 Git 文档。

### 5.3 最终回归结果

完成时间：**2026-11-16 18:56:09（+08:00）**。

| Tests run | Passed | Failures | Errors | Skipped | Maven 退出码 | 构建结果 |
|---:|---:|---:|---:|---:|---:|---|
| **57** | **57** | **0** | **0** | **0** | **0** | **BUILD SUCCESS** |

耗时：`8.253 s`。

**结论：** 现有 Maven 自动化测试全部通过；此前 37 项失败已通过正确的配置修复。此结论仅覆盖当前测试集及其模拟环境，不表示真实 MySQL 业务全链路已经验收。

## 6. 现有后端 API 路由基线

### 6.1 扫描范围与汇总

从 `banking-backend/src/main/java` 扫描 `*Controller.java`：

- **Controller 类：16 个**。
- **方法级 HTTP 路由：45 个**。
- 统计依据：类级 `@RequestMapping` 与方法级 `@GetMapping` / `@PostMapping` 等组合。
- 下列路径是静态代码注解结果；HTTP 请求体、查询参数、响应 DTO、权限及可用条件需要在 D2 进一步核对。

| 模块 | 路由数量 | 对应 Controller |
|---|---:|---|
| 认证 | 5 | `Day7AuthController`, `DemoLoginController` |
| 账户与流水 | 3 | `BalanceController`, `PayeeController`, `TransactionController` |
| 转账（含收款人搜索） | 9 | `Day7RecipientController`, `TransferPrepareController`, `TransferWorkflowController` |
| AA 收款 | 11 | `Day7AaController` |
| 预约转账 | 7 | `Day7ScheduledController` |
| 订阅 | 5 | `SubscriptionController`, `SubscriptionCancellationController` |
| 月度分析 | 1 | `MonthlyAnalyticsController` |
| Agent 与工作流 | 3 | `AgentCapabilityController`, `AgentWorkflowRegistryController` |
| 健康检查 | 1 | `DemoHealthController` |
| **合计** | **45** | **16 个 Controller** |

### 6.2 认证（5）

| 方法 | 路径 |
|---|---|
| POST | `/api/auth/register` |
| POST | `/api/auth/login` |
| GET | `/api/auth/me` |
| POST | `/api/auth/demo-login` |
| POST | `/api/auth/logout` |

### 6.3 账户与交易（3）

| 方法 | 路径 |
|---|---|
| GET | `/api/demo/balance` |
| GET | `/api/demo/payees` |
| GET | `/api/demo/transactions` |

### 6.4 转账（9）

| 方法 | 路径 |
|---|---|
| GET | `/api/transfers/recipients/search` |
| POST | `/api/transfers/recipients/confirm` |
| POST | `/api/transfers/prepare` |
| GET | `/api/transfers/{orderId}` |
| POST | `/api/transfers/{orderId}/otp/request` |
| POST | `/api/transfers/{orderId}/authorize` |
| POST | `/api/transfers/{orderId}/execute` |
| POST | `/api/transfers/{orderId}/cancel` |
| GET | `/api/transfers/{orderId}/demo-otp` |

### 6.5 AA 收款（11）

| 方法 | 路径 |
|---|---|
| POST | `/api/aa/prepare` |
| GET | `/api/aa/outgoing` |
| GET | `/api/aa/inbox` |
| GET | `/api/aa/{id}` |
| POST | `/api/aa/{id}/publish` |
| POST | `/api/aa/{id}/cancel-draft` |
| GET | `/api/aa/items/{id}/payment` |
| POST | `/api/aa/items/{id}/payment/prepare` |
| POST | `/api/aa/items/{id}/otp/request` |
| POST | `/api/aa/items/{id}/payment/confirm` |
| POST | `/api/aa/items/{id}/decline` |

### 6.6 预约转账（7）

| 方法 | 路径 |
|---|---|
| POST | `/api/scheduled-transfers/prepare` |
| POST | `/api/scheduled-transfers/{id}/authorize` |
| POST | `/api/scheduled-transfers/{id}/otp/request` |
| GET | `/api/scheduled-transfers/{id}/demo-otp` |
| POST | `/api/scheduled-transfers/{id}/cancel` |
| GET | `/api/scheduled-transfers/mine` |
| GET | `/api/scheduled-transfers/{id}` |

### 6.7 订阅（5）

| 方法 | 路径 |
|---|---|
| GET | `/api/demo/subscriptions` |
| POST | `/api/subscription-cancellations/prepare` |
| GET | `/api/subscription-cancellations/{orderId}` |
| POST | `/api/subscription-cancellations/{orderId}/authorize` |
| POST | `/api/subscription-cancellations/{orderId}/execute` |

### 6.8 月度分析（1）

| 方法 | 路径 |
|---|---|
| GET | `/api/demo/analytics/monthly` |

### 6.9 Agent / 工作流（3）

| 方法 | 路径 |
|---|---|
| GET | `/api/agent/capabilities` |
| POST | `/api/agent/workflow-runs` |
| GET | `/api/agent/workflow-runs/{workflowId}` |

### 6.10 健康检查（1）

| 方法 | 路径 |
|---|---|
| GET | `/api/demo/health` |

**补充说明：** `demo-login`、`demo-otp` 为演示相关接口，不应假设其默认在生产或所有运行环境中可用。下一阶段须核对开关、鉴权以及敏感信息暴露风险。

## 7. D1 问题与风险

| 优先级 | 问题 / 风险 | 当前判断 | 后续动作 |
|---|---|---|---|
| P0 | 未解决的 Java 测试构建阻塞 | **无已确认项**；57/57 已通过 | 保持回归测试 |
| P1 | 预约单 `MISSED` 1 条、`UNKNOWN` 1 条 | 数据异常状态待调查，尚不能直接定性为代码 bug | 只读核对 `last_error_code`、调度与审计链路 |
| P1 | 缺少真实 MySQL 端到端验收证据 | H2 自动化测试不能替代真实库运行 | D2 规划隔离、可回滚的接口验收 |
| P1 | API 请求/响应/鉴权契约未逐项盘点 | 当前仅完成路由扫描 | 核对 DTO、权限、状态码与幂等规则 |
| P2 | SQL 备份未做隔离恢复演练 | 已导出非空文件，不代表可恢复 | 以后在独立数据库测试恢复 |
| P2 | MySQL 客户端 PATH 可能仅临时有效 | 当前终端可用 | 永久配置并重启终端复核 |
| P2 | 测试环境依赖显式配置项 | 已修复本次测试 | 制定不含密码的本地测试运行说明 |

## 8. D2 交接与设计建议

### 8.1 可复用的后端能力

现有后端已提供认证、账户与流水查询、转账准备/授权/执行、AA 收款、预约转账、订阅查询与取消、月度分析以及 Agent 工作流登记等路由。D2 应优先复用这些接口，避免重复实现资金类业务链路。

### 8.2 新功能与现有数据的关系

| 拟新增功能 | 可复用数据/接口 | 建议新增或进一步确认的部分 |
|---|---|---|
| 多轮对话管理 | 认证、`agent_workflow_runs` | 会话、消息、会话与工作流关联、上下文权限 |
| 年度账单 | `transactions`、`accounts`、月度分析 | 年度聚合口径、类别与时间范围、是否缓存 |
| 异常交易检测 | `transactions`、`transfer_orders`、审计表 | 风控规则/模型结果、告警状态、解释及复核记录 |
| 理财 | 用户与账户 | 演示产品、持仓、交易/估值模型与风险提示 |
| 卡片管理 | `users`、`accounts` | 卡片与账户关系、脱敏展示、冻结/解冻状态 |
| 订阅识别 | `transactions`、`subscriptions` | 周期识别、置信度、人工确认、误报处理 |
| 事件管理 | 工作流与预约记录 | 通用事件、提醒、触发条件及执行历史 |
| 预算预留 | `accounts`、`transactions` | 预算、预留、释放、实际余额与可用余额口径 |

### 8.3 对话管理 API 初步建议（尚未实现）

| 方法 | 建议路径 | 用途 |
|---|---|---|
| POST | `/api/conversations` | 新建对话 |
| GET | `/api/conversations/{conversationId}` | 获取会话元信息 |
| GET | `/api/conversations/{conversationId}/messages` | 分页查询消息 |
| POST | `/api/conversations/{conversationId}/messages` | 追加消息并触发 Agent 流程 |

这是设计草案，不属于第 6 节已实现的 45 条 API。具体路径应与成员 B 协商，并确认认证方式、消息幂等、用户数据隔离和业务审批边界。

### 8.4 A/B 双方需要统一的字段与约束

- 身份与资源归属：`userId`、`accountId`，确保读取和操作均按当前登录用户鉴权。
- 业务订单：`orderId`、`requestId`、`status`、`errorCode`；需要确认现有 DTO 字段，而非仅按数据库列名推断。
- Agent 流程：`workflowId`、建议新增 `conversationId`；确定二者关联和生命周期。
- 金额与时间：明确金额字符串/数值的 JSON 表达，后端采用精确小数处理；统一时区与 ISO 8601 时间约定。
- 安全与审计：确认高风险操作的授权步骤、幂等性、Token 保护、日志脱敏和操作可追踪性。
- 接口错误：明确 HTTP 状态码、错误码、可重试与不可重试条件。

### 8.5 D2 建议起步顺序

1. 根据 Controller、Service、DTO 核对核心 API 请求/响应字段及鉴权规则。
2. 用 `SHOW CREATE TABLE` / 索引清单核对实际外键、唯一约束、金额精度及时间字段。
3. 选定一个最小新增模块（优先对话管理），明确 API 契约、数据模型和测试用例。
4. 在独立测试环境验收新增能力与现有转账、AA、订阅、预约功能的兼容性。
5. 对 `MISSED` / `UNKNOWN` 预约单只读排查，避免人工改写历史基线。

## 9. D1 交付物与 Git 提交

**计划提交文件：**

- `docs/d1-backend-baseline.md`：本报告。
- `docs/d1-api-annotations.csv`：从 Controller 源码生成的路由注解清单（若已生成并检查）。

**不允许提交：** 项目外的数据库 SQL 备份、真实凭证、OTP、Token、包含个人敏感资料的日志及数据库原始明细。

待文件核对完成后执行：

```powershell
git status -sb
git add -- docs/d1-backend-baseline.md
# 如果已经生成并检查过 CSV，再执行：
# git add -- docs/d1-api-annotations.csv
git diff --cached --check
git diff --cached --stat
git diff --cached
git commit -m "docs: establish D1 backend baseline"
git push -u origin feature/v2-d1-baseline-member-a
git status -sb
```

**提交状态：** 本报告整理时尚未收到最终 Git 提交与远程推送验证输出，应以实际终端结果为准。

## 10. 最终总结

2026-11-16 的 D1 后端基线工作已经获得以下可核验结果：

- Git 基础提交为 **`7ff9b1f`**，工作分支为 **`feature/v2-d1-baseline-member-a`**。
- Java、Maven、MySQL 环境可用，两个业务数据库已完成非空 SQL 逻辑导出。
- `bankpilot_day7_test` 包含 **21 张表**、**5 名用户**、**5 个账户**、**37 条转账订单**、**4 条 AA 收款单**、**12 条预约转账单**。
- 预约状态为：`CANCELLED=8`、`SUCCESS=2`、`MISSED=1`、`UNKNOWN=1`，异常状态留待后续只读调查。
- Java 自动化测试最终 **57/57 通过，BUILD SUCCESS**；原有 503 失败根因是 Spring 演示登录配置项映射不匹配，修复方式为正确设置本地测试环境变量。
- 已静态核对 **16 个 Controller、45 个方法级路由**，可作为 D2 接口复用与扩展设计的基础。

**D1 验收边界：** 数据库隔离恢复、真实 MySQL 端到端业务测试、API 全量契约核对以及 Git 推送仍需单独验证，不应在完成前标记为已通过。
