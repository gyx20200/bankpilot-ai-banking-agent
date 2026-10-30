# BankPilot Day 7 阶段 4：定时转账 Agent / Vue / Java 交接契约

**基线要求：阶段 1 注册登录 + 阶段 2 收款人和备注转账 + 阶段 3 AA 功能全部已应用。** 本阶段不重写普通转账、AA 或订阅取消业务。

## 业务边界与规则

1. 用户必须在**同一条自然语言指令**中明确收款人、数字金额与具体未来执行时间；不依赖聊天多轮上下文。支持“明天下午3点给李四转200元”、`2026-11-01 15:00给李四转200元` 等明确时间；“明天3点”不区分早晚，会要求重新输入完整指令。
2. 银行目录负责解析姓名、手机号；出现重名时必须由当前用户选择脱敏候选。模型不得生成银行账户或目标用户 ID。
3. 预约**只支持一次性执行，不设置业务预约时长上限**，允许任意可以正确表示的未来日期时间；具体时间采用 `+08:00` ISO 8601，如 `2026-11-01T15:00+08:00`。Java 应校验时间、时区和业务参数。
4. 预约阶段所有金额 **统一强制 OTP**。银行短期校验 OTP，通过后建立只绑定该预约固定付款账户、收款账户、金额和执行时间的**长期专属预授权**；不是延长原始 OTP 或保存明文 OTP。无需因预约很远而自动使预授权到期。
5. 预约成功状态 `SCHEDULED` **不代表已转账**。Java/MySQL 保存计划，用户退出或关闭浏览器不影响预约；到期由 Java 调度，在当前风险/资金条件允许时执行，必须双边记账、双方流水、幂等审计。所有预约均经过强验证，可覆盖执行日的 YELLOW/RED 变化；不能跳过余额或其他已有基础风控。
6. 因服务停止而错过预约执行时间，采用 **方案 B：不补执行**。技术上为防止正常调度抖动，建议允许开始执行时间晚于约定时间最多 60 秒；超过则 `MISSED`。不要使用队列恢复时不受限制的补执行。**执行失败不自动重试**。状态 `UNKNOWN` 需先核查原资金订单，禁止盲目重新创建。
7. 只能查看/取消自己未执行的计划。**不支持编辑**，修改目标、金额或时间时先取消再通过完整新指令重新创建，必须重新 OTP。`SUCCESS`、`FAILED`、`MISSED` 不允许通过取消改变终态。
8. Stage4 Mock 只在内存存储注册、OTP、预约和余额，**Mock 重启会清空预约**；真实长期计划持久化、宕机后的 MISSED 识别必须由 Java/MySQL 实现。当前尚未开发冻结等银行能力，因此不额外引入账户冻结模块。

## Java 必须实现的端点

统一前缀 `/api/scheduled-transfers`，均要求 `Authorization: Bearer <Token>`；资金行为只由 Java/MySQL执行。浏览器只能访问 FastAPI `/api/agent/...`。

| 方法 | Java 路径 | 作用 | 状态要求 |
|---|---|---|---|
| POST | `/prepare` | 创建一次性预约草稿 | `PENDING_AUTH`，不扣款 |
| GET | `/mine` | 查询当前用户全部预约 | 按 Token 过滤用户 |
| GET | `/{scheduleId}` | 查询本人单项预约 | 跨用户 404/403 |
| POST | `/{scheduleId}/otp/request` | 申请预约 OTP | 仅 `PENDING_AUTH` |
| POST | `/{scheduleId}/authorize` | 确认固定业务及 OTP，签发专属预授权 | `SCHEDULED`，不扣款 |
| POST | `/{scheduleId}/cancel` | 撤销草稿或未到期的预约 | `CANCELLED`，禁止已执行取消 |

**POST /prepare** 请求示例：

```json
{"payeeId":2,"amount":"200.00","executeAt":"2026-11-01T15:00+08:00","remark":"生活费","requestId":"sched-unique-001"}
```

返回示例（金额、ID 为示意）：

```json
{"scheduleId":"ST-001","payeeName":"李四","accountMasked":"****6602","amount":"200.00","remark":"生活费","executeAt":"2026-11-01T15:00+08:00","status":"PENDING_AUTH","orderId":null,"failureReason":null}
```

**POST /{id}/otp/request**：使用当前 Token，仅请求一次性验证码。返回 `{"scheduleId":"ST-001","status":"OTP_REQUESTED","expiresInSeconds":120}`。

**POST /{id}/authorize**：`{"requestId":"sched-auth-unique-001","confirmed":true,"otpCode":"<用户输入的6位数字>"}`。需在同一用户身份下验证 OTP 与预约范围，成功返回同形态 `status=SCHEDULED`，失败不可改变为已授权。

**POST /{id}/cancel**：`{"requestId":"sched-cancel-unique-001"}`；允许 `PENDING_AUTH` 或 `SCHEDULED`，完成后返回 `CANCELLED`，原预授权必须撤销。

`GET /mine` 返回上述对象数组。所有 POST 使用 scoped requestId 幂等，特别是 OTP 授权和取消；相同 requestId 不得用于不同预约或变更金额/收款人/时间。

