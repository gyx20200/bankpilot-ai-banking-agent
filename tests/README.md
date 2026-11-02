# 测试说明

Python 测试统一从仓库根目录运行，Java 测试保留在 Maven 约定目录。

```powershell
# 仓库根目录（不启动 Java/MySQL，不直接调用大模型）
python -m pip install -r agent-service/requirements.txt
python -m pytest -q

# 指定领域回归
python -m pytest -q tests/agent/planning
python -m pytest -q tests/agent/workflows
python -m pytest -q tests/mock

# Java（部分测试使用嵌入式测试库）
cd banking-backend
mvn test
```

| 目录 | 作用 |
|---|---|
| `agent/planning/` | 模型意图、任务白名单、解析与计划校验 |
| `agent/workflows/` | 任务依赖、图执行、审批与恢复 |
| `agent/banking/` | 银行客户端与交易准备 |
| `agent/api/` | FastAPI 路由与认证代理 |
| `mock/` | 内存银行业务及各类回归 |
| `smoke/` | 需启动 Java/MySQL 的**手动**冒烟脚本 |

> `tests/smoke/` 不在默认 pytest 收集路径中。部分脚本会生成订单或取消模拟订阅，**只允许在可丢弃的本地测试库**中运行。
> 缺少 `langgraph` 或其他依赖时，请先用对应的 Agent 虚拟环境安装 `agent-service/requirements.txt`。
