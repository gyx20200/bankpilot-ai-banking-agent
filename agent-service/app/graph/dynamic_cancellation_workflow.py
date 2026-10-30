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
from app.graph.transfer_prepare import prepare_verified_transfer
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
    recipientChoices: list[dict]
    selectedRecipient: dict
    transferRequestId: str
    transferOrder: dict
    transferDecision: bool
    transferAuthorizeRequestId: str
    transferExecuteRequestId: str
    transferCancelRequestId: str
    aaDraft: dict
    aaPrepareRequestId: str
    aaPublishRequestId: str
    aaDiscardRequestId: str
    aaDecision: bool
    scheduledDraft: dict
    scheduledPrepareRequestId: str
    scheduledAuthorizeRequestId: str
    scheduledCancelRequestId: str
    scheduledDecision: bool


async def plan_node(state: State) -> dict:
    plan = await plan_tasks(state['message'])
    return {'plan': plan.model_dump(mode='json', exclude_none=True)}


def validate_node(state: State) -> dict:
    plan = state['plan']
    if plan['status'] != 'ready':
        return {'status': 'NEEDS_CLARIFICATION',
                'details': plan.get('clarification') or '请补充任务参数。'}
    supported = READ_TASK_TYPES | {'cancel_subscription', 'transfer_prepare', 'create_aa_collection', 'schedule_transfer'}
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
    reads = [Send('execute_read', {'task': tasks.get(task_type, {'type': task_type})})
             for task_type in state['plan']['execution_order'] if task_type in READ_TASK_TYPES]
    return reads if reads else 'summarize_reads'


def summarize_reads(state: State) -> dict:
    expected = {t for t in state['plan']['execution_order'] if t in READ_TASK_TYPES}
    actual = {t for t, r in state.get('results', {}).items() if r.get('status') == 'SUCCESS'}
    if expected != actual:
        return {'status': 'INCOMPLETE', 'details': '只读查询结果不完整，未创建取消申请。'}
    if any(t['type'] in ('cancel_subscription', 'transfer_prepare', 'create_aa_collection', 'schedule_transfer')
           for t in state['plan']['tasks']):
        return {'status': 'READS_COMPLETE'}
    return {'status': 'COMPLETED', 'details': '查询任务全部完成。'}


def after_reads(state: State):
    if state['status'] != 'READS_COMPLETE':
        return END
    if any(t['type'] == 'cancel_subscription' for t in state['plan']['tasks']):
        return 'match_target'
    if any(t['type'] == 'create_aa_collection' for t in state['plan']['tasks']):
        return 'assign_aa_prepare_request_id'
    return 'resolve_registered_recipient'


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




async def resolve_registered_recipient(state: State, runtime: Runtime[Context]) -> dict:
    """Search the bank directory, not an LLM-provided account number."""
    task = next(t for t in state['plan']['tasks'] if t['type'] in ('transfer_prepare', 'schedule_transfer'))
    choices = await bank.search_registered_recipients(
        runtime.context['authorization'], name=task.get('payee_name'),
        phone=task.get('payee_phone'))
    if not choices:
        return {'status': 'PAYEE_NOT_FOUND',
                'details': '银行没有找到匹配的注册用户，未创建转账订单。'}
    if len(choices) == 1:
        return {'status': 'RECIPIENT_SELECTED', 'selectedRecipient': choices[0],
                'recipientChoices': choices}
    return {'status': 'RECIPIENT_CHOICES', 'recipientChoices': choices,
            'details': '找到多个同名收款用户，请选择正确的脱敏账户。尚未创建转账订单。'}


def after_resolve_recipient(state: State):
    if state['status'] == 'RECIPIENT_SELECTED':
        return 'confirm_recipient'
    if state['status'] == 'RECIPIENT_CHOICES':
        return 'wait_for_recipient_selection'
    return END


def wait_for_recipient_selection(state: State) -> dict:
    """Human selects a Java-returned candidate. No bank write in interrupt node."""
    selected_id = interrupt({
        'kind': 'RECIPIENT_SELECTION',
        'choices': state['recipientChoices'],
        'notice': '请选择收款对象。收款账户由银行提供，模型不能替你选择。',
    })
    if selected_id is False:
        return {'status': 'REJECTED', 'details': '已放弃选择收款人，本次没有创建银行转账订单。'}
    if type(selected_id) is not int:
        return {'status': 'RECIPIENT_INVALID_SELECTION', 'details': '选择必须是银行候选用户编号。'}
    matches = [x for x in state['recipientChoices'] if x['recipientId'] == selected_id]
    if len(matches) != 1:
        return {'status': 'RECIPIENT_INVALID_SELECTION', 'details': '选择不在银行候选列表中，未创建订单。'}
    return {'status': 'RECIPIENT_SELECTED', 'selectedRecipient': matches[0]}


