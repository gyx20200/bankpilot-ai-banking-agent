@'
# BankPilot V2 D8 Integration Report

## 1. 集成范围
- 成员 A：公开金融知识语料及来源治理
- 成员 B：RAG 检索、Agent 工具路由及 Vue 知识证据展示
- 本地集成修复：银行只读任务路由、工作流身份测试隔离

## 2. 资料审核
- APPROVED_SOURCES：4
- SECTIONS：6
- Embedding：BAAI/bge-small-zh-v1.5
- Chroma 索引构建：待附最终构建记录

## 3. 自动化测试
- Python 全量：325 passed，4 warnings
- RAG + Planning：127 passed
- Java：最近一次 75 tests，16 errors，待修复并重新验证
- Vue build：待记录实际结果

## 4. RAG 检索质量
- Recall@3：待填写实际评测输出
- 官方引用检查：待完成正向用例验收
- 证据不足安全拒答：已观察到预期行为

## 5. 端到端验收
- 个人余额查询：待记录最终响应
- 金融知识查询：待完成正向验证
- 余额与知识组合查询：待验证
- 个人数据隔离：待验证

## 6. 数据一致性
- MySQL 数据库：bankpilot_day7_test
- 账户余额、转账订单、交易流水：待与 D8 前基线核对
- LangGraph Checkpoint：保留原 SQLite 文件

## 7. 已知问题与结论
- Java Spring 测试上下文初始化异常尚未排除
- 端到端验收尚未全部完成
- 当前报告为阶段性记录，暂不判定 D8 全部通过
'@ | Set-Content -Path .\docs\d8-integration-report.md -Encoding utf8