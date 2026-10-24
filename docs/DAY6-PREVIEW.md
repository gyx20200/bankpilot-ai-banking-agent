# Day 6 计划：LangGraph 跨场景任务（暂未开发）

明天实现 **一个受控、固定结构** 的跨场景工作流：

用户输入：“分析我最近的消费，查一下有哪些订阅，帮我取消视频会员代扣。”

1. 意图结构化提取：账单分析 / 订阅查询 / 订阅取消候选。
2. LangGraph 中并行调用读工具：交易流水和订阅列表。
3. Java 或 Python 做确定性汇总，不让 LLM 自行加减财务金额。
4. 给出用户确认卡片；通过 LangGraph `interrupt()` 暂停。
5. 用户确认后恢复 `thread_id`，Java 端重新认证/授权并执行**模拟代扣取消**。
6. 展示 Java 的真实业务结果和审计事件，拒绝/超时不报告成功。

优先增加 `GET /api/analytics/monthly` 和 Java 审批后的 `POST /api/subscriptions/{id}/cancel` 接口。
**注意：Day 6 的功能尚未实现，不能当作 Day 5 已完成项目的能力。**