def after_recipient_selection(state: State):
    return 'confirm_recipient' if state['status'] == 'RECIPIENT_SELECTED' else END


async def confirm_recipient(state: State, runtime: Runtime[Context]) -> dict:
    """Upsert a saved payee through Java; cross-check bank identity again."""
    choice = state['selectedRecipient']
    payee = await bank.confirm_registered_recipient(
        choice['recipientId'], runtime.context['authorization'])
    if (payee['payeeName'].strip() != choice['payeeName']
            or payee['payeeAccountMasked'] != choice['accountMasked']):
        raise bank.BankError('银行确认收款账户与已选对象不一致，未创建转账订单。', 409)
    task = next(t for t in state['plan']['tasks'] if t['type'] in ('transfer_prepare', 'schedule_transfer'))
    return {'status': 'PAYEE_FOUND', 'transferCandidate': {
        'id': payee['id'], 'payeeName': payee['payeeName'],
        'accountMasked': payee['payeeAccountMasked'],
        'amount': task['amount'], 'remark': task.get('remark') or '',
        'executeAt': task.get('execute_at') if task['type'] == 'schedule_transfer' else None,
    }}


def after_confirm_recipient(state: State):
    return ('assign_schedule_prepare_request_id' if any(t['type'] == 'schedule_transfer' for t in state['plan']['tasks'])
            else 'assign_transfer_request_id')


def assign_transfer_request_id(state: State) -> dict:
    # Save the idempotency key to a checkpoint BEFORE the external POST.
    return {'transferRequestId': uuid4().hex}


async def prepare_transfer_node(state: State, runtime: Runtime[Context]) -> dict:
    order = await prepare_verified_transfer(
        state['transferCandidate'], state['transferRequestId'],
        runtime.context['authorization'])
    return {'transferOrder': order, 'status': 'TRANSFER_PENDING_APPROVAL'}



# AA: prepare a bank-owned draft, then interrupt BEFORE publishing to payers.
# Recipient payments happen later under each payer's own login and never here.
def assign_aa_prepare_request_id(state: State) -> dict:
    return {'aaPrepareRequestId': uuid4().hex}


async def aa_prepare_node(state: State, runtime: Runtime[Context]) -> dict:
    task = next(t for t in state['plan']['tasks'] if t['type'] == 'create_aa_collection')
    draft = await bank.aa_prepare(task['aa_participants'], task['amount'],
                                  task['aa_mode'], task.get('aa_reason') or '',
                                  state['aaPrepareRequestId'], runtime.context['authorization'])
    return {'aaDraft': draft, 'status': 'AA_DRAFT_READY'}


def assign_aa_action_ids(state: State) -> dict:
    return {'aaPublishRequestId': uuid4().hex, 'aaDiscardRequestId': uuid4().hex}


def wait_aa_confirmation(state: State) -> dict:
    decision = interrupt({
        'kind': 'AA_COLLECTION', 'collectionId': state['aaDraft']['collectionId'],
        'items': state['aaDraft']['items'],
        'notice': '请确认要向这些用户发布AA收款请求。发布不会直接扣除他们的余额。',
    })
    if type(decision) is not bool:
        return {'status': 'INVALID_APPROVAL', 'details': 'AA 发布必须由发起人明确确认。'}
    return {'aaDecision': decision, 'status': 'AA_APPROVED' if decision else 'AA_DECLINED'}


def after_aa_decision(state: State):
    return 'aa_publish' if state['status'] == 'AA_APPROVED' else ('aa_discard' if state['status'] == 'AA_DECLINED' else END)


def _aa_same_draft(before: dict, now: dict) -> bool:
    return (before['collectionId'] == now['collectionId']
            and before['initiatorId'] == now['initiatorId']
            and before['totalAmount'] == now['totalAmount']
            and before['requestedAmount'] == now['requestedAmount']
            and [(i['itemId'], i['payerId'], i['amount']) for i in before['items']]
                == [(i['itemId'], i['payerId'], i['amount']) for i in now['items']])


async def aa_publish_node(state: State, runtime: Runtime[Context]) -> dict:
    draft = state['aaDraft']
    try:
        value = await bank.aa_publish(draft['collectionId'], state['aaPublishRequestId'], runtime.context['authorization'])
    except bank.BankError:
        value = await bank.aa_get(draft['collectionId'], runtime.context['authorization'])
        if value['status'] not in ('PUBLISHED', 'PARTIAL', 'COMPLETED'):
            raise
    if value['status'] not in ('PUBLISHED', 'PARTIAL', 'COMPLETED') or not _aa_same_draft(draft, value):
        raise bank.BankError('银行没有确认 AA 按原始明细发布。', 409)
    return {'aaDraft': value, 'status': 'AA_PUBLISHED_PENDING_VERIFY'}


