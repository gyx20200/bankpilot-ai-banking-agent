# BankPilot Day 7 Java + MySQL 完整安装与联调指南

**适用分支：** `feature/day7-backend`；**基线：** 队友 Day 7 Agent/Vue 已合并至最新 main。本文命令以 Windows PowerShell、MySQL Workbench、JDK21、Maven、MySQL8 为例。**仅本地模拟银行**。

## 0. Git 及文件落地（务必先完成）

```powershell
cd "$HOME\Projects\bankpilot-ai-banking-agent"
git switch feature/day7-backend
git status -sb
git fetch origin --prune
git merge --ff-only origin/main
```

确认工作区干净。将提供的 ZIP 解压到 `$env:TEMP\bankpilot-day7-final` 后，以压缩包中的**实际**补丁位置为准：

```powershell
$patch="$env:TEMP\bankpilot-day7-final\day7-changes.patch"
git apply --check $patch
# 只有检查通过才执行：
git apply $patch
git status -sb
git diff --check
```

若补丁基线不一致，停下来查看差异，**不要 `git reset --hard`、不要覆盖队友 Python/Vue、更不要直接强制推送 main**。

## 1. Day 6 数据库备份与隔离

1. Workbench → **Server → Data Export**，备份 Day 6 `bankpilot` 全部结构及数据到本地 SQL 文件。
2. 单独创建 `bankpilot_day7_test`：

```sql
CREATE DATABASE IF NOT EXISTS bankpilot_day7_test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

3. **从备份恢复至该测试库**。注意 MySQL dump 可能有 `CREATE DATABASE bankpilot` / `USE bankpilot`，先检查再导入，确保不会意外重置原库。
4. 测试库执行并核对：

```sql
USE bankpilot_day7_test;
SELECT DATABASE();
SELECT id,display_name FROM users;
SELECT id,user_id,balance FROM accounts ORDER BY id;
SHOW CREATE TABLE transfer_orders;
```

5. 再在 Workbench 中按顺序一次性执行以下增量 SQL（选择已恢复的测试库）：

```text
database/day7_01_auth.sql
database/day7_02_recipients.sql  （仅检查）
database/day7_03_aa.sql
database/day7_04_schedule.sql
database/day7_05_audit.sql
```

6. 用 MySQL 管理员执行 `database/day7_06_test_db_grants.sql`，为 `bankpilot_app@localhost` 提供测试库权限。**不要将真实数据库密码写入文件或 Git。**
7. 运行 `database/day7_check.sql`，保留结果截图。SQL 是增量迁移，**不能再次执行 Day1 init.sql**，也不要重复执行已经创建的表。

## 2. Java 启动和测试

关闭此前的 Java 8080 端口服务；打开新 PowerShell：

```powershell
cd "$HOME\Projects\bankpilot-ai-banking-agent\banking-backend"
$env:DB_PASSWORD = Read-Host 'bankpilot_app 数据库密码'
$env:SPRING_DATASOURCE_URL = 'jdbc:mysql://127.0.0.1:3306/bankpilot_day7_test?connectionTimeZone=UTC&forceConnectionTimeZoneToSession=true'
$env:BANKPILOT_DAY7_JOBS_ENABLED = 'false'
$env:BANKPILOT_DEMO_OTP_DEBUG_ENABLED = 'true'

