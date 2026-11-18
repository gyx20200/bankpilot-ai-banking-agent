# BankPilot 2.0 — D3 成员 B 开发与独立测试报告

> **项目名称：** BankPilot｜基于 LangGraph 的金融业务 Agent 与 RAG 智能服务系统  
> **开发阶段：** D3（会话管理与历史消息持久化基础）  
> **负责成员：** 成员 B（Python Agent + Vue 前端）  
> **测试日期：** 2026-11-18  
> **测试环境：** Windows PowerShell、Python 3.14.0、pytest 9.1.1、Vite 6.4.5  
> **说明：** 本报告依据本次实际 PowerShell 执行记录整理。未在日志中出现的开发、提交或联调行为不视为已完成。

---

## 一、D3 阶段目标与成员 B 职责

D3 的目标是把 D2 阶段形成的会话数据结构、API 契约和 Context Manager 设计推进到可独立验证的代码层，为后续多轮记忆、历史上下文注入及 LangGraph 持久化恢复提供基础。

成员 B 负责：

1. Python Agent 服务侧的会话 API 代理。
2. Java 会话 API 的请求转发与异常处理。
3. 历史消息到 Agent Context 的适配。
4. Vue 会话列表及历史消息界面的集成。
5. Python 单元测试、Mock Java API 测试和 Vue 构建验证。
6. 编写开发与测试记录，并向成员 A 交接接口契约及待联调事项。

**职责边界：** 成员 B 不负责 MySQL 表结构迁移和 Spring Boot 会话持久化实现；这些由成员 A 完成。成员 B 的 Mock 测试只能验证 Python 侧的请求构造、校验和响应处理，不能替代 Java 真实接口或数据库测试。

## 二、开发内容与文件清单

以下按 D3 设计的交付范围列出。提交前应使用 `git status` 和 `git diff --stat` 核实每个文件确实已新增或修改；本次测试日志能够证明部分模块被调用或测试，但不能单独证明所有前端改动均已完成。

| 模块             | 目标文件                                          | 说明                                                 | 本次日志证据                                         |
| ---------------- | ------------------------------------------------- | ---------------------------------------------------- | ---------------------------------------------------- |
| FastAPI 会话代理 | `agent-service/app/conversation_api.py`           | 代理会话创建、列表、详情、消息读取和用户消息提交请求 | Mock 测试导入该模块并通过                            |
| Context 历史适配 | `agent-service/app/context/history_client.py`     | 将 Java 历史消息响应转换为 Agent Context             | 本次打开过文件，但未展示专门测试结果                 |
| Context 数据模型 | `agent-service/app/context/models.py`             | 定义并校验 Planner Context 数据                      | D2 Context Manager 测试通过；本次未单独展示文件 diff |
| Context 管理器   | `agent-service/app/context/manager.py`            | 历史消息排序、数量限制、去重及上下文构建             | 对应 7 项测试通过                                    |
| FastAPI 路由注册 | `agent-service/main.py`                           | 注册会话代理路由                                     | 应在提交前检查实际 diff                              |
| Vue 会话侧栏     | `frontend/src/components/ConversationSidebar.vue` | 会话列表、新建会话和选择会话的 UI                    | 本次日志未展示浏览器交互测试                         |
| Vue 主界面       | `frontend/src/App.vue`                            | 将会话侧栏和会话状态接入主界面                       | 本次日志未展示文件 diff 或浏览器验收                 |
| Mock API 测试    | `tests/agent/test_conversation_api_mock.py`       | 不依赖真实 Java 服务，模拟 Java HTTP 响应            | 7 项测试通过                                         |
| D3 测试报告      | `docs/d3-member-b-test-report.md`                 | 记录开发范围、测试证据、限制和交接事项               | 本文档                                               |

### 2.1 FastAPI 会话代理的设计职责

FastAPI 作为 Agent 服务入口，接收前端会话请求，并将请求转发至 Spring Boot 会话 API。成员 B 侧应负责：

- 检查请求是否携带 Bearer Token；
- 校验会话 UUID、请求体字段和消息长度；
- 将当前用户的认证凭证转发给 Java；
- 将 Java 的业务状态码传递给前端；
- Java 服务不可用或返回异常数据时，返回明确的网关错误；
- 不允许浏览器通过请求体指定 `user_id` 或伪造 `ASSISTANT` 角色。

