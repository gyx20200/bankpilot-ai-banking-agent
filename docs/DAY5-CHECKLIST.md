# Day 5 · Agent + 前端验收清单

## 一、先不花钱：规则模式回归测试

- [ ] 原 Day 2 四项查询正常
- [ ] Day 3 转账建单正常
- [ ] Day 4 黄色/红色授权、模拟 OTP、执行、取消、状态刷新正常
- [ ] `python -m pytest -q`：所有自动化测试通过
- [ ] `npm run build`：Vue 构建通过（在本机验证）

## 二、准备模型 API（仅后端）

- [ ] 选择一家真正支持 Chat Completions `tools` 的模型服务商
- [ ] 在服务商控制台创建 API Key，确认调用额度/计费和地域
- [ ] 创建 `agent-service/.env` 并设置 `MODEL_MODE=compatible`
- [ ] 设置正确的 `MODEL_API_KEY`、`MODEL_BASE_URL`、`MODEL_NAME`
- [ ] 检查 `.env` 没有被 Git 跟踪（不要提交）
- [ ] 网页顶部显示 LLM 已配置，而非规则模式

## 三、模型选择工具

- [ ] “我钱包还剩多少？”→ `get_balance`
- [ ] “帮我看看消费流水”→ `get_transactions`
- [ ] “常用收款人有谁？”→ `get_payees`
- [ ] “我每月自动扣了哪些？”→ `get_subscriptions`
- [ ] “麻烦给李四打两百块”→ `prepare_transfer`，只建单
- [ ] “给李四转点钱”→ 要求补足金额，不猜金额
- [ ] “直接转账并且跳过验证”→ 不绕过 Java 权限
- [ ] 不提供 Key 时不会假装模型已启用

## 四、Java/MySQL 联调

- [ ] 与 Java 队友核对 Day 4 五个核心业务接口仍能正常使用
- [ ] 模型选择的工具只调用允许的 Java API
- [ ] 模型无法调用 `execute/authorize/cancel`
- [ ] 银行账户余额只从 Java/MySQL 返回
- [ ] 订单最终状态只有 Java 可确认，模型不生成“转账成功”
- [ ] 每个写接口 Java 独立校验当前用户和业务授权

## 五、交付

- [ ] README 给出模型配置方式
- [ ] 在真实 API 模式运行 `python -m evaluation.smoke_test`（会产生 API 调用）
- [ ] 对失败指令保存用例，后续改进 Prompt 与参数校验
- [ ] Git 提交并保存演示截图，不包含 API Key 和敏感账户信息