mvn clean test
mvn spring-boot:run
```

> 注意：Spring Boot 配置绑定名称由 `application.properties` 定义；Java OTP 调试开关的 `-D` 是**仅本地**测试使用，正式演示关闭。此处所有资金均为模拟数据。若 MySQL/JDBC 使用不同会话时区，核验 UTC 时间转换；如偏移 8 小时，停止预约测试，先统一连接和 DB 时区。

如果测试仍依赖 Day6 的演示密码，请在本地环境设置 `BANKPILOT_DEMO_LOGIN_PASSWORD` 或使用 `-Dbankpilot.demo.login.password=...`（不要把密码复制进日志或源码）。

## 3. 为旧用户绑定可登录凭证（可选，推荐三用户联调时使用）

原数据库 `users.id=1` 为张小明、`users.id=2` 为李四，但之前没有 `user_credentials`。**仅在本地测试库**可以打开以下功能，为两位旧用户绑定新登录凭证，保留既有账户余额、流水和订阅：

```powershell
$env:BANKPILOT_DAY7_LEGACY_BOOTSTRAP_ENABLED = 'true'
$env:BANKPILOT_DAY7_LEGACY_XIAOMING_PASSWORD = Read-Host '设置张小明演示密码'
$env:BANKPILOT_DAY7_LEGACY_XIAOMING_PHONE    = Read-Host '张小明唯一测试手机号'
$env:BANKPILOT_DAY7_LEGACY_LISI_PASSWORD     = Read-Host '设置李四演示密码'
$env:BANKPILOT_DAY7_LEGACY_LISI_PHONE        = Read-Host '李四唯一测试手机号'
```

**重要：** 本次补丁的 `application.properties` 已包含以下环境变量映射；不需要再手动添加。为便于核对，映射内容如下：

```properties
bankpilot.day7.legacy-bootstrap.enabled=${BANKPILOT_DAY7_LEGACY_BOOTSTRAP_ENABLED:false}
bankpilot.day7.legacy-xiaoming.password=${BANKPILOT_DAY7_LEGACY_XIAOMING_PASSWORD:}
bankpilot.day7.legacy-xiaoming.phone=${BANKPILOT_DAY7_LEGACY_XIAOMING_PHONE:}
bankpilot.day7.legacy-lisi.password=${BANKPILOT_DAY7_LEGACY_LISI_PASSWORD:}
bankpilot.day7.legacy-lisi.phone=${BANKPILOT_DAY7_LEGACY_LISI_PHONE:}
```

启动一次后检查原旧用户凭证已存在，后续关闭 bootstrap：

```sql
SELECT u.id,u.display_name,c.username,a.balance
FROM users u JOIN user_credentials c ON c.user_id=u.id
JOIN accounts a ON a.user_id=u.id ORDER BY u.id;
```

另通过 `/api/auth/register` 注册张三，使其获得独立的 `¥10000.00` 模拟初始资金。如需要让新注册的张三也能演示“取消视频会员”，可**额外**在测试库手动执行 `database/day7_optional_test_subscriptions.sql`；默认注册不伪造已有订阅。也可注册全新的三位测试用户，无须 bootstrap；但旧 userId=1 的历史业务将仍需旧 demo-login 才可访问。

## 4. 先以 PowerShell 验证 Java 认证 / 当前用户

```powershell
$base='http://127.0.0.1:8080'
$loginPassword=Read-Host '张小明登录密码'
$login=Invoke-RestMethod "$base/api/auth/login" -Method POST -ContentType 'application/json' `
  -Body (@{username='xiaoming';password=$loginPassword}|ConvertTo-Json) -ErrorAction Stop
$headers=@{Authorization="Bearer $($login.token)"}
Invoke-RestMethod "$base/api/auth/me" -Headers $headers | ConvertTo-Json
Invoke-RestMethod "$base/api/demo/balance" -Headers $headers | ConvertTo-Json
```

验收：`/me` 显示真实 `userId`，`/balance` 仅当前人数据；退出后旧 token `401`，不能使用张小明 Token 操作张三或李四的银行订单。

新用户注册示例（操作前替换为测试手机号及密码）：

```powershell
$regPassword=Read-Host '张三注册密码'
$regBody=@{username='zhangsan';password=$regPassword;fullName='张三';phone='13800138003'}|ConvertTo-Json
Invoke-RestMethod "$base/api/auth/register" -Method POST -ContentType 'application/json; charset=utf-8' `
  -Body ([Text.Encoding]::UTF8.GetBytes($regBody))
