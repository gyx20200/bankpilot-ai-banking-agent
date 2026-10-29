"""BankPilot Day 6: concurrent reads + at most one independent approval business.

Only the authenticated resume endpoint can trigger banking authorization.
The graph never allows transfer and cancellation to run in the same request.
"""
from typing import Annotated, Any, NotRequired, TypedDict
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send, interrupt
from langgraph.runtime import Runtime

from app import banking_client as bank
from app.graph.task_planner import plan_tasks
from app.graph.dynamic_read_workflow import READ_TASK_TYPES, execute_read
from app.graph.task_registry import TASK_REGISTRY
from app.graph.transfer_prepare import match_registered_payee, prepare_verified_transfer
from app.graph.transfer_approval_nodes import (
    assign_transfer_approval_ids, wait_transfer_approval, after_transfer_decision,
    transfer_authorize_node, after_transfer_authorize, transfer_execute_node,
    transfer_verify_success_node, transfer_cancel_node, transfer_verify_cancelled_node,
)


class Context(TypedDict):
    authorization: str
    transferOtpCode: NotRequired[str | None]


def merge_results(left: dict, right: dict) -> dict:
    return {**left, **right}


class State(TypedDict, total=False):
    message: str
    plan: dict[str, Any]
    status: str
    details: str
    results: Annotated[dict[str, dict], merge_results]
    candidate: dict | None
    prepareRequestId: str
    authorizeRequestId: str
    executeRequestId: str
    rejectRequestId: str
    approvalDecision: bool
    cancellationOrder: dict
    transferCandidate: dict | None
    transferRequestId: str
    transferOrder: dict
    transferDecision: bool
    transferAuthorizeRequestId: str
    transferExecuteRequestId: str
    transferCancelRequestId: str


async def plan_node(state: State) -> dict:
    plan = await plan_tasks(state['message'])
    return {'plan': plan.model_dump(mode='json', exclude_none=True)}


def validate_node(state: State) -> dict:
    plan = state['plan']
    if plan['status'] != 'ready':
        return {'status': 'NEEDS_CLARIFICATION',
                'details': plan.get('clarification') or '请补充任务参数。'}
    supported = READ_TASK_TYPES | {'cancel_subscription', 'transfer_prepare'}
    unsupported = [t['type'] for t in plan['tasks'] if t['type'] not in supported]
    if unsupported:
        return {'status': 'NOT_IMPLEMENTED_YET',
                'details': '本阶段尚未执行这些操作：' + '、'.join(unsupported) + '；未执行任何银行业务。'}
    # Planner preflight forbids multiple approval businesses. Verify again at
    # graph boundary in case the planner is replaced or graph is invoked directly.
    writes = [t for t in plan['tasks']
              if TASK_REGISTRY[t['type']].risk_level != 'LOW']
    if len(writes) > 1:
        return {'status': 'NEEDS_CLARIFICATION',
                'details': '转账和取消订阅不能放在同一个请求里审批，请拆分操作；没有执行银行任务。'}
    return {'status': 'READY'}


def dispatch_reads(state: State):
    if state['status'] != 'READY':
        return END
    tasks = {task['type']: task for task in state['plan']['tasks']}
    # execution_order includes dependencies (e.g. cancel -> list_subscriptions).
    return [Send('execute_read', {'task': tasks.get(task_type, {'type': task_type})})
            for task_type in state['plan']['execution_order']
            if task_type in READ_TASK_TYPES]


def summarize_reads(state: State) -> dict:
    expected = {t for t in state['plan']['execution_order'] if t in READ_TASK_TYPES}
    actual = {t for t, r in state.get('results', {}).items() if r.get('status') == 'SUCCESS'}
    if expected != actual:
        return {'status': 'INCOMPLETE', 'details': '只读查询结果不完整，未创建取消申请。'}
    if any(t['type'] in ('cancel_subscription', 'transfer_prepare')
           for t in state['plan']['tasks']):
        return {'status': 'READS_COMPLETE'}
    return {'status': 'COMPLETED', 'details': '查询任务全部完成。'}


