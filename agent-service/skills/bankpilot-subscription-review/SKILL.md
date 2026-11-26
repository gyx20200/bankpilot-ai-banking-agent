---
name: bankpilot-subscription-review
description: 查看当前用户订阅代扣和交易流水，不自动取消、代扣或认定重复扣费。
---

# 订阅巡检

## 触发条件
用户明确要求“检查我的订阅和最近账单”“订阅巡检”，只需查看，不要取消订阅。

## 只读步骤
1. MCP `bank_list_subscriptions()` 读取本人订阅代扣列表。
2. MCP `bank_get_transactions()` 读取本人模拟流水。
3. 显示订阅总数、ACTIVE 数量和返回的流水数量。

## 边界
不自动取消订阅，不自行认定重复扣费，不执行支付或订阅授权。需要取消时仍走原 D6 人工确认及 Java 授权流程。
