# BankPilot 2.0 — D1 Agent 开发基线报告

- 日期：2026-11-16
- 负责人：成员 B（Agent / Python 开发）
- 项目目录：`E:\bank_agent\bankpilot-project`
- 基础代码来源：GitHub 远程 `main`（本地提交 SHA 需以当前终端核验结果为准）

> 本报告仅记录截至本次终端输出已实际验证的内容。尚未执行的完整回归测试、未检查的工作流文件和未确认的 Git 信息均明确标记为待验证。

## 1. Git 基线

| 项目 | 结果 |
|---|---|
| 本地项目目录 | `E:\bank_agent\bankpilot-project` |
| 远程仓库 | `https://github.com/gyx20200/bankpilot-ai-banking-agent.git` |
| 当前分支 | 待执行 `git branch --show-current` 核验 |
| 当前 HEAD | 待执行 `git rev-parse --short HEAD` 核验 |
| 工作区状态 | 待执行 `git status -sb` 核验 |
| D1 报告文件 | `docs/d1-agent-baseline.md` |

## 2. 开发环境

| 组件 | 实际结果 |
|---|---|
| Python | 3.14.0（终端日志） |
| Python 虚拟环境 | `agent-service\.venv` |
| Node.js | 24.11.1 |
| npm | 11.6.2 |
| Vite | 6.4.5 |
| 前端包管理 | `npm ci`，使用项目锁文件安装 |

说明：后续建议团队统一 Python 版本，优先选择项目依赖明确支持的 Python 3.11 或 3.12。当前记录的 Python 3.14.0 不代表已经确认所有依赖均针对该版本完成兼容性验证。

## 3. Python Agent 自动化测试

### 3.1 首次全量测试

执行命令：

```powershell
& $py -m pytest -q
```

首次结果：

| 指标 | 结果 |
|---|---:|
| Passed | 223 |
| Failed | 1 |
| Warnings | 4 |
| 失败测试 | `tests/agent/workflows/test_approval_resume.py::test_reject_closes_order_without_execution` |

失败场景为：用户拒绝订阅取消申请后，工作流应验证取消申请订单进入拒绝终态，同时订阅本身保持 ACTIVE，不应执行真实取消。

### 3.2 失败测试单项复测

检查到当前进程环境变量：

```text
BANK_API_MODE = java
```

随后打开并检查了测试文件：

`tests/agent/workflows/test_approval_resume.py`

单项复测命令：

```powershell
& $py -m pytest -q "tests/agent/workflows/test_approval_resume.py::test_reject_closes_order_without_execution"
```

实际结果：

```text
1 passed in 3.60s
```

结论：

- 原先失败的单项测试目前已复测通过。
- 本次输出没有展示测试文件的实际差异，因此具体修复代码及根因仍应通过 `git diff -- tests/agent/workflows/test_approval_resume.py` 核验。
- 尚未重新运行完整 pytest，全量回归结果待补充。
- 在全量复测通过前，不将测试基线记为 `224 passed`。

### 3.3 下一步全量回归命令

在项目根目录重新执行：

```powershell
& $py -m pytest -q
```

将最终 Passed、Failed、Warnings 数量补充到本节。

## 4. Vue 前端构建基线

执行目录：

`E:\bank_agent\bankpilot-project\frontend`

依次执行：

```powershell
npm ci
npm run build
```

实际结果：

- `npm ci` 成功，新增安装 34 个 packages。
- 审计 35 个 packages，报告 0 vulnerabilities。
- Vite 版本：6.4.5。
- `npm run build` 成功。
- 构建耗时：738ms。
- 生成 `dist/index.html`、CSS、JS 及图片资源。

构建期间出现以下警告：

```text
./assets/auth-bank-building.jpg referenced in ./assets/auth-bank-building.jpg
didn't resolve at build time, it will remain unchanged to be resolved at runtime
```

结论：

- Vue 生产构建已成功。
- `auth-bank-building.jpg` 图片资源引用路径需要后续检查。
- 该警告不是本次构建失败，不应记录为构建失败。
- 需要在浏览器中实际检查登录页图片是否正常显示，并确认资源应放在 `src/assets` 还是 `public` 目录，以及引用方式是否匹配 Vite 规则。

## 5. 当前前端组件盘点

通过 `Get-ChildItem .\frontend\src\components -Filter *.vue` 确认存在：

| 组件 | 当前可确认的职责/用途 |
|---|---|
| `AaCenter.vue` | AA 收款业务页面 |
| `AuthPanel.vue` | 登录与认证页面 |
| `DynamicWorkflowCard.vue` | 动态工作流展示与交互 |
| `MonthlyAnalyticsCard.vue` | 月度账单分析页面 |
| `ScheduleCenter.vue` | 预约转账页面 |

本节仅记录文件存在及从文件名可识别的用途，具体页面行为仍应通过源码和运行演示进一步确认。

## 6. Agent Task Registry 现状

已检查：

`agent-service/app/graph/task_registry.py`

该文件定义 `TaskSpec` 数据类，字段包括：

- `description`
- `executor_key`
- `risk_level`
- `required_params`
- `depends_on`
- `legacy_tool`

风险等级类型为：

```python
Literal["LOW", "MEDIUM", "HIGH"]
```

当前已注册 9 类任务：

