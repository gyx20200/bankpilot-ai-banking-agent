# BankPilot Day 7 阶段 1：模拟银行后端测试说明

## 适用代码版本

- Git 分支：`feature/day7-agent`。
- 已应用《Day7 阶段1 完整开发补丁》和《Day7 登录注册 UI 视觉优化补丁》。
- 本补丁是**在上述两份补丁之后**应用的增量补丁；没有修改现有 Vue、LangGraph、FastAPI 银行代理业务代码。
- 后端是独立文件 `agent-service/mock_day7_backend.py`，不修改原 `mock_backend.py`，不修改 Java/MySQL。

## 启动顺序（Windows PowerShell 示例）

### ① 配置 Agent 的银行接口地址

在 `agent-service/.env` 中，将以下五项替换为本地 Mock 地址（如果文件尚不存在，从 `.env.example` 复制）。

```ini
BANK_API_MODE=mock
BANK_API_BASE=http://127.0.0.1:18080/api/demo
BANK_TRANSFER_API_BASE=http://127.0.0.1:18080/api/transfers
BANK_CANCELLATION_API_BASE=http://127.0.0.1:18080/api/subscription-cancellations
BANK_AUTH_API_BASE=http://127.0.0.1:18080/api/auth
```

可参考 `agent-service/.env.stage1-mock.example`。**保留你原有的 DeepSeek `MODEL_*` 配置**，不要把 API Key 发给任何人。

**注意：** 后端接口地址在 Agent 启动时读取，修改 `.env` 后必须重启 FastAPI；不要只刷新浏览器。

### ② 启动专用模拟银行（终端 1）

在项目根目录执行：

```powershell
cd agent-service
$env:BANKPILOT_STAGE1_MOCK="1"
python -m uvicorn mock_day7_backend:app --host 127.0.0.1 --port 18080
```

在浏览器访问 `http://127.0.0.1:18080/health`，应返回 `mode: LOCAL_MOCK_ONLY`。

> macOS / Linux 则运行：
> `BANKPILOT_STAGE1_MOCK=1 python -m uvicorn mock_day7_backend:app --host 127.0.0.1 --port 18080`

### ③ 启动 Agent（终端 2）

```powershell
cd agent-service
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

访问 `http://127.0.0.1:8000/api/agent/health`，`bankMode` 应为 `mock`。

### ④ 启动 Vue（终端 3）

```powershell
cd frontend
npm run dev
```

打开 `http://127.0.0.1:5173`，应该能看到你选定的蓝白渐变登录/注册 UI。

## 必须手工检查的阶段 1 场景

| 编号 | 操作 | 预期结果 |
|---|---|---|
| A01 | 注册 `zhangsan` / 张三 / 13800138000 | 提示注册成功，停留在登录界面，不自动登录 |
| A02 | 使用相同用户名或手机号再注册 | 拒绝并显示冲突提示 |
| A03 | 使用张三账号错误密码登录 | 拒绝，不进入工作台 |
| A04 | 使用张三账号正确密码登录 | 进入银行工作台，显示当前用户张三 |
| A05 | 张三查询余额 | 初始 `¥10,000.00`，账户属于张三 |
| A06 | 张三退出，使用另一用户名注册李四并登录 | 显示李四；看不到张三之前的聊天和业务卡片 |
| A07 | 李四查询余额、订阅和流水 | 只返回李四的数据；初始 `¥10,000.00`，有自己独立的模拟订阅 |
| A08 | 张三重新登录 | `userId` 不变；以前的银行模拟订单（如果有）仍归张三所有 |
| A09 | 退出后试图用旧 Token 查询 `/me` | 返回 `401` |
| A10 | 不输入 Token 直接调用余额/订阅接口 | 返回 `401` |
| A11 | 刷新浏览器 | Token 仅保存在内存，页面回到登录态 |

**注册字段：** 用户名、姓名、11 位手机号、密码、确认密码；用户名最少3位、密码最少8位。模拟账户初始余额每人 ¥10,000。

### 可选 Day 6 业务回归（需 DeepSeek 正常连接）

先注册张三与李四，登录张三后可以在聊天中尝试：

- “我的余额是多少？”
- “查询最近交易和常用收款人”
- “查询自动扣费”
- “给李四转200元” → YELLOW 明确批准后，张三余额 `9800.00`、李四余额 `10200.00`；两边新增流水
- “给李四转1500元” → RED，模拟 OTP 固定 **246810**（仅本地 Mock），必须先通过申请 OTP 的操作才能校验
- “取消视频会员代扣” → 经审批后，只有张三自己的视频会员变成 `CANCELLED`；李四不变

**注意：** 如果 `.env` 中 `MODEL_MODE=rules` 或没有有效模型 Key，现有 `dynamic` LangGraph 任务会提示“请先配置并启用模型 API”，这是原 Day 6 规划器的既有要求，不是模拟银行认证失败。可以先完成 A01～A11，不影响阶段 1 验收。

## 自动化测试

在 `agent-service/` 目录执行：

```powershell
python -m pytest -q tests/test_day7_mock_backend.py tests/test_day7_auth_proxy.py tests/test_day7_auth_safety.py tests/test_day7_workflow_identity.py
```

`test_day7_mock_backend.py` 通过 FastAPI TestClient 直接调用模拟服务，不需要启动 Java 或 DeepSeek；测试会清理自己创建的内存数据。

## 模拟服务与正式 Java 的边界

- 新服务**不会调用 Java/MySQL**，只在一个 Python 进程的 RAM 中保存注册用户、Token、余额、订单与订阅；重启全部消失。
- 使用独立端口 `127.0.0.1:18080`，只能用专门的环境变量 `BANKPILOT_STAGE1_MOCK=1` 启动；**不要使用 `--host 0.0.0.0`**，不允许对外网发布。
- 模拟 OTP 固定 `246810`，仅用于开发阶段测试；正式 Java 不得沿用固定验证码。
- 模拟转账使用 Python 内存锁和 Decimal；这**不等于**正式银行的事务和安全保证。
- 新增 Mock 对 Day 6 转账/订阅取消仅做本地兼容模拟，**不包含 Day 7 的按姓名/手机号全局搜索、AA 收款、定时转账**，这些属于后续阶段。
- 切回 Java 时把五个 `BANK_*` 地址改回 `127.0.0.1:8080`，`BANK_API_MODE=java`，然后重启 FastAPI，并启动正式 Java/MySQL。旧演示登录接口仍然保留，但新 UI 不显示。

## 已知范围

当 Java 队友尚未实现 Day 7 认证接口时，**阶段 1 只能在模拟银行环境中完成前端+Agent 的逻辑验收**；正式 Java 集成仍需要单独验收。阶段 1 成功后，再开始 Day 7 阶段 2（按姓名/手机号/备注转账）。
