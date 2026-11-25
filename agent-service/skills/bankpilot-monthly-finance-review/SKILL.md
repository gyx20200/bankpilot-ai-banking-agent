---
name: bankpilot-monthly-finance-review
description: 基于当前用户真实模拟银行数据，联合查询指定月收支和异常规则；不确认盗刷、不修改资金。
---

# 月度财务体检

## 触发条件
用户要求“某年某月的财务体检、收支和异常一起检查”，且**当前消息明确提供年月**。

## 输入
- `month`：YYYY-MM，必须能从当前轮验证，不能凭历史决定跨期资金操作。

## 只读步骤
1. 使用已授权 MCP `bank_monthly_analytics(month)`，读取 Java/MySQL 月度统计。
2. 使用已授权 MCP `bank_transaction_anomalies(month)`，读取 Java 规则事件。
3. 合并查询结果，仅报告确定的收支金额和规则提示条数。

## 边界
不认定用户遭遇诈骗；不冻结卡、不转账、不自动创建工单。MCP 与 Java 用户身份仍须有效。不得从本文件生成新的资金工具。