def after_reads(state: State):
    if state['status'] != 'READS_COMPLETE':
        return END
    if any(t['type'] == 'cancel_subscription' for t in state['plan']['tasks']):
        return 'match_target'
    return 'match_payee'


def match_target(state: State) -> dict:
    target_name = next(t['target_name'] for t in state['plan']['tasks']
                       if t['type'] == 'cancel_subscription')
    subs = state['results']['list_subscriptions']['data']
    active = [s for s in subs
              if s.get('status') == 'ACTIVE'
              and str(s.get('merchantName', '')).strip() == target_name.strip()]
    if not active:
        return {'status': 'TARGET_NOT_FOUND',
                'details': '没有找到名称完全一致的有效代扣协议，未创建取消申请。'}
    if len(active) != 1:
        return {'status': 'TARGET_AMBIGUOUS',
                'details': '匹配到多个同名代扣协议，请明确选择，未创建取消申请。'}
    sub = active[0]
    if type(sub.get('id')) is not int or sub['id'] <= 0:
        return {'status': 'TARGET_INVALID', 'details': '银行订阅 ID 无效。'}
    return {'status': 'TARGET_FOUND',
            'candidate': {'id': sub['id'], 'merchantName': sub['merchantName'],
                          'amount': str(sub.get('amount', '')),
                          'billingCycle': sub.get('billingCycle', '')}}


def after_match(state: State):
    return 'assign_request_id' if state['status'] == 'TARGET_FOUND' else END


def assign_request_id(state: State) -> dict:
    # Committed at a graph checkpoint BEFORE the external prepare POST.
    return {'prepareRequestId': uuid4().hex}


async def prepare_node(state: State, runtime: Runtime[Context]) -> dict:
    result = await bank.prepare_subscription_cancellation(
        state['candidate']['id'], runtime.context['authorization'], state['prepareRequestId'])
    # The client also validates response status + subscription identity.
    return {'cancellationOrder': result, 'status': 'PENDING_APPROVAL'}


def assign_decision_ids(state: State) -> dict:
    # Checkpoint stable idempotency keys BEFORE the approval can be resumed.
    return {
        'authorizeRequestId': uuid4().hex,
        'executeRequestId': uuid4().hex,
        'rejectRequestId': uuid4().hex,
    }


def pause_for_user(state: State) -> dict:
    # No network side effects inside a node that calls interrupt(): this node
    # is re-entered during resume. The API validates identity and thread owner.
    decision = interrupt({
        'kind': 'SUBSCRIPTION_CANCELLATION',
        'orderId': state['cancellationOrder']['orderId'],
        'candidate': state['candidate'],
        'notice': '请确认是否取消该模拟代扣。拒绝后将关闭该取消申请。',
    })
    if type(decision) is not bool:
        return {'status': 'INVALID_APPROVAL',
                'details': '审批值必须是明确的 true 或 false，银行操作未执行。'}
    return {'approvalDecision': decision,
            'status': 'APPROVED' if decision else 'DECLINED'}


def after_approval(state: State):
    if state['status'] == 'APPROVED':
        return 'authorize'
    if state['status'] == 'DECLINED':
        return 'reject'
    return END


async def authorize_node(state: State, runtime: Runtime[Context]) -> dict:
    oid = state['cancellationOrder']['orderId']
    bearer = runtime.context['authorization']
    try:
        order = await bank.authorize_subscription_cancellation(
            oid, bearer, state['authorizeRequestId'], confirmed=True)
    except bank.BankError:
        # If the POST succeeded but response was lost, verify with the bank.
        order = await bank.get_subscription_cancellation(oid, bearer)
        if order.get('status') not in ('AUTHORIZED', 'SUCCESS'):
            raise
    if ('subscriptionId' in order
            and order['subscriptionId'] != state['candidate']['id']):
        raise bank.BankError('授权返回的订阅与审批目标不一致。', 409)
    return {'cancellationOrder': order, 'status': 'AUTHORIZED'}


