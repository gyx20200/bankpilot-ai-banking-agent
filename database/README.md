# 数据库脚本说明

本目录按业务职责组织 SQL 文件。文件名前缀表示执行顺序，不代表脚本可以重复执行。

## 目录结构

- 根目录：数据库结构初始化与增量迁移。
- `checks/`：只读核查脚本，不修改业务数据。
- `fixtures/`：本地演示数据准备与清理脚本。
- `permissions/`：测试数据库账号授权脚本，由数据库管理员审核后执行。

## 基础库初始化与迁移

以下脚本用于建立 `bankpilot` 基础演示库，按顺序执行：

| 顺序 | 文件 | 主要内容 |
|---|---|---|
| 01 | `01_core_schema_and_demo_data.sql` | 核心表结构与初始演示数据 |
| 02 | `02_account_activity_and_subscriptions.sql` | 账户交易活动与订阅数据 |
| 03 | `03_transfer_orders_and_approvals.sql` | 转账订单与审批记录 |
| 04 | `04_transfer_authorization_and_ledger.sql` | 转账授权字段与资金流水相关结构 |
| 05 | `05_agent_tool_audit.sql` | Agent 工具调用审计记录 |
| 06 | `06_subscription_cancellation.sql` | 订阅取消业务 |
| 07 | `07_workflow_registry.sql` | 动态工作流登记 |

上述脚本包含本地演示库的初始化或增量变更。执行前应备份并确认目标数据库；不要在已有业务数据的库上重复执行初始化脚本。

## 多用户业务测试库迁移

`08` 至 `11` 是面向已具备基础业务结构的独立测试库增量迁移。当前部署流程使用 `bankpilot_day7_test`，应先备份 Day 6 基础库并恢复到该测试库，再按以下顺序执行：

1. `08_user_authentication.sql`
2. `checks/check_recipient_uniqueness.sql`（只读检查）
3. `09_aa_collections.sql`
4. `10_scheduled_transfers.sql`
5. `11_business_audit.sql`
6. `permissions/grant_test_database_access.sql`（管理员审核后执行）
7. `checks/check_business_state.sql`（只读核查）

注意：`08` 至 `11` 文件内使用 `bankpilot_day7_test`。不要将其直接执行到 `bankpilot`，也不要把测试库迁移误当成全新数据库初始化流程。

## 检查与演示数据

- `checks/` 中的脚本用于核对账户、订单、流水、收款人唯一性、工作流及审计状态。
- `fixtures/seed_demo_subscriptions.sql` 用于本地测试账号准备订阅数据。
- `fixtures/reset_demo_accounts.sql` 会重置模拟账户及相关演示记录，只能在确认无重要数据的本地演示库中手动执行。

## 安全注意事项

- SQL 迁移不会由应用启动过程自动执行。
- 迁移前先备份，并确认 `USE` 指定的数据库名称。
- 不要提交包含真实密码、访问令牌或个人信息的 SQL 文件。
- 本目录脚本仅用于模拟银行项目，不应用于真实银行生产数据库。