async def aa_verify_publish_node(state: State, runtime: Runtime[Context]) -> dict:
    value = await bank.aa_get(state['aaDraft']['collectionId'], runtime.context['authorization'])
    if value['status'] not in ('PUBLISHED', 'PARTIAL', 'COMPLETED') or not _aa_same_draft(state['aaDraft'], value):
        raise bank.BankError('AA 发布结果未核实，不能宣称已发送。', 409)
    return {'aaDraft': value, 'status': 'COMPLETED', 'details': 'AA 收款请求已发布，等待接收用户登录确认付款。'}


async def aa_discard_node(state: State, runtime: Runtime[Context]) -> dict:
    draft = state['aaDraft']
    try:
        value = await bank.aa_cancel_draft(draft['collectionId'], state['aaDiscardRequestId'], runtime.context['authorization'])
    except bank.BankError:
        value = await bank.aa_get(draft['collectionId'], runtime.context['authorization'])
        if value['status'] != 'CANCELLED':
            raise
    if value['status'] != 'CANCELLED' or not _aa_same_draft(draft, value):
        raise bank.BankError('银行未确认 AA 草稿已撤销。', 409)
    return {'aaDraft': value, 'status': 'REJECTED', 'details': '已取消 AA 草稿，其他用户未收到收款请求。'}



# Stage 4: the bank owns the future schedule. No Python timer or transfer execute.
def assign_schedule_prepare_request_id(state: State) -> dict:
    return {'scheduledPrepareRequestId': uuid4().hex}


async def schedule_prepare_node(state: State, runtime: Runtime[Context]) -> dict:
    c = state['transferCandidate']
    result = await bank.scheduled_prepare(c['id'], c['amount'], c['executeAt'],
                                          c['remark'], state['scheduledPrepareRequestId'],
                                          runtime.context['authorization'])
    _scheduled_check(state, result)
    if result['status'] != 'PENDING_AUTH':
        raise bank.BankError('银行预约没有进入待OTP授权状态。', 409)
    return {'scheduledDraft': result, 'status': 'SCHEDULE_PENDING_AUTH'}


def _scheduled_check(state: State, result: dict) -> None:
    from decimal import Decimal
    c = state['transferCandidate']
    previous = state.get('scheduledDraft') or result
    try:
        matches = (result['scheduleId'] == previous['scheduleId']
                   and result['payeeName'] == c['payeeName']
                   and result['accountMasked'] == c['accountMasked']
                   and Decimal(result['amount']) == Decimal(c['amount'])
                   and result['remark'] == c['remark']
                   and result['executeAt'] == c['executeAt'])
    except (KeyError, ValueError, TypeError, ArithmeticError):
        matches = False
    if not matches:
        raise bank.BankError('银行预约内容与用户确认的内容不一致。', 409)


def assign_schedule_action_ids(state: State) -> dict:
    return {'scheduledAuthorizeRequestId': uuid4().hex, 'scheduledCancelRequestId': uuid4().hex}


def wait_schedule_confirmation(state: State) -> dict:
    decision = interrupt({
        'kind': 'SCHEDULE_TRANSFER', 'scheduleId': state['scheduledDraft']['scheduleId'],
        'notice': '请核对固定金额、收款人及时间，并申请 OTP 完成预约专属预授权；此时不扣款。',
    })
    if type(decision) is not bool:
        return {'status': 'INVALID_APPROVAL', 'details': '预约必须明确确认。'}
    return {'scheduledDecision': decision, 'status': 'SCHEDULE_APPROVED' if decision else 'SCHEDULE_DECLINED'}


def after_schedule_confirmation(state: State):
    return 'schedule_authorize' if state['status'] == 'SCHEDULE_APPROVED' else ('schedule_discard' if state['status'] == 'SCHEDULE_DECLINED' else END)


async def schedule_authorize_node(state: State, runtime: Runtime[Context]) -> dict:
    """Verify prior explicit user OTP approval; do not POST again inside graph.

    OTP authorization is performed at the authenticated resume boundary BEFORE
    the interrupt checkpoint advances, so a wrong OTP permits a safe retry.
    """
    sid = state['scheduledDraft']['scheduleId']
    result = await bank.scheduled_get(sid, runtime.context['authorization'])
    _scheduled_check(state, result)
    if result['status'] not in ('SCHEDULED', 'SUCCESS'):
        raise bank.BankError('银行未确认预约已授权。', 409)
    return {'scheduledDraft': result, 'status': 'SCHEDULE_VERIFY_PENDING'}


