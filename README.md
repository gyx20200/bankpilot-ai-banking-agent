# BankPilot｜AI 智能银行 Agent 系统

> **银行业务模拟系统 · 比赛项目**。以自然语言调用受约束的银行工具，完成账户查询、收支分析、转账、订阅代扣、AA 收付款与单次定时转账。**所有账户、余额和资金交易均为模拟数据，不连接真实银行或支付网络。**

## 项目简介

BankPilot 采用 **Vue 3 + FastAPI + DeepSeek（Tool Calling）+ LangGraph + Spring Boot + MySQL** 的分层设计。用户只需输入完整业务指令，Agent 将其解析为受注册表约束的任务计划，再通过工作流执行查询或生成待审批订单；所有账户身份、OTP 验证、幂等、防重复扣款及最终资金状态由银行后端决定。

```text
Vue 3 聊天工作台 / 任务中心
        │  HTTP（登录 Token 仅保存在页面运行内存）
        ▼
FastAPI 网关（8000）
        ├─ DeepSeek Tool Calling → Task Planner → Task Registry
        └─ LangGraph（依赖调度 / 人工确认 / 工作流恢复）
                       │ 固定、白名单内的银行 API
                       ▼
           Spring Boot（8080）
                  │   └─ 登录认证 / 风控 / OTP / 业务状态 / 调度器
                  ▼
              MySQL 8
```

开发时也可将银行 API 切换至独立的 **Python Day 7 内存 Mock（18080）**，用于不依赖 MySQL 的 UI/Agent 演示。Mock 重启即清空账户与预约，不能替代正式数据库持久化验证。

## 核心功能

| 模块 | 用户能做什么 | 关键约束 |
| --- | --- | --- |
| 多用户账户 | 注册、登录、退出、查询本人的账户 | 注册后需单独登录；账号按已验证 Token 隔离；新账户初始模拟余额 ¥10,000 |
| 账户查询 | 查询余额、最近交易、常用收款人 | 数据来自银行接口，不由模型捏造 |
| 月度收支 | 查询指定月份收入、支出、净现金流及分类汇总 | Java/MySQL 统计，Agent 仅组织结果 |
| 订阅代扣 | 查询订阅、申请取消 | 取消属于敏感写操作，需用户确认与后端核验 |
| 普通转账 | 根据注册姓名/手机号找收款人，填写金额、备注 | 同名由用户选；普通转账按当日累计风险进入 YELLOW 确认或 RED OTP；由银行完成双边记账 |
| AA 收付款 | 发起人创建并确认发布 AA；他人登录后付款/拒绝，查看进度 | 发布前仅草稿；付款独立走银行转账；成功后才能标记已收款 |
| 单次定时转账 | 用自然语言约定未来时间，确认授权、查看或取消预约 | DeepSeek 输出标准时间；**所有金额预约时强制 OTP**；预约时不扣款；银行到期执行；错过标记 MISSED、不补执行 |
| 组合业务 | 一句话查询多个独立只读任务，配合一项敏感写任务 | Task Registry / LangGraph 控制依赖；同条指令最多执行一项独立敏感写业务 |

**业务边界：** 不支持周期性定时转账；不允许跳过授权；不提供真实货币支付。对银行返回 `UNKNOWN` / 执行结果不明确的订单，必须先查原单，不能直接重复提交。

## 项目目录

```text
bankpilot-project/
├── agent-service/           FastAPI、DeepSeek Planner、LangGraph、模拟银行及测试
│   ├── app/graph/           任务注册、任务规划、工作流、预约时间校验
│   ├── mock_day7_backend.py 本地内存 Mock（可选）
│   ├── .env.example         完整环境变量示例（不含密钥）
│   └── tests/               Python 回归测试
├── banking-backend/        Spring Boot 银行 API 与测试
├── database/               Day 1～Day 7 SQL 初始化、迁移与检查脚本
├── frontend/               Vue 3 + Vite 聊天与任务中心
├── docs/                   接口契约、业务交接、联调说明
└── tests/                  跨阶段的辅助冒烟测试
```

## 技术环境

- **JDK 21**、Maven 3.9+、MySQL 8.0
- **Python 3.11+**（依赖以 `agent-service/requirements.txt` 为准）
- **Node.js 20+**、npm（前端按 `frontend/package-lock.json` 安装）
- DeepSeek API Key，或遵循同样 Chat Completions/Tool Calling 协议的兼容模型。模型密钥仅用于本地服务，不放到 Vue 或仓库。

以下命令以 **Windows PowerShell、三个独立终端**为例。目录均相对于仓库根目录。

### 1. MySQL 数据库

**已有 Day 6 数据库的团队联调环境：** 先备份，然后按 [`docs/Day7_后端部署联调指南.md`](docs/Day7_后端部署联调指南.md) 创建隔离的 `bankpilot_day7_test` 数据库，恢复备份，并依次执行：

```text
database/day7_01_auth.sql
database/day7_02_recipients.sql    # 检查脚本
database/day7_03_aa.sql
database/day7_04_schedule.sql
database/day7_05_audit.sql
database/day7_06_test_db_grants.sql  # 管理员执行
database/day7_check.sql
```

**全新环境：** `database/init.sql` 只是 Day 1 基础表和演示数据，**并非 Day 7 完整数据库初始化脚本**。必须依据 `database/` 中 Day 2～Day 6 迁移及现有联调文档先准备对应表，再执行 Day 7 增量脚本；不要把上述 SQL 直接套在只有 Day 1 表的数据库中。注意 Day 7 SQL 中 `USE bankpilot_day7_test` 的目标库名。