| Task ID | Executor Key | 风险等级 | 必填参数 | 依赖 |
|---|---|---|---|---|
| `get_balance` | `balance` | LOW | 无 | 无 |
| `get_transactions` | `transactions` | LOW | 无 | 无 |
| `get_payees` | `payees` | LOW | 无 | 无 |
| `monthly_analytics` | `monthly_analytics` | LOW | `month` | 无 |
| `list_subscriptions` | `subscriptions` | LOW | 无 | 无 |
| `transfer_prepare` | `transfer_prepare` | HIGH | `payee_name`、`payee_phone`、`amount`、`remark` | `get_payees` |
| `schedule_transfer` | `schedule_transfer` | HIGH | `payee_name`、`payee_phone`、`amount`、`remark`、`time_expression`、`execute_at` | 无 |
| `create_aa_collection` | `aa_collection` | MEDIUM | `aa_participants`、`aa_mode`、`amount`、`aa_reason` | 无 |
| `cancel_subscription` | `subscription_cancellation` | MEDIUM | `target_name` | `list_subscriptions` |

此外，`resolve_execution_order(requested)` 会递归展开任务依赖，检查未注册任务和循环依赖，并返回依赖优先的执行顺序。

注意：Registry 中的风险等级属于 Agent 任务元数据，不应替代 Java 后端最终的身份认证、授权和风险审批。

## 7. Planner 现状

已检查：

`agent-service/app/graph/task_planner.py`

目前可以确认：

1. 使用 Pydantic 定义 `Task`、`TaskPlan` 等结构。
2. `Task` 配置 `extra="forbid"`、`strict=True`，用于限制额外字段并执行严格校验。
3. `TaskPlan` 包含：
    - `status`
    - `tasks`
    - `dependencies`
    - `clarification`
    - `execution_order`
4. 存在 `validate_plan(...)`，负责校验模型生成的任务计划。
5. `validate_plan(...)` 使用 Registry 中的依赖信息及 `resolve_execution_order(...)` 生成执行顺序。
6. 当前 `plan_tasks` 函数签名为：

```python
async def plan_tasks(message: str) -> TaskPlan:
```

其文档说明为单次 LLM 请求，返回经过验证的任务计划，不直接调用银行 API。

初步结论：

- 当前 Planner 的显式入口参数是单条 `message`。
- 多轮历史消息、用户长期偏好及跨轮参数继承尚未在本次 D1 检查中得到验证。
- D2—D4 需要设计 Context Manager，并明确历史上下文如何进入 Planner，同时保留当前用户输入的优先级。

## 8. LangGraph 工作流与 API 状态

以下文件尚需进一步检查并补充：

- `agent-service/app/graph/dynamic_cancellation_workflow.py`
- `agent-service/app/workflow_api.py`

待核验内容：

- Graph State 的完整字段。
- Node、Edge 和条件路由。
- 人工审批使用的中断机制。
- 当前 Checkpointer 类型及存储位置。
- `thread_id` 的生成、校验和用户归属。
- 工作流会话是否仅保存在进程内存。
- Python 服务重启后恢复工作流的实际能力。

在完成源码核查前，不将 Checkpoint 持久化和重启恢复标记为已实现。

## 9. D1 已发现问题与风险

| 优先级 | 问题 | 当前状态 | 后续处理 |
|---|---|---|---|
| P1 | 原订阅拒绝工作流测试首次失败 | 单项复测通过，全量复测待完成 | 检查测试文件 diff，运行完整 pytest |
| P2 | `auth-bank-building.jpg` 构建资源警告 | 构建成功，资源运行时显示待验证 | 检查 Vite 静态资源路径 |
| P2 | Python 3.14.0 环境兼容性 | 当前测试可运行，长期兼容性未确认 | 统一 Python 版本并验证依赖 |
| 待核验 | Checkpoint、Memory、会话恢复 | 尚未完成本次源码检查 | D2—D6 逐步设计和实现 |

## 10. D2 Agent 开发准备

成员 B 负责：

1. 设计 `conversationId` 与 LangGraph `thread_id` 的映射关系。
2. 设计 Context Manager，区分当前轮输入、短期对话历史和长期用户记忆。
3. 明确历史消息进入 Planner 的格式及上下文长度控制策略。
4. 定义历史参数继承规则：当前用户明确提供的新参数优先于历史参数；信息不足时应追问。
5. 与成员 A 对齐会话、消息、记忆和用户归属 API。
6. 设计用户隔离和敏感信息过滤规则。

成员 A 需要提供或共同确认：

- 会话创建、查询和删除接口。
- 消息保存和历史消息查询接口。
- 用户身份与会话归属校验方式。
- 数据表字段、主键、索引及时间字段格式。

## 11. D1 最终验收状态

| 任务 | 状态 |
|---|---|
| GitHub 代码更新及开发分支 | 待核验当前分支和 HEAD |
| Python 环境准备 | 已完成 |
| 首次 Python 全量测试 | 已完成：223 passed、1 failed |
| 原失败测试单项复测 | 已通过：1 passed |
| Python 全量回归复测 | 待完成 |
| `npm ci` | 已完成 |
| `npm run build` | 已完成，有一条图片资源路径警告 |
| 前端组件盘点 | 已完成初步盘点 |
| Task Registry 梳理 | 已完成 |
| Planner 梳理 | 已完成初步梳理 |
| LangGraph 工作流与 API 深入梳理 | 待完成 |
| D1 报告提交 Git | 待完成 |

---

**报告原则：** 只记录已执行命令和实际输出；单项测试通过不等同于全量测试通过；构建成功不等同于所有静态资源均已在浏览器验证；代码中存在某个类或配置不等同于该功能已经完成端到端验收。
