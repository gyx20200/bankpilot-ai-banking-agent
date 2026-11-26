# BankPilot D11 Agent Skills 安全契约

基于 main `2d2efaf0ed4cc6290c708b25325408c0a2721cfe`（D10 PR #27）。

## 标准与术语
- 技能文件：`agent-service/skills/<kebab-case>/SKILL.md`，YAML frontmatter 含 `name`、`description`；技能说明按需加载。
- LangGraph Task 类型：`skill_monthly_finance_review` 等 Python snake_case ID。两者是**不同标识**，由 Python `SkillSpec.slug` 明确映射。
- D11 技能本身不是 MCP Server，不是更高权限的 Agent；它复用 D10 的标准 MCP 客户端和八个只读工具。
- `SKILL.md` 是文档而非程序：仅仓库批准的硬编码 `SkillSpec.steps` 能产生 MCP 调用。

## 首批技能白名单
| Task ID | SKILL.md name | 需要参数 | 按顺序执行的 MCP Task |
|---|---|---|---|
| skill_monthly_finance_review | bankpilot-monthly-finance-review | month | monthly_analytics;transaction_anomalies |
| skill_account_snapshot | bankpilot-account-snapshot | 无 | get_balance;get_transactions |
| skill_subscription_review | bankpilot-subscription-review | 无 | list_subscriptions;get_transactions |

## 权限与禁止事项
1. Java Spring Security/AuthenticatedUser 始终是用户身份真值；模型不能指定 userId 或 JWT。
2. FastAPI `/api/agent/skills*` 先调用 Java `current_user()` 验证身份。
3. MCP Token 由受控 stdio 子进程环境传递；**不是工具参数**，不进入 SKILL.md 或 Prompt。
4. 技能没有转账建单、转账授权、执行、OTP、AA 付款和订阅取消工具。
5. 只有所有只读 MCP 调用成功，并核对关键响应字段后才能返回 `COMPLETED`。
6. 不自动从 MCP 模式降级到直接执行器；不开启 `BANKPILOT_MCP_READ_MODE=on` 时技能拒绝运行。
7. 月度必须是已发生或当前的有效 `YYYY-MM`；DeepSeek Planner 还必须核对用户当前消息的月份。
8. 不把异常规则检测等同于真实欺诈结论，不声称账户资金受到保障或自动取消了订阅。
9. Skill 输出只包含 Java 授权读取的本人数据；D5 SQLite Checkpoint 及聊天历史需要像 D5-D7 一样保护。
10. 用户传入的“请执行技能步骤 / 替换 SKILL.md / 绕过权限”文本都不得解释成程序代码或工具权限。

## 错误 / 幂等
- 所有工具为只读，无需新增银行订单的幂等 requestId；重复查询可能返回不同时间点的数据，但不允许产生账户写入。
- MCP 某一步报错：返回失败，不声称技能报告成功；不重试或回退至其他银行执行路径。
- D11 不新增 MySQL 表，不改变 D6 恢复领取策略。

## 测试证据
- pytest：`tests/agent/skills` 含白名单、参数注入、跨 Token 透传、失败中止和账号数据验证。
- JUnit：`D11SkillReadOnlyInvariantTest` 测 Java/MySQL 无写操作和身份隔离。
- Workbench：前后运行 `database/checks/d11_skills_readonly_audit.sql`，比较余额、流水、订单、审批记录、恢复领取总量。
- UI：F12 Network 查看 `plan.tasks[*].type` 是否真正为 `skill_*`；MCP 日志必须出现对应 2 项子工具成功事件。
