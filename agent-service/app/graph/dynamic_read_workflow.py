"""Dynamic read-only LangGraph. D10 optionally dispatches reads over MCP stdio.

No bank write tools are exposed through MCP. D1-D9 direct path remains available
with BANKPILOT_MCP_READ_MODE=off.
"""
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Send

from app import banking_client as bank
from app.graph.task_planner import plan_tasks
from app.graph.task_registry import TASK_REGISTRY
from app.rag.answer import answer_public_question
from app.mcp.dispatch import execute_mcp_read
from app.mcp.policy import read_mode
from app.skills.catalog import SKILLS
from app.skills.runtime import run_skill


class Context(TypedDict):
    authorization: str


class State(TypedDict, total=False):
    message: str
    plan: dict[str, Any]
    status: str
    details: str
    results: Annotated[dict[str, dict[str, Any]], lambda left, right: {**left, **right}]


READ_EXECUTORS = {
    'balance': bank.balance,
    'transactions': bank.transactions,
    'payees': bank.payees,
    'subscriptions': bank.subscriptions,
}
READ_TASK_TYPES = frozenset(
    task_type
    for task_type, spec in TASK_REGISTRY.items()
    if spec.risk_level == 'LOW'
    and (
        spec.executor_key in READ_EXECUTORS
        or spec.executor_key in {
            'monthly_analytics',
            'annual_analytics',
            'transaction_anomalies',
            'knowledge_search',
            'skill',
        }
    )
)


async def make_plan(state: State) -> dict:
    plan = await plan_tasks(state['message'])
    return {'plan': plan.model_dump(mode='json', exclude_none=True)}


def validate_for_read_stage(state: State) -> dict:
    plan = state['plan']
    if plan['status'] != 'ready':
        return {'status': 'NEEDS_CLARIFICATION', 'details': plan.get('clarification') or '请补充业务参数。'}
    requested = {task['type'] for task in plan['tasks']}
    not_ready = sorted(requested - READ_TASK_TYPES)
    if not_ready:
        return {'status': 'NOT_IMPLEMENTED_YET',
                'details': '以下业务已识别，但尚未接入本阶段的安全执行流程：' + '、'.join(not_ready) + '。未执行任何银行任务。'}
    return {'status': 'READY'}


def schedule_reads(state: State):
    if state['status'] != 'READY':
        return END
    return [Send('execute_read', {'task': item}) for item in state['plan']['tasks']]


async def execute_read(state: dict, runtime: Runtime[Context]) -> dict:
    task = state['task']
    task_type = task['type']

    if task_type not in READ_TASK_TYPES:
        raise ValueError('未授权的只读任务类型。')

    spec = TASK_REGISTRY[task_type]
    bearer = runtime.context['authorization']

    if task_type in SKILLS:
        # D11 skill step recipes are fixed in Python and use D10 MCP reads.
        # Cannot run in direct mode; no silent fallback or money tools.
        spec_skill = SKILLS[task_type]
        params = {k: task[k] for k in spec_skill.required_params if k in task}
        data = await run_skill(task_type, params, bearer)
    elif read_mode() == 'on':
        # D10: model still chooses a registered task; MCP only executes reads.
        # A read error is NOT silently routed to the direct executor.
        data = await execute_mcp_read(task, bearer)
    elif task_type == 'knowledge_search':
        data = await answer_public_question(task['query'])
    elif task_type == 'monthly_analytics':
        data = await bank.get_monthly_analytics(task['month'], bearer)
    elif task_type == 'annual_analytics':
        data = await bank.get_annual_analytics(task['year'], bearer)
    elif task_type == 'transaction_anomalies':
        data = await bank.get_transaction_anomalies(task['month'], bearer)
    else:
        handler = READ_EXECUTORS.get(spec.executor_key)
        if handler is None:
            raise ValueError(f'未找到任务 {task_type} 的受控只读执行器。')
        data = await handler(bearer)

    return {'results': {task_type: {'status': 'SUCCESS', 'data': data}}}


def finish(state: State) -> dict:
    expected = {item['type'] for item in state['plan']['tasks']}
    if set(state.get('results', {})) != expected:
        return {'status': 'INCOMPLETE', 'details': '查询结果不完整，不能报告全部任务成功。'}
    return {'status': 'COMPLETED', 'details': f'已完成 {len(expected)} 项银行只读查询。'}


builder = StateGraph(State, context_schema=Context)
builder.add_node('plan', make_plan)
builder.add_node('validate', validate_for_read_stage)
builder.add_node('execute_read', execute_read)
builder.add_node('finish', finish)
builder.add_edge(START, 'plan')
builder.add_edge('plan', 'validate')
builder.add_conditional_edges('validate', schedule_reads, ['execute_read', END])
builder.add_edge('execute_read', 'finish')
read_graph = builder.compile()