```

**不要重复注册已经存在的用户名；出现 409 正常表示唯一约束生效。**

## 5. 收款人 / 备注转账联调

张小明登录后测试：

```powershell
$found=Invoke-RestMethod "$base/api/transfers/recipients/search?name=%E5%BC%A0%E4%B8%89" -Headers $headers
$found | ConvertTo-Json -Depth 5
# 使用刚查到的唯一 recipientId，不能把它直接当作 payeeId
$person=Invoke-RestMethod "$base/api/transfers/recipients/confirm" -Headers $headers -Method POST `
   -ContentType 'application/json' -Body (@{recipientId=$found[0].recipientId}|ConvertTo-Json)
$person | ConvertTo-Json
```

确保返回 `id` 为可信 `payeeId`；接下来发送自然语言「给张三转100元」「给李四转200元，备注周末聚餐」「给张三转1500元」，通过 Vue 确认、OTP 及实际 Java 执行。核对付款账户 -X、收款账户 +X，`transfer_orders.remark`、两侧 `transactions` 和唯一银行订单 ID。手机号查询 `?phone=<注册手机号>` 应精确返回一个候选。两位同名应返回两个候选供选择。

## 6. AA 三用户端到端联调

1. 张小明（`xiaoming`）登录 Vue，输入：`我和张三、李四聚餐一共300元，三个人AA，帮我收款`。
2. Java `/api/aa/prepare` 创建 **DRAFT**，两条 item 各 ¥100；此时余额不变；张三的 inbox 不应出现 DRAFT。
3. 张小明在 Vue 明确点击发布后，`/api/aa/{id}/publish` → **PUBLISHED**。
4. 张三（`zhangsan`）登录，打开 AA 中心查看本人 inbox，点击付款；Java 创建唯一绑定的旧转账订单。YELLOW 要确认，RED 要 OTP；资金成功后张三 -100，张小明 +100，item → PAID。
5. 李四（`lisi`）登录，打开 AA 中心，拒绝自己那条 item → DECLINED，李四余额不变。
6. 张小明重新登录并刷新 outgoing，应看到 `receivedAmount="100.00"`，两条 item 分别 PAID、DECLINED。
7. 再次点已付款 item、换其他用户 Token 请求该 item，必须被拒绝或幂等返回原结果，不能产生第二笔成功转账。

Workbench 只读检查：

```sql
SELECT c.id,c.initiator_user_id,c.status,i.id AS item_id,i.payer_user_id,
 i.amount,i.status AS item_status,i.transfer_order_id,t.status AS bank_status
FROM aa_collections c JOIN aa_collection_items i ON i.collection_id=c.id
LEFT JOIN transfer_orders t ON t.id=i.transfer_order_id
ORDER BY c.id DESC,i.id DESC LIMIT 20;
SELECT id,transfer_order_id,account_id,direction,amount FROM transactions
WHERE transfer_order_id IS NOT NULL ORDER BY id DESC LIMIT 20;
```

## 7. 定时转账（所有金额统一 OTP）

联调早期 **保持** `$env:BANKPILOT_DAY7_JOBS_ENABLED='false'`，先检查 `prepare` → `PENDING_AUTH`、申请 OTP、模拟验证码、本人 `authorize` → `SCHEDULED`，**此时账户余额不得改变**。

然后停掉 Java，调整：

```powershell
$env:BANKPILOT_DAY7_JOBS_ENABLED='true'
mvn spring-boot:run
```

在 Vue 输入：`2分钟后给李四转10元，备注联调预约`，让 Agent 产生 `YYYY-MM-DDTHH:MM:SS+08:00`；银行按 ISO 时间创建预约。**10 元也必须 OTP。** 浏览器关闭 / Python 停掉后，Java 依赖 MySQL 独立调度。查询 `/api/scheduled-transfers/mine` 和 `/api/scheduled-transfers/{id}`：到期只应执行一笔资金转账，`status=SUCCESS`、`orderId` 非空、双方余额及流水对应。未授权或取消的预约不扣款。