async def execute_node(state: State, runtime: Runtime[Context]) -> dict:
    oid = state['cancellationOrder']['orderId']
    bearer = runtime.context['authorization']
    try:
        order = await bank.execute_subscription_cancellation(
            oid, bearer, state['executeRequestId'])
    except bank.BankError:
        # Never blindly retry with a new requestId after an ambiguous response.
        order = await bank.get_subscription_cancellation(oid, bearer)
        if (order.get('status') != 'SUCCESS'
                or order.get('subscriptionStatus') != 'CANCELLED'):
            raise
    if ('subscriptionId' in order
            and order['subscriptionId'] != state['candidate']['id']):
        raise bank.BankError('执行返回的订阅与审批目标不一致。', 409)
    return {'cancellationOrder': order, 'status': 'EXECUTED_PENDING_VERIFICATION'}


async def verify_cancelled(state: State, runtime: Runtime[Context]) -> dict:
    oid = state['cancellationOrder']['orderId']
    order = await bank.get_subscription_cancellation(
        oid, runtime.context['authorization'])
    if (order.get('orderId') != oid
            or order.get('subscriptionId') != state['candidate']['id']
            or order.get('status') != 'SUCCESS'
            or order.get('subscriptionStatus') != 'CANCELLED'):
        raise bank.BankError('取消结果尚未确认，请查询银行订单，不得宣称取消成功。', 409)
    return {'cancellationOrder': order, 'status': 'COMPLETED',
            'details': '银行已确认代扣取消成功。'}


def expected_rejected_order_status() -> str:
    return "REJECTED" if bank.BANK_MODE == "mock" else "CANCELLED"



async def reject_node(state: State, runtime: Runtime[Context]) -> dict:
    oid = state['cancellationOrder']['orderId']
    bearer = runtime.context['authorization']

    # Java 和 Mock 的拒绝订单终态不同
    expected_status = (
        'REJECTED' if bank.BANK_MODE == 'mock'
        else 'CANCELLED'
    )

    try:
        order = await bank.reject_subscription_cancellation(
            oid, bearer, state['rejectRequestId']
        )
    except bank.BankError:
        # 如果 POST 已成功但响应丢失，只查询真实订单，不重复提交
        order = await bank.get_subscription_cancellation(oid, bearer)

        if (
            order.get('status') != expected_status
            or order.get('subscriptionStatus') != 'ACTIVE'
        ):
            raise

    # 严格验证返回的订单和订阅
    if (
        order.get('orderId') != oid
        or order.get('subscriptionId') != state['candidate']['id']
        or order.get('status') != expected_status
        or order.get('subscriptionStatus') != 'ACTIVE'
    ):
        raise bank.BankError(
            '银行未确认关闭取消申请，不能报告拒绝成功。',
            409
        )

    return {
        'cancellationOrder': order,
        'status': 'REJECTED_PENDING_VERIFICATION'
    }



async def verify_rejected(
    state: State,
    runtime: Runtime[Context]
) -> dict:
    oid = state['cancellationOrder']['orderId']

    expected_status = (
        'REJECTED' if bank.BANK_MODE == 'mock'
        else 'CANCELLED'
    )

    # 再次向银行查询最终订单状态
    order = await bank.get_subscription_cancellation(
        oid,
        runtime.context['authorization']
    )

    if (
        order.get('orderId') != oid
        or order.get('subscriptionId') != state['candidate']['id']
        or order.get('status') != expected_status
        or order.get('subscriptionStatus') != 'ACTIVE'
    ):
        raise bank.BankError(
            '拒绝结果尚未确认，请核查银行订单。',
            409
        )

    return {
        'cancellationOrder': order,
        'status': 'REJECTED',
        'details': '用户已拒绝；银行已关闭取消申请，订阅保持 ACTIVE。'
    }




def match_payee(state: State) -> dict:
    task = next(t for t in state['plan']['tasks']
                if t['type'] == 'transfer_prepare')
    status, candidate = match_registered_payee(
        state['results']['get_payees']['data'],
        task['payee_name'], task['amount'])
    if status != 'PAYEE_FOUND':
        return {'status': status,
                'details': '没有唯一匹配的已保存收款人或金额不合法，未创建转账订单。'}
    return {'status': 'PAYEE_FOUND', 'transferCandidate': candidate}


