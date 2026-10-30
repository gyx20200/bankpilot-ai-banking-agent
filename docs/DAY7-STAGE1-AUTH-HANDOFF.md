# BankPilot Day 7 · 阶段 1（Agent + Vue）开发交接说明

> 交付范围：FastAPI 多用户认证代理、Vue 注册/登录/退出、当前用户显示及账户切换清理、LangGraph 用户归属。**未实现 Java/MySQL 身份服务**。本说明描述本次交付的增量代码，不修改旧 Java 业务。

## 1. 源码基线与应用条件

- 源码基于此前上传的 **`bankpilot-project.zip`**（Day 6 联调版，ZIP 中 `.git/HEAD` 为 `main`，ZIP 中 `.git/refs/heads/main` 为 `43953bb6ca008afbc2b978eb58bf169ebed66ef3`）。
- **请以 ZIP 中的实际工作树文件为准**：压缩包内 Git HEAD 不保证 ZIP 工作树没有未提交改动。
- 用户本地应在 `feature/day7-agent` 分支、且**尚未应用先前单独的“阶段 1.1 认证补丁”**时应用本交付补丁；本补丁**已包含 1.1**，不能重复叠加。
- 环境要求：Python 3.11+（按 `agent-service/requirements.txt` 安装）；Node.js 20+，前端按锁文件执行 `npm ci`。Java 必须提供本文件第 3 节所列接口。
- 代码补丁是**项目根目录相对路径**，即在同时含有 `agent-service/` 和 `frontend/` 的目录运行 `git apply`。

## 2. 修改文件及业务原因

| 文件 | 类型 | 修改原因及行为 |
|---|---|---|
| `agent-service/app/auth_api.py` | 新增 | `/api/agent/auth/register/login/me/logout`；参数校验后转发 Java；不创建假用户或 Token。 |
| `agent-service/app/banking_client.py` | 扩展 | Java 认证端点客户端与必要的返回字段校验；保留 Day 6 资金、查询、订阅 API。 |
| `agent-service/main.py` | 轻微修改 | 注册新的认证路由；**保留** `/api/agent/auth/demo-login` 兼容入口。 |
| `agent-service/app/workflow_api.py` | 安全修改 | 每次 start/status/otp/resume 均调用 Java `/api/auth/me` 验证令牌；会话归属由 Token 哈希换为 Java 认证 `userId`；同一用户换 Token 仍可按旧 `threadId` 检查，同名/不同用户不能接管。原审批/授权/执行节点不变。 |
| `frontend/src/components/AuthPanel.vue` | 新增 | 注册/登录表单、二次密码确认、字段校验，不在页面暴露 Token 输入；注册成功后切回登录。 |
| `frontend/src/App.vue` | 修改 | 注册登录状态、`/me` 再确认身份、当前用户名称、退出 Java Token 撤销、401 清理前端状态、隐藏未登录聊天；同时保留现有聊天和审批卡。 |
| `frontend/src/style.css` | 附加 | 注册登录及当前用户区域样式，不替换旧卡片样式。 |
| `agent-service/tests/test_day7_auth_proxy.py` | 新增 | 四种认证代理、请求字段、基础错误输入测试。 |
| `agent-service/tests/test_day7_auth_safety.py` | 新增 | 无效 Java 响应、撤销结果不明确、无凭证和登录失败。 |
| `agent-service/tests/test_day7_workflow_identity.py` | 新增 | 使用隔离的假图只测试 HTTP 身份保护：同一 userId 不同 Token 允许、不同 userId 拒绝、撤销 Token 拒绝。不是完整图集成测试。 |

**明确不修改：** Task Planner、Task Registry、LangGraph 图节点、普通转账金额/风控规则、订阅取消行为、Java/MySQL 数据库。

## 3. Java 队友必须实现的认证契约（新增，当前旧 Java 不具备全部接口）

| Java URL | 方法 | 请求与返回约定 |
|---|---|---|
| `/api/auth/register` | POST | `{"username":"zhangsan","password":"TestPassword123!","fullName":"张三","phone":"13800138000"}` → `{"status":"REGISTERED","userId":3}`。Java 在同一事务中建用户与**唯一账户**，初始余额 ¥10,000。**不得返回 Token**。 |
| `/api/auth/login` | POST | `{"username":"zhangsan","password":"TestPassword123!"}` → `{"token":"...","tokenType":"Bearer","expiresInSeconds":1800,"displayName":"张三"}`。用户身份由 Java 账号密码验证后签发。 |
| `/api/auth/me` | GET | `Authorization: Bearer ...` → `{"userId":3,"username":"zhangsan","displayName":"张三","phoneMasked":"138****8000"}`。必须检查 Token 是否已撤销/过期并返回 `401`。 |
| `/api/auth/logout` | POST | `Authorization: Bearer ...` → `{"status":"logged_out"}`。**Java 必须撤销 Token**；用同一 Token 调 `/me` 返回 `401`。 |

FastAPI 对 Vue 暴露同名逻辑的接口，统一加 `/api/agent/auth/` 前缀。