### 状态枚举

- `PENDING_AUTH`：创建草稿、尚未验证 OTP；不执行。
- `SCHEDULED`：已有专属强验证预授权，等待指定时间；不执行。
- `PROCESSING`：Java 调度已经独占处理。
- `SUCCESS`：资金实际扣减和入账成功，`orderId` 关联真实转账订单。
- `CANCELLED`：本人取消，预授权撤销。
- `FAILED`：明确余额不足等失败，不自动重试。
- `MISSED`：到期窗口已错过；不补执行。
- `UNKNOWN`：订单结果不能确定，先审计核实，不能重复扣款。

建议 MySQL `scheduled_transfers` 记录 payer_id, payee_id/payee_account_id, amount, execute_at, remark, status, order_id, request_id, authorized_at, processed_at, fail_reason, created_at, updated_at, version；`scheduled_transfer_authorizations` 记录 schedule_id, owner_id, verification_method, verified_at, binding_digest, revoked_at, security_event_id（**不存明文 OTP**）。按 scheduleId 唯一控制执行，并在数据库事务中完成余额、流水、实际 transfer order 和预约状态，避免多实例/并发重复处理。**时间调度以数据库为准，不能用长期内存定时器代替。**

## 你的 Python / Vue 的实现范围

- Planner 新增 `schedule_transfer`，完整指令校验，程序独立解析时间，拒绝含糊的“明天3点”。
- LangGraph 使用现有银行目录的可信收款人解析和重名选择；独立预约草稿、用户确认、专属 OTP、审批与核实节点。**用户输入 OTP 只在当前 FastAPI / Graph Runtime 中短时传递，不写入图 checkpoint、聊天记录或审计。**
- 预约 OTP 验证先于 LangGraph 审批节点推进，OTP 错误可以重新输入，不会造成无法继续的已批准状态。
- `GET /api/agent/schedules`、`GET /api/agent/schedules/{id}`、`POST /api/agent/schedules/{id}/cancel` 提供 Vue 预约中心；用户需通过银行 Token 验证。UI 只显示 Java 返回的订单和状态，不使用本地计时器执行转账。
- 模拟服务内置单独调度线程，每 1 秒扫描，按约定时间处理，允许 60 秒调度容差。真实 Java 服务到期逻辑尚待队友完成。

## 本地启动与必须配置

在 `agent-service/.env` 中**保留已有配置**并增加：

```ini
BANK_SCHEDULE_API_BASE=http://127.0.0.1:18080/api/scheduled-transfers
```

其他 Mock 环境变量参照 `agent-service/.env.stage4-schedule-mock.example`。**不加入这行时，本次代码也会在 `BANK_API_MODE=mock` 下根据 `BANK_API_BASE` 推导默认 Mock 预约地址**，避免阶段 3 的 AA 502 配置问题；但显式配置最容易诊断。

分别启动：

```powershell
# 终端 1，本地模拟银行；不得用于生产
cd agent-service
$env:BANKPILOT_STAGE1_MOCK='1'
python -m uvicorn mock_day7_backend:app --host 127.0.0.1 --port 18080

# 终端 2，原 Agent；继续用你已有的 DeepSeek 配置
cd agent-service
python -m uvicorn main:app --host 127.0.0.1 --port 8000

# 终端 3，Vue
cd frontend
npm run dev
```

新开的浏览器页面需要注册/登录测试用户。Mock 所有数据只在内存，重启就重置。

### 完整手动验收

1. 新注册测试用户 A 和用户 B；A 登录，发送完整指令，例如“明天下午3点给用户B转200元，备注生活费”。
2. 页面展示银行确认的收款人、金额、时间和脱敏账号。**未授权时双方余额不变。**
3. 点击“申请验证码”，Mock 仅用测试验证码 `246810`；输错后仍能留在审批卡纠正。
4. 输入正确 OTP、勾选确认，银行返回 `SCHEDULED`；立即查询双方余额，仍然不变。
5. 在预约中心查看、刷新、取消；取消后不得在到期时扣款。预约不能编辑，需要取消再发完整新指令。
6. 测试近期开单：用明确的实际日期时间（比现在晚约 2～3 分钟）建单，完成 OTP 后等银行执行。状态为 `SUCCESS` 时双方余额各减少、增加相同金额并有双方流水。
7. 用后端自动化测试检查 `MISSED`（窗口超过 60 秒）、余额不足 `FAILED`、幂等防重复、跨用户访问。Mock 重启不保留预约，不用于验证宕机恢复。
8. 回归：普通 YELLOW/RED、AA 付款、订阅取消、同名收款人选择、当前用户隔离。

自动化：

```powershell
cd agent-service
python -m pytest -q tests/test_day7_stage4_schedule.py
```

**测试边界：** 本环境已运行 Mock 业务测试、部分 Day 6/7 回归及 FastAPI 银行客户端的真实 HTTP 请求。完整 LangGraph 及 Vite 端到端在当前执行环境不可用（依赖缺失），需你本地依赖齐全后确认。正式 Java/MySQL 端点尚未实现，不能宣称真实 Java 定时服务已完成。