def after_match_payee(state: State):
    return 'assign_transfer_request_id' if state['status'] == 'PAYEE_FOUND' else END


def assign_transfer_request_id(state: State) -> dict:
    # Save the idempotency key to a checkpoint BEFORE the external POST.
    return {'transferRequestId': uuid4().hex}


async def prepare_transfer_node(state: State, runtime: Runtime[Context]) -> dict:
    order = await prepare_verified_transfer(
        state['transferCandidate'], state['transferRequestId'],
        runtime.context['authorization'])
    return {'transferOrder': order, 'status': 'TRANSFER_PENDING_APPROVAL'}




builder = StateGraph(State, context_schema=Context)
builder.add_node('match_payee', match_payee)
builder.add_node('assign_transfer_request_id', assign_transfer_request_id)
builder.add_node('prepare_transfer', prepare_transfer_node)
builder.add_node('assign_transfer_approval_ids', assign_transfer_approval_ids)
builder.add_node('wait_for_transfer_approval', wait_transfer_approval)
builder.add_node('transfer_authorize', transfer_authorize_node)
builder.add_node('transfer_execute', transfer_execute_node)
builder.add_node('transfer_verify_success', transfer_verify_success_node)
builder.add_node('transfer_cancel', transfer_cancel_node)
builder.add_node('transfer_verify_cancelled', transfer_verify_cancelled_node)
builder.add_node('plan', plan_node)
builder.add_node('validate', validate_node)
builder.add_node('execute_read', execute_read)
builder.add_node('summarize_reads', summarize_reads)
builder.add_node('match_target', match_target)
builder.add_node('assign_request_id', assign_request_id)
builder.add_node('prepare', prepare_node)
builder.add_node('assign_decision_ids', assign_decision_ids)
builder.add_node('wait_for_approval', pause_for_user)
builder.add_node('authorize', authorize_node)
builder.add_node('execute', execute_node)
builder.add_node('verify_cancelled', verify_cancelled)
builder.add_node('reject', reject_node)
builder.add_node('verify_rejected', verify_rejected)
builder.add_edge(START, 'plan')
builder.add_edge('plan', 'validate')
builder.add_conditional_edges('validate', dispatch_reads, ['execute_read', END])
builder.add_edge('execute_read', 'summarize_reads')
builder.add_conditional_edges('summarize_reads', after_reads,
                              ['match_target', 'match_payee', END])
builder.add_conditional_edges('match_payee', after_match_payee,
                              ['assign_transfer_request_id', END])
builder.add_edge('assign_transfer_request_id', 'prepare_transfer')
builder.add_edge('prepare_transfer', 'assign_transfer_approval_ids')
builder.add_edge('assign_transfer_approval_ids', 'wait_for_transfer_approval')
builder.add_conditional_edges('wait_for_transfer_approval', after_transfer_decision,
                              ['transfer_authorize', 'transfer_cancel', END])
builder.add_conditional_edges('transfer_authorize', after_transfer_authorize,
                              ['transfer_execute', 'transfer_verify_success'])
builder.add_edge('transfer_execute', 'transfer_verify_success')
builder.add_edge('transfer_verify_success', END)
builder.add_edge('transfer_cancel', 'transfer_verify_cancelled')
builder.add_edge('transfer_verify_cancelled', END)
builder.add_conditional_edges('match_target', after_match, ['assign_request_id', END])
builder.add_edge('assign_request_id', 'prepare')
builder.add_edge('prepare', 'assign_decision_ids')
builder.add_edge('assign_decision_ids', 'wait_for_approval')
builder.add_conditional_edges('wait_for_approval', after_approval,
                              ['authorize', 'reject', END])
builder.add_edge('authorize', 'execute')
builder.add_edge('execute', 'verify_cancelled')
builder.add_edge('verify_cancelled', END)
builder.add_edge('reject', 'verify_rejected')
builder.add_edge('verify_rejected', END)

dynamic_graph = builder.compile(checkpointer=InMemorySaver())