### 2.2 Context 历史消息适配的设计职责

历史消息应来自 Java 后端经过用户身份验证的会话查询接口，而不是浏览器自行提交的历史消息数组。

适配层应检查：

- 响应中的 `conversationId` 与当前请求会话一致；
- 历史消息字段符合 D2 Pydantic 模型；
- 消息角色只允许 `USER` 和 `ASSISTANT`；
- 历史消息按时间或消息 ID 正确排序；
- 历史数量限制和当前消息去重由 Context Manager 统一处理。

**本次测试记录没有显示 History Client 的专门测试结果，因此该模块仍需补充独立测试或在 D3 联调时验证。**

## 三、独立测试环境与执行方式

本次使用成员 B 本机的 Python 虚拟环境执行测试：

```powershell
cd "E:\bank_agent\bankpilot-project"

$py = ".\agent-service\.venv\Scripts\python.exe"
$env:PYTHONPATH = (Resolve-Path .\agent-service).Path
```

测试使用项目内的虚拟环境解释器，不要求启动成员 A 的 Spring Boot 服务，也不要求连接 MySQL。

Vue 构建在 `frontend` 目录下执行：

```powershell
cd .\frontend
npm run build
cd ..
```

## 四、Python 测试结果

### 4.1 Context Manager 定向测试

执行命令：

```powershell
& $py -m pytest -q tests/agent/planning/test_context_manager.py
```

实际结果：

```text
....... [100%]
7 passed in 0.06s
```

<测试结论：通过>

该结果表明 D2 已有的 Context Manager 测试集在本次环境中通过。测试覆盖的设计范围包括历史消息解析、角色校验、历史条数限制、当前消息去重及空历史处理等。

### 4.2 Python 全量测试

执行命令：

```powershell
& $py -m pytest -q
```

实际结果：

```text
231 passed, 4 warnings in 13.23s
```

<测试结论：通过，但存在 4 条弃用警告>

警告来自 `agent-service/mock_day7_backend.py` 中的 FastAPI `@app.on_event("startup")` 和 `@app.on_event("shutdown")` 用法，以及 FastAPI 对应的弃用提示。它们没有导致本次测试失败，但后续可以迁移到 FastAPI lifespan 事件管理方式。

**测试统计口径说明：** 这次 231 项全量测试是在创建并运行 `tests/agent/test_conversation_api_mock.py` 之前执行的。因此，不能把本次结果写成“全量 238 项通过”。新增的 7 项 Mock 测试在后续单独执行，见 4.3 节。建议在所有 D3 测试文件加入后重新运行一次全量 pytest，取得最终统一结果。

### 4.3 FastAPI Mock Java 接口测试

新增测试文件：

```text
tests/agent/test_conversation_api_mock.py
```

执行前设置：

```powershell
$env:PYTHONPATH = (Resolve-Path .\agent-service).Path
```

执行命令：

```powershell
& $py -m pytest -v tests/agent/test_conversation_api_mock.py
```

实际结果：

```text
collected 7 items

test_missing_token_returns_401 PASSED
test_create_conversation_forwards_to_java PASSED
test_java_404_is_preserved PASSED
test_java_409_is_preserved PASSED
test_assistant_role_cannot_be_submitted PASSED
test_invalid_conversation_id_is_rejected PASSED
test_java_connection_failure_returns_502 PASSED

7 passed in 1.36s
```

<测试结论：7 项全部通过>

测试采用 `httpx.MockTransport` 模拟 Java API 响应，不会真实访问 Spring Boot 或 MySQL。

| 测试用例            | 实际结果 | 验证内容                                                     |
| ------------------- | -------- | ------------------------------------------------------------ |
| 无 Token 请求       | PASSED   | FastAPI 入口拒绝未携带 Bearer Token 的请求                   |
| 创建会话转发        | PASSED   | 创建请求被转发至约定的 Java 路径，认证头和请求体符合测试预期 |
| Java 返回 404       | PASSED   | 代理保留资源不存在状态                                       |
| Java 返回 409       | PASSED   | 代理保留冲突状态                                             |
| 伪造 ASSISTANT 角色 | PASSED   | 请求模型拒绝额外的助手角色字段                               |
| 非法 conversationId | PASSED   | UUID 路径参数校验拒绝非法值                                  |
| Java 连接失败       | PASSED   | Java 服务不可用时返回 502                                    |

