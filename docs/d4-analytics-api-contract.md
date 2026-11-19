# BankPilot 2.0 D4 账单分析接口交接

基线：main df81aeb；成员 B 上下文分支 feature/d4-context-review（ac8b28c9a7）。新增文件可直接复制到仓库，不替换 D3 源码，不增加数据库表，不运行历史 SQL 初始化。使用 bankpilot_day7_test。两个接口都只读，认证使用现有 Bearer Token，Java 从 AuthenticatedUser.id() 决定用户，不能从请求提供 userId。统计范围与现有月度接口相同：当前用户 ACTIVE 账户，IN/OUT 为流水方向（包括转账等非消费性支出；不等于纯消费）。

## 接口一
GET /api/demo/analytics/annual?year=2026
任务名及 executor_key: annual_analytics，LOW，year 为字符串 YYYY（1000 至数据库当前年份）。

返回字段：year (string), currency (CNY), totalIncome, totalExpense, netCashFlow (JSON number), categories [{name, amount, count}], monthlyBreakdown [{month, totalIncome, totalExpense}], periodType (YEAR_TO_DATE / FULL_YEAR), source (mysql), periodStart, periodEndExclusive（数据库业务本地时间 ISO 字符串，无时区偏移）。

所有时间范围为 [start, end)。当年截止数据库查询时刻，未来月份不返回；已发生的空月份为零。过去年度返回 12 个月。金额以 BigDecimal 运算。分类只统计 OUT，不包含 IN。

## 接口二
GET /api/demo/analytics/anomalies?month=2026-10
任务名及 executor_key: transaction_anomalies，LOW，month 为 YYYY-MM；不允许未来月份。

返回字段：month, currency, scannedCount (扫描的 OUT 记录数), anomalyCount (规则事件数), items [{transactionId, ruleCode, amount, category, merchantName, occurredAt, relatedTransactionId, reason}], largeOutflowThreshold (1000.00), duplicateWindowMinutes (10), source (mysql), periodStart, periodEndExclusive。

规则：LARGE_OUTFLOW（金额 >=1000 元）；POSSIBLE_DUPLICATE（同账户、非空商户、去首尾空白后忽略大小写、同金额、相邻同组支出间隔 <=10 分钟，含恰好10分钟）。重复事件只记录较晚交易，relatedTransactionId 指向前一笔；同一交易可命中两条规则。仅检查当前指定月份范围，不跨月比较。如果超过10000笔支出，返回422而不是部分结果。规则命中不等于欺诈或重复扣款已确认。

两接口：未登录401、非法期间400；数据库错误不得伪装成零结果。金额从 Java 获取，不由模型计算。开发和联调不插入或修改真实模拟账本；JUnit 使用项目原有 H2 数据和事务回滚。

## 成员 B 对接清单

- 保留已经实现的 build_planner_messages(), contextual_month_from_history(), validate_plan() 和 Runtime Context。
- task_registry.py 新增两个 LOW 任务。task_planner.py Task.year、TASK_PARAMETER_SCHEMAS.year、合法字段检查增加 year；分别校验年度和异常月份来源、格式、上下限，不把某个明确年月中的年份误判为独立年度任务。D4 只要求月度续问，年度和异常任务要求显式期间。敏感写任务仍根据当前原话校验，不从历史继承。
- banking_client.py 使用 READ_URL 和 _request() 增加 get_annual_analytics(year,bearer) 与 get_transaction_anomalies(month,bearer)；urlencode 参数，检查响应期间、必需字段、金额、列表、计数和 source。
- dynamic_read_workflow.py 扩展 READ_TASK_TYPES 与 execute_read()，主 dynamic_graph 自动复用该执行器。独立 read_graph 未接入上下文不影响主页面 D4。
- assistant_history.py 从 results 两个新任务生成实际文字摘要，年度当年标明累计，异常标明规则事件而非盗刷。保持 D3 assistantPersisted。
- DynamicWorkflowCard.vue 添加对应展示分支、任务名；可选各新增独立卡片组件。
- Python Mock、实际 Java/MySQL 联调、Vue build、D3 回归。

## 验证命令

项目根目录 PowerShell：

```powershell
mvn -f .\banking-backend\pom.xml "-Dtest=AnnualAnalyticsTest,TransactionAnomalyTest" test
mvn -f .\banking-backend\pom.xml test
```

已做：Java 21 使用轻量 Spring/JDBC 类型桩编译两个生产 Controller，并运行独立规则 smoke 检查；未执行完整 Spring Boot/JUnit/H2/MySQL 测试（环境缺少 Maven 及真实依赖）。JUnit 两份各5项测试，实际结果以本地为准。