> 迁移脚本不是可随意重复执行的初始化接口。操作前先备份并核实数据库目标，演示库不得使用真实客户数据。

### 2. 启动 Java 银行服务（8080）

```powershell
cd banking-backend
$env:DB_PASSWORD = Read-Host '本地 MySQL 应用用户密码'
$env:SPRING_DATASOURCE_URL = 'jdbc:mysql://127.0.0.1:3306/bankpilot_day7_test?connectionTimeZone=UTC&forceConnectionTimeZoneToSession=true'
$env:BANKPILOT_DAY7_JOBS_ENABLED = 'true'   # 演示单次定时转账到期执行时启用
$env:BANKPILOT_DEMO_OTP_DEBUG_ENABLED = 'false'
mvn spring-boot:run
```

预约调度由 **Java 进程**负责，不是 Vue 定时器或 LangGraph 长期驻留任务。若不准备测试到期执行，可将 `BANKPILOT_DAY7_JOBS_ENABLED` 设为 `false`；注意默认配置也为 `false`。

### 3. 启动 Python Agent（8000）

```powershell
cd agent-service
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
# 编辑 .env，填入你自己的 MODEL_API_KEY，并核对全部 BANK_* URL
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Agent API 文档：<http://127.0.0.1:8000/docs>。登录/注册与动态 Agent 工作流通过 `/api/agent/...` 路由访问。**注册不自动登录**；Token 只存 Vue 运行内存，刷新页面必须重新登录。

### 4. 启动 Vue（5173）

```powershell
cd frontend
npm ci
npm run dev
```

浏览器打开 <http://127.0.0.1:5173>。Vite 已将 `/api/agent` 代理到 `http://127.0.0.1:8000`。登录后在聊天输入自然语言；AA 收付款与定时转账进度从顶部的“任务中心”进入。

### 无 Java/MySQL 时使用 Mock（可选）

在第四个 PowerShell 终端：

```powershell
cd agent-service
$env:BANKPILOT_STAGE1_MOCK = '1'
.\.venv\Scripts\python.exe -m uvicorn mock_day7_backend:app --host 127.0.0.1 --port 18080
```

随后把 `agent-service/.env` 改为：`BANK_API_MODE=mock`，并将 **全部** `BANK_*_API_BASE` 和 `BANK_API_BASE` 中的 `8080` 统一改为 `18080`，重启 FastAPI。不能只改部分 URL，否则会出现 AA、预约或身份验证访问错误端口。Mock 测试 OTP 为 `246810`（**仅此本地 Mock**；Java 的 OTP 行为以其实现和环境设置为准）。

## 演示指令（每条单独发送）

```text
查询我的余额，并查询最近交易流水
分析我本月的收入和支出
查看我的订阅代扣协议
给李四转200元，备注聚餐
我和张三、李四聚餐300元，三个人AA，帮我收款
明天下午3点给李四转100元，备注生活费
分析本月收支，查询订阅，并取消音乐会员自动代扣
```

请先注册足够的模拟用户并登录。姓名重复的收款人需在前端选择，AA 接收人需要**切换自己的账户**处理请求；取消订阅要求目标协议真实存在。最后一条敏感写请求只允许完成一个独立写任务。预约显示 `SCHEDULED` 只代表已授权、等待银行到期执行，不代表已扣款。

## 测试与提交检查

```powershell
# Agent 测试
cd agent-service
.\.venv\Scripts\python.exe -m pytest -q

# 前端构建（另一个终端）
cd frontend
npm ci
npm run build

# Java 测试（另一个终端，需要适配好的测试数据库/环境）
cd banking-backend
mvn test
```

**交付前人工验收：** 注册→登录→余额/流水、收支分析、YELLOW/RED 与 OTP、重名选择、订阅取消、AA 收/付款及拒绝、预约确认与 OTP、到期双方流水、取消预约、登出与跨账号隔离。测试完成后清除本地 Token、检查 `.env` 等敏感配置未提交。

## 安全与实现边界

- DeepSeek 只产生**受限任务计划**；不直接持有银行账户操作权限或执行 SQL。
- FastAPI 对任务参数与身份做校验，敏感操作通过 LangGraph 人工确认；Java 在每次关键交易时再次确认身份、授权和状态。
- 普通转账按累计风控规则区别 YELLOW（人工确认）与 RED（OTP）；**单次定时转账无论金额都需要预约 OTP**。
- 银行后端应负责事务一致性、双方流水、幂等和未知结果核实；模拟环境不能作为生产级资金系统。
- 项目只用于教学/竞赛演示，禁止将调试开关、固定验证码、开发密钥或无鉴权端口用于生产。

## 更多文档

- [Day 7 Java/MySQL 本地部署与联调](docs/Day7_后端部署联调指南.md)
- [Day 7 Java-Agent 接口契约](docs/day7-java-agent-contract.md)
- [AA 业务交接](docs/DAY7-STAGE3-AA-HANDOFF.md)
- [单次预约业务交接](docs/DAY7-STAGE4-SCHEDULE-HANDOFF.md)
- [历史阶段开发与接口资料](docs/)（保留供追溯；最终行为以当前源码与银行 API 契约为准）

---

**BankPilot · AI Banking Assistant** — 让复杂的模拟银行事务，通过自然语言与可信审批流程变得直观、可核查。