**测试边界：** 以上结果证明 Python 代理在模拟响应下的行为符合测试预期；不能证明 Java 真实实现了 Token 验证、用户归属校验、消息幂等或数据库事务。

## 五、Vue 前端构建结果

执行命令：

```powershell
cd .\frontend
npm run build
```

本次执行两次，均构建成功。日志中的关键结果：

```text
vite v6.4.5 building for production...
24 modules transformed.

dist/index.html                                 0.36 kB
dist/assets/auth-city-B0uz282x.svg             18.22 kB
dist/assets/auth-building-layer-IWf_KkLs.png  424.96 kB
dist/assets/index-DZIhHGqX.css                 88.36 kB
dist/assets/index-Db7-_5XZ.js                 146.86 kB

✓ built in 1.07s
```

第二次构建同样成功，耗时约 1.10 秒。

<测试结论：Vite 生产构建通过>

### 5.1 需要跟进的资源警告

两次构建均出现：

```text
./assets/auth-bank-building.jpg referenced in
./assets/auth-bank-building.jpg didn't resolve at build time,
it will remain unchanged to be resolved at runtime
```

该警告没有阻止构建，但说明 `auth-bank-building.jpg` 在构建阶段未被 Vite 解析。需要检查资源文件是否存在、引用路径是否正确，以及该资源是否应放入 `public` 目录或通过相对模块路径导入。

在浏览器实际打开登录页检查该图片前，不应声称资源显示正常。

### 5.2 前端自动化测试能力说明

本次读取的 `frontend/package.json` 中 scripts 为：

```json
{
  "scripts": {
    "dev": "vite --host 127.0.0.1",
    "build": "vite build",
    "preview": "vite preview"
  }
}
```

当前没有配置 `npm test` 脚本。因此，本次完成的是 Vite 生产构建检查，不是 Vue 组件单元测试或浏览器端到端测试。

尚需人工或后续自动化验证：

- 登录后会话列表是否加载；
- 新建会话是否显示在侧栏；
- 选择会话是否加载对应历史消息；
- 退出登录后是否清空前一用户的会话状态；
- 原有转账、OTP、预约及审批交互是否保持正常。

## 六、与成员 A 的接口交接约定

成员 B 的 FastAPI 代理与成员 A 的 Spring Boot 会话 API 应按 D2 契约对接。

| 操作         | Spring Boot 约定路径                    | FastAPI 前端入口                              |
| ------------ | --------------------------------------- | --------------------------------------------- |
| 创建会话     | `POST /api/conversations`               | `POST /api/agent/conversations`               |
| 获取会话列表 | `GET /api/conversations`                | `GET /api/agent/conversations`                |
| 获取会话详情 | `GET /api/conversations/{id}`           | `GET /api/agent/conversations/{id}`           |
| 分页读取消息 | `GET /api/conversations/{id}/messages`  | `GET /api/agent/conversations/{id}/messages`  |
| 保存用户消息 | `POST /api/conversations/{id}/messages` | `POST /api/agent/conversations/{id}/messages` |

以上是双方应核对的接口映射，最终以合并后的 API 契约和 Java 实际实现为准。

### 6.1 双方职责边界

**成员 A（Java + MySQL）：**

- 创建并迁移会话、消息等数据库表；
- 实现 Spring Boot 会话管理 API；
- 从认证上下文取得当前用户 ID；
- 对所有会话和消息查询执行用户归属校验；
- 将用户消息以 `USER` 角色写入数据库；
- 实现请求幂等、事务和数据校验；
- 后续提供受认证的服务端助手消息写入机制。

**成员 B（Python Agent + Vue）：**

- 接收前端请求并转发 Java API；
- 透传当前用户的 Bearer Token；
- 处理 Java 的状态码和网络异常；
- 从可信 Java API 获取历史消息；
- 将历史消息转换为 Planner Context；
- 在 Vue 中展示会话列表和历史消息；
- 不允许浏览器自行指定消息所属用户或伪造 `ASSISTANT` 角色。