另测：
- **超 60 秒错过执行时间**：关 Java，重新开启时应 `MISSED`，不追扣。
- **余额不足**：`FAILED`，不自动重试。
- **连续两次调度同一预约**：只创建一个成功资金订单、双边流水各一条。
- **异常未知**：`UNKNOWN`，不得再次自动扣款，人工只读核实原银行订单。
- **长时间未来预约**：没有 30 天业务上限，验证创建后持久保存，取消后不会执行。

SQL：

```sql
SELECT id,owner_user_id,amount,status,scheduled_at_utc,
transfer_order_id,last_error_code FROM scheduled_transfers ORDER BY id DESC LIMIT 20;
SELECT schedule_id,auth_method,covered_risk,status,valid_until,revoked_at
FROM scheduled_transfer_authorizations ORDER BY id DESC LIMIT 20;
SELECT id,user_id,amount,status,remark FROM transfer_orders ORDER BY id DESC LIMIT 20;
```

## 8. 队友 FastAPI 与 Vue 联调环境

让队友将 Agent 所有银行 URL 统一切至 Java：

```powershell
cd "$HOME\Projects\bankpilot-ai-banking-agent\agent-service"
$env:BANK_API_MODE='java'
$env:BANK_API_BASE='http://127.0.0.1:8080/api/demo'
$env:BANK_TRANSFER_API_BASE='http://127.0.0.1:8080/api/transfers'
$env:BANK_AUTH_API_BASE='http://127.0.0.1:8080/api/auth'
$env:BANK_CANCELLATION_API_BASE='http://127.0.0.1:8080/api/subscription-cancellations'
$env:BANK_AA_API_BASE='http://127.0.0.1:8080/api/aa'
$env:BANK_SCHEDULE_API_BASE='http://127.0.0.1:8080/api/scheduled-transfers'
& '.\.venv\Scripts\python.exe' -m pytest -q
& '.\.venv\Scripts\python.exe' -m uvicorn main:app --host 127.0.0.1 --port 8000
```

另开前端终端：

```powershell
cd "$HOME\Projects\bankpilot-ai-banking-agent\frontend"
npm ci
npm run build
npm run dev
```

如果 `npm ci` 因 `esbuild.exe EPERM` 失败，先结束占用该前端项目的 Vite 进程，再重新安装。浏览器打开 `http://127.0.0.1:5173`。**Mock 的 18080 不要与 Java 的 8080 混用。**

## 9. Day6 回归 / 合并分支

测试余额、流水、月度账单、订阅、本人订阅取消、普通转账、YELLOW/RED、LangGraph 多任务、Token 过期后登录。同一用户重新登录应能根据 Java 订单查询自己的银行状态；Python 进程内旧 checkpoint 丢失不得伪装为已恢复。按用户 `userId` 校验工作流 owner；换账号后不得使用旧账号的审批卡。

```powershell
cd "$HOME\Projects\bankpilot-ai-banking-agent"
git branch --show-current
git status -sb
git diff --check
git add -- banking-backend database/day7_*.sql docs/day7-java-agent-contract.md docs/Day7_后端部署联调指南.md
git diff --cached --stat
git diff --cached --check
git commit -m 'feat(day7): multi-user Java banking AA and durable scheduled transfer'
git push -u origin feature/day7-backend
```

PR 阶段合并进 `integration/day7-joint`，双方跑全量测试和数据库核对，再 PR 合并到 main。**不要提交 `.env`、真实密码、Token、OTP、MySQL 备份，不要强制推送 main。**

## 10. 重要验收边界

目前生成的 Java/SQL 已完成源码层增量开发与静态语法检查，但**当前运行容器没有 Maven、Spring 依赖和 MySQL 实例**，无法证明 Java JUnit 及 MySQL/Agent 真实联调成功。以上验收必须在本地运行，任何报错以日志/实际 SQL 为准。若一个模块没有通过实际银行事务和双边流水核对，不能向队友宣称该模块已完成端到端验收。
