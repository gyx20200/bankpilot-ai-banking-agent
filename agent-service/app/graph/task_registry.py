"""BankPilot unified task registry (metadata only; does NOT call bank APIs).

Phase 1: describe the existing tasks, their parameters, dependencies and risk.
Later phases will wire the executor keys to existing banking_client handlers.
"""

from dataclasses import dataclass
from typing import Iterable, Literal

RiskLevel = Literal["LOW", "MEDIUM", "HIGH"]


@dataclass(frozen=True)
class TaskSpec:
    description: str
    executor_key: str
    risk_level: RiskLevel = "LOW"
    required_params: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()
    legacy_tool: str | None = None


# Task IDs are shared across the planner, LangGraph, and the frontend.
# legacy_tool records the name used by the existing Day 5 LLM router;
# it does not invoke that tool.
TASK_REGISTRY: dict[str, TaskSpec] = {
    "get_balance": TaskSpec(
        description="查询当前用户余额",
        executor_key="balance",
        legacy_tool="get_balance",
    ),
    "get_transactions": TaskSpec(
        description="查询当前用户历史交易流水",
        executor_key="transactions",
        legacy_tool="get_transactions",
    ),
    "get_payees": TaskSpec(
        description="查询当前用户常用收款人",
        executor_key="payees",
        legacy_tool="get_payees",
    ),
    "monthly_analytics": TaskSpec(
        description="分析指定月份收支",
        executor_key="monthly_analytics",
        required_params=("month",),
        legacy_tool="get_monthly_analytics",
    ),
    "list_subscriptions": TaskSpec(
        description="查询当前用户订阅代扣协议",
        executor_key="subscriptions",
        legacy_tool="get_subscriptions",
    ),
    "transfer_prepare": TaskSpec(
        description="创建待确认的转账订单，不执行转账",
        executor_key="transfer_prepare",
        risk_level="HIGH",
        required_params=("payee_name", "payee_phone", "amount", "remark"),
        depends_on=("get_payees",),
        legacy_tool="prepare_transfer",
    ),
    "schedule_transfer": TaskSpec(
        description="预约未来单次转账，固定收款人金额时间，预约时所有金额均强制OTP；到期银行自动执行",
        executor_key="schedule_transfer",
        risk_level="HIGH",
        required_params=("payee_name", "payee_phone", "amount", "remark", "time_expression", "execute_at"),
    ),
    "create_aa_collection": TaskSpec(
        description="准备并经发起人确认后发布AA收款请求；不会替接收人付款",
        executor_key="aa_collection",
        risk_level="MEDIUM",
        required_params=("aa_participants", "aa_mode", "amount", "aa_reason"),
    ),
    "cancel_subscription": TaskSpec(
        description="申请取消指定代扣，必须经独立人工审批与银行授权",
        executor_key="subscription_cancellation",
        risk_level="MEDIUM",
        required_params=("target_name",),
        depends_on=("list_subscriptions",),
    ),
}


def resolve_execution_order(requested: Iterable[str]) -> list[str]:
    """Return a valid dependency-first ordering, including internal tasks.

    This is a planning helper, NOT a bank executor. Independent read-only
    tasks may run concurrently when wired into LangGraph later.
    """
    ordered: list[str] = []
    visited: set[str] = set()
    visiting: set[str] = set()

    def visit(task_type: str) -> None:
        if task_type not in TASK_REGISTRY:
            raise ValueError(f"未注册任务：{task_type}")
        if task_type in visiting:
            raise ValueError(f"任务依赖存在循环：{task_type}")
        if task_type in visited:
            return
        visiting.add(task_type)
        for dependency in TASK_REGISTRY[task_type].depends_on:
            visit(dependency)
        visiting.remove(task_type)
        visited.add(task_type)
        ordered.append(task_type)

    for task_type in requested:
        visit(task_type)
    return ordered