### 6.2 安全约束

1. 浏览器提交的消息只能按 `USER` 角色处理。
2. 历史消息必须由 Java 根据当前认证用户和 conversationId 查询。
3. 不得相信浏览器自行提交的历史消息数组。
4. Python 代理不得把 Java 连接失败转换成业务成功。
5. 历史消息展示不等于恢复历史银行操作；不得自动重放转账、申购、取消订阅或审批动作。
6. OTP、密码、Bearer Token 等敏感凭证不得写入长期聊天记录或普通日志。
7. 助手消息应由可信服务端写入接口保存，不能开放给浏览器任意声明角色。

## 七、尚未完成及待联合验收事项

由于本次独立测试没有启动真实 Java 后端，也没有连接 MySQL，以下事项尚未完成：

| 待办                              | 负责人         | 验收方式                                               |
| --------------------------------- | -------------- | ------------------------------------------------------ |
| Java 会话 API 与 FastAPI 真实联调 | A + B          | 启动 Spring Boot 和 FastAPI，执行真实 HTTP 请求        |
| MySQL 会话、消息真实持久化        | A              | 创建消息后查询数据库，并刷新后读取                     |
| 用户 A/B 会话隔离                 | A 主责，B 配合 | 使用两个真实测试账户交叉访问                           |
| History Client 专项测试           | B              | Mock Java 历史响应，验证字段、排序、会话 ID 和错误处理 |
| Vue 会话创建和切换                | B              | 浏览器端操作验证                                       |
| 刷新后历史消息恢复                | A + B          | 真实 MySQL 数据重新加载                                |
| Agent 助手回复持久化              | A + B          | 通过可信服务端写入接口验证                             |
| LangGraph Checkpoint 持久化与恢复 | 后续阶段       | 使用持久化 Checkpointer 和线程恢复测试                 |

## 八、D3 成员 B 当前结论

根据本次执行记录，可以确认：

- Context Manager 定向测试：7 项通过；
- Python 全量测试：231 项通过，4 条弃用警告；
- FastAPI Mock Java 测试：7 项通过；
- Vue Vite 生产构建：两次成功；
- 尚未完成真实 Java/MySQL 联调；
- History Client 专项测试结果尚未提供；
- Vue 浏览器交互及端到端验收尚未提供。

因此，成员 B 已完成 D3 的一部分独立开发验证工作，具备向成员 A 提交代码审查和接口交接的基础。**D3 全栈联调和最终验收仍需双方完成，不应仅凭 Mock 测试和前端构建结果宣称全部完成。**

## 九、提交前检查与 Git 交付

提交前执行：

```powershell
git branch --show-current
git status -sb
git diff --check
git diff --stat
```

确认测试报告、Python 代码、测试代码和 Vue 修改均在预期范围内；确认没有提交 `.env`、密码、Token、OTP、数据库备份、虚拟环境或构建缓存。

建议提交信息：

```powershell
git add docs/d3-member-b-test-report.md
git add tests/agent/test_conversation_api_mock.py
# 再将实际修改的 Python、Vue 文件逐项 git add

git commit -m "feat: add D3 conversation gateway and member B tests"
git push -u origin feature/v2-d3-conversation-agent-b
```

**分支名、commit SHA、PR 链接和最终合并状态应在实际执行后补录，不得预先填写。**

---

## 附录：本次实际测试命令

```powershell
# Context Manager
& $py -m pytest -q tests/agent/planning/test_context_manager.py

# Python 全量测试（本次新增 Mock 测试文件创建之前）
& $py -m pytest -q

# FastAPI Mock Java
$env:PYTHONPATH = (Resolve-Path .\agent-service).Path
& $py -m pytest -v tests/agent/test_conversation_api_mock.py

# Vue 生产构建
cd .\frontend
npm run build
cd ..
```

**建议最终提交前补做一次：**

```powershell
# 确保新增 Mock 测试已纳入全量测试
$env:PYTHONPATH = (Resolve-Path .\agent-service).Path
& $py -m pytest -q
```

将这次最终全量测试结果追加到本报告，作为 D3 成员 B 最终测试基线。