async def schedule_verify_node(state: State, runtime: Runtime[Context]) -> dict:
    result = await bank.scheduled_get(state['scheduledDraft']['scheduleId'], runtime.context['authorization'])
    _scheduled_check(state, result)
    # Near-immediate appointment may already have executed before GET.
    if result['status'] not in ('SCHEDULED', 'SUCCESS'):
        raise bank.BankError('预约结果尚未确认，请查询原预约状态。', 409)
    return {'scheduledDraft': result, 'status': 'COMPLETED',
            'details': '预约预授权已完成；实际扣款只会在预约时间到达、银行确认执行成功后发生。'}


async def schedule_discard_node(state: State, runtime: Runtime[Context]) -> dict:
    sid = state['scheduledDraft']['scheduleId']
    try:
        result = await bank.scheduled_cancel(sid, state['scheduledCancelRequestId'], runtime.context['authorization'])
    except bank.BankError:
        result = await bank.scheduled_get(sid, runtime.context['authorization'])
        if result['status'] != 'CANCELLED':
            raise
    _scheduled_check(state, result)
    if result['status'] != 'CANCELLED':
        raise bank.BankError('银行未确认取消预约草稿。', 409)
    return {'scheduledDraft': result, 'status': 'REJECTED', 'details': '用户未授权，本次预约已取消。'}


builder = StateGraph(State, context_schema=Context)
builder.add_node('assign_schedule_prepare_request_id', assign_schedule_prepare_request_id)
builder.add_node('schedule_prepare', schedule_prepare_node)
builder.add_node('assign_schedule_action_ids', assign_schedule_action_ids)
builder.add_node('wait_schedule_confirmation', wait_schedule_confirmation)
builder.add_node('schedule_authorize', schedule_authorize_node)
builder.add_node('schedule_verify', schedule_verify_node)
builder.add_node('schedule_discard', schedule_discard_node)
builder.add_node('assign_aa_prepare_request_id', assign_aa_prepare_request_id)
builder.add_node('aa_prepare', aa_prepare_node)
builder.add_node('assign_aa_action_ids', assign_aa_action_ids)
builder.add_node('wait_aa_confirmation', wait_aa_confirmation)
builder.add_node('aa_publish', aa_publish_node)
builder.add_node('aa_verify_publish', aa_verify_publish_node)
builder.add_node('aa_discard', aa_discard_node)
builder.add_node('resolve_registered_recipient', resolve_registered_recipient)
builder.add_node('wait_for_recipient_selection', wait_for_recipient_selection)
builder.add_node('confirm_recipient', confirm_recipient)
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
builder.add_conditional_edges('validate', dispatch_reads, ['execute_read', 'summarize_reads', END])
builder.add_edge('execute_read', 'summarize_reads')
builder.add_edge('assign_schedule_prepare_request_id', 'schedule_prepare')
builder.add_edge('schedule_prepare', 'assign_schedule_action_ids')
builder.add_edge('assign_schedule_action_ids', 'wait_schedule_confirmation')
builder.add_conditional_edges('wait_schedule_confirmation', after_schedule_confirmation,
                              ['schedule_authorize', 'schedule_discard', END])
builder.add_edge('schedule_authorize', 'schedule_verify')
builder.add_edge('schedule_verify', END)
builder.add_edge('schedule_discard', END)
builder.add_edge('assign_aa_prepare_request_id', 'aa_prepare')
builder.add_edge('aa_prepare', 'assign_aa_action_ids')
builder.add_edge('assign_aa_action_ids', 'wait_aa_confirmation')
builder.add_conditional_edges('wait_aa_confirmation', after_aa_decision,
                              ['aa_publish', 'aa_discard', END])
builder.add_edge('aa_publish', 'aa_verify_publish')
builder.add_edge('aa_verify_publish', END)
builder.add_edge('aa_discard', END)
builder.add_conditional_edges('summarize_reads', after_reads,
                              ['match_target', 'resolve_registered_recipient', 'assign_aa_prepare_request_id', END])
builder.add_conditional_edges('resolve_registered_recipient', after_resolve_recipient,
                              ['confirm_recipient', 'wait_for_recipient_selection', END])
builder.add_conditional_edges('wait_for_recipient_selection', after_recipient_selection,
                              ['confirm_recipient', END])
builder.add_conditional_edges('confirm_recipient', after_confirm_recipient,
                              ['assign_transfer_request_id', 'assign_schedule_prepare_request_id'])
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
