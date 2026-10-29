"""Day 6, stage 3A: dynamic read-only LangGraph, separate from legacy workflow.

DeepSeek plans -> Python validates -> LangGraph Send fan-out -> real bank reads.
Mutations are intentionally NOT supported in this stage and NEVER partially run.
Authorization is runtime-only; never placed in the graph State.
"""
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Send

from app import banking_client as bank
from app.graph.task_planner import plan_tasks
from app.graph.task_registry import TASK_REGISTRY


class Context(TypedDict):
    authorization: str


class State(TypedDict, total=False):
    message: str
    plan: dict[str, Any]
    status: str
    details: str
    results: Annotated[dict[str, dict[str, Any]], lambda left, right: {**left, **right}]


# Explicit whitelist of read-only tasks available NOW.  Write-capable tasks are
# registered for planning but not executable by this graph.
READ_EXECUTORS = {
    "balance": bank.balance,
    "transactions": bank.transactions,
    "payees": bank.payees,
    "subscriptions": bank.subscriptions,
}
READ_TASK_TYPES = frozenset(
    task_type for task_type, spec in TASK_REGISTRY.items()
    if spec.risk_level == "LOW" and (
            spec.executor_key in READ_EXECUTORS or spec.executor_key == "monthly_analytics"
    )
)


async def make_plan(state: State) -> dict:
    plan = await plan_tasks(state["message"])

    return {
        "plan": plan.model_dump(
            mode="json",
            exclude_none=True
        )
    }


def validate_for_read_stage(state: State) -> dict:
    """A separate Graph guard; TaskPlan itself is already Pydantic-validated."""
    plan = state["plan"]
    if plan["status"] != "ready":
        return {
            "status": "NEEDS_CLARIFICATION",
            "details": plan.get("clarification") or "请补充业务参数。",
        }

    requested = {task["type"] for task in plan["tasks"]}
    not_ready = sorted(requested - READ_TASK_TYPES)
    if not_ready:
        # All-or-nothing for this stage: do not secretly ignore a transfer or
        # cancellation while running the other requested read tasks.
        return {
            "status": "NOT_IMPLEMENTED_YET",
            "details": "以下业务已识别，但尚未接入本阶段的安全执行流程：" + "、".join(not_ready)
                       + "。未执行任何银行任务。",
        }

    return {"status": "READY"}


def schedule_reads(state: State):
    if state["status"] != "READY":
        return END
    return [
        Send("execute_read", {"task": item})
        for item in state["plan"]["tasks"]
    ]


async def execute_read(state: dict, runtime: Runtime[Context]) -> dict:
    task = state["task"]
    task_type = task["type"]
    if task_type not in READ_TASK_TYPES:
        raise ValueError("未授权的只读任务类型。")
    spec = TASK_REGISTRY[task_type]
    bearer = runtime.context["authorization"]

    if task_type == "monthly_analytics":
        data = await bank.get_monthly_analytics(task["month"], bearer)
    else:
        handler = READ_EXECUTORS.get(spec.executor_key)
        if handler is None:
            raise ValueError(f"未找到任务 {task_type} 的受控只读执行器。")
        data = await handler(bearer)

    return {"results": {task_type: {"status": "SUCCESS", "data": data}}}


def finish(state: State) -> dict:
    expected = {item["type"] for item in state["plan"]["tasks"]}
    if set(state.get("results", {})) != expected:
        return {"status": "INCOMPLETE", "details": "查询结果不完整，不能报告全部任务成功。"}
    return {
        "status": "COMPLETED",
        "details": f"已完成 {len(expected)} 项银行只读查询。",
    }


builder = StateGraph(State, context_schema=Context)
builder.add_node("plan", make_plan)
builder.add_node("validate", validate_for_read_stage)
builder.add_node("execute_read", execute_read)
builder.add_node("finish", finish)
builder.add_edge(START, "plan")
builder.add_edge("plan", "validate")
builder.add_conditional_edges("validate", schedule_reads, ["execute_read", END])
builder.add_edge("execute_read", "finish")
# Read-only requests do not require checkpoints.  The write/approval graph in
# the next stage will use thread_id + a persistent checkpointer as appropriate.
read_graph = builder.compile()
