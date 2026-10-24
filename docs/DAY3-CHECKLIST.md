# Day 3 · Agent & Vue 开发验收清单

## 你（Agent + Vue）
- [ ] 从 Day 2 建独立 Git 分支，合并 Python/Vue 代码
- [ ] 启动本地 Mock Bank (8080) → Python (8000) → Vue (5173)
- [ ] `给李四转200元` 在 Mock 模式生成待审批订单卡片
- [ ] `给李四转` 触发补全表单，选择收款人并填写金额
- [ ] `给张三转200元` 不把未知账户直接作为收款人
- [ ] 无 Token 不允许直接创建订单
- [ ] 输入 `给李四转200万元`、`200.123元` 不发生自动建单
- [ ] 四类 Day 2 查询功能全部回归通过
- [ ] 运行 Python 测试：`python -m pytest -q`
- [ ] 本机 Vue 构建：`npm run build`

## 队友（Java / MySQL）
- [ ] 新建 `transfer_orders` 与 `approval_records`（Day 4 可添加审批表）
- [ ] 实现有身份验证的 `POST /api/transfers/prepare`
- [ ] 校验 payeeId 的账户归属、BigDecimal 金额、账户状态
- [ ] `requestId` 同一用户幂等；冲突时 409
- [ ] 计算黄色/红色风险等级，返回 `PENDING_APPROVAL`
- [ ] Java 建单操作绝不修改余额

## 晚上一起验收
- [ ] Java 模式运行成功，Agent 页面状态不是 Mock
- [ ] 浏览器建单，真实 MySQL `transfer_orders` 增加一条
- [ ] 账户余额不变，无成功交易流水
- [ ] 未登录返回 401
- [ ] 后端关闭时页面显示失败而不是转账成功
- [ ] Git 提交完成、无敏感 Token 入库