- 当前 Day 6 Java **仅实现** `/api/auth/demo-login` 和 `/api/auth/logout`。队友须新增 `register`、`login`、`me`，才可以完成真实多用户端到端联调。
- 用 Java Token 识别当前用户，不能相信前端/LLM 的 `userId`，必须按用户隔离余额、流水、账单、常用收款人、订阅、订单和审批。
- 用户名 `[A-Za-z0-9_]{3,32}`；密码 8～128 个字符；手机号 11 位中国大陆格式且唯一；姓名 1～50 字符允许重名；用户名不重复；注册不自动登录。
- 认证错误应使用准确 HTTP 状态：未认证 `401`、无权限 `403`、重复用户名或手机号 `409`、非法输入 `400/422`，登录错误不能泄露账户是否存在。
- 原 `demo-login` **保留用于历史测试**。但新 LangGraph 身份校验**要求 `/me`**；在旧 Java 未提供 `/me` 时，即使通过 `demo-login` 拿到 Token，也不能启动新的受保护工作流。这是安全优先的兼容边界，不能靠 Agent 猜用户 ID 规避。

## 4. 交互流程及异常约定

### 注册

用户进入注册页 → Vue 校验表单 → FastAPI 转发 Java → Java 成功创建账户 → Vue 显示“注册成功，请登录”；**不会自动登录**、不会从注册响应获得 Token。

### 登录

用户填写账号和密码 → FastAPI → Java 签发 Token → Vue 携刚获得的 Token 再调用 `/me` → 确认 `userId` 为有效正整数 → 在内存中保存 Token 和当前用户 → 显示原聊天工作台。若 `/me` 失败，不进入工作台。

### 退出

Vue 调 FastAPI `/logout` → Java 撤销 Token → 返回 `logged_out` 后 Vue 清理 Token、当前用户、聊天、审批卡、OTP 消息等私人 UI。**不对旧 Java 银行订单调用取消**。若银行退出失败，不谎称已完成服务端撤销，保留页面会话并提示重试。若 Token 已过期并收到 `401`，本地会话失效，需要重新登录。

### 会话与审批归属

Token 仅存在于 Vue 组件内存，刷新网页须重新登录。`workflow_api.py` 每次敏感工作流操作调用 Java `/me` 并检查 `userId` 与会话记录一致。退出再登录同一用户，若还持有 `threadId` 且 Python 进程中的检查点仍在 30 分钟窗口，可继续验证并处理该任务。**页面不会持久化或自动找回旧 `threadId`**；如果需要跨刷新找回未完成银行订单，须后续通过 Java 订单列表/状态功能单独实现，不能伪造内存检查点。

## 5. 测试记录（本次交付环境）

- `python -m pytest -q tests/test_day7_auth_proxy.py tests/test_day7_auth_safety.py tests/test_day7_workflow_identity.py` → **5 passed**。其中工作流身份测试采用受控假图，不等价于真实 LangGraph 运行。
- `python -m pytest -q tests/test_transfer_parser.py tests/test_task_planner.py tests/test_task_registry.py tests/test_mock_backend.py tests/test_mock_subscription_cancellation.py` → **69 passed**，验证未直接修改的核心旧功能单元测试。
- 对 `App.vue` 与 `AuthPanel.vue` 进行了 Vue SFC 解析、script 编译和 template 编译检查：**无编译错误**。
- Python `compileall`：通过。
- **尚未完成完整端到端联调**：当前没有 Day 7 Java 认证服务；本次 Linux 验证环境没有 LangGraph 包且无法联网安装；用户 ZIP 中的 Node_modules 为 Windows Rollup 原生二进制，无法在 Linux 完整运行 Vite 打包。需在你本地按下述步骤验证。

## 6. 如何安全应用

在项目根目录（你的 `feature/day7-agent` 分支）运行：

```bash
git branch --show-current
git status --short
git apply --check BankPilot_Day7_阶段1_完整开发.patch
git apply BankPilot_Day7_阶段1_完整开发.patch
```

先看 `git apply --check`，若提示文件不匹配，**不要强行应用**：检查是否使用了不同版本的 Day 6 ZIP，或者之前已应用阶段 1.1 补丁。

在你的本地环境中执行：

```bash
cd agent-service
python -m pip install -r requirements.txt
python -m pytest -q tests/test_day7_auth_proxy.py tests/test_day7_auth_safety.py tests/test_day7_workflow_identity.py
python -m pytest -q tests

cd ../frontend
npm ci
npm run build
npm run dev
```

由于目前 Java 尚未提供 Day 7 新接口，新 UI 真实登录失败属于**待 Java 联调**，不属于假数据可修复问题。待 Java 完成后依次验收：两位用户注册→分别登录→余额/订阅隔离→A 登出 B 登录→B 不能恢复 A 的工作流→旧转账审批/订阅取消回归。

## 7. 安全与已知边界

- 本阶段没有在浏览器的 `localStorage`/`sessionStorage` 中保存 Token、密码或 OTP，也没有引入新的模型调用来认证。
- Vue `busy` 时禁用退出，避免用户在审批提交中途切换身份；登录有效性由 Java `/me` 再确认。
- Java/MySQL 必须独立保护**所有**读取、资金写入与订单状态接口。Python 按 `userId` 绑定工作流是第二道防线，不替代 Java。
- 当前 LangGraph 会话和检查点仍是**内存状态**，服务重启不可直接恢复；原有工作流会话 30 分钟 TTL 沿用 Day 6。
- 新 UI 不提供 Mock/手填 Token；旧的后端 `demo-login` 和 `mock_backend.py` 保留用于自动化测试。新 UI 必须连接实现新版身份接口的 Java 服务才能真实使用。
- 登出失败时不删除服务器 Token，也不误报成功；当用户通过刷新浏览器丢失内存 Token 时，服务端原 Token 可能在到期前仍有效，直到 Java 清理。这是已选择的“Token 仅内存”模式的自然边界。
