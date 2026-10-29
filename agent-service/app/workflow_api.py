"""Single Day 6 dynamic entrypoint: concurrent bank reads + at most one approval.

The model only plans tasks. Only the authenticated /resume endpoint can supply a
human approval. OTP stays in runtime context, never in graph state or responses.
Banking backends independently enforce user ownership, risk controls and idempotency.
"""
import asyncio
import hashlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException
from langgraph.types import Command
from pydantic import BaseModel, Field, StrictBool

from app import banking_client as bank
from app.graph.dynamic_cancellation_workflow import dynamic_graph
from app.graph.task_planner import PlannerError

router = APIRouter(prefix='/api/agent/workflows', tags=['Dynamic Workflow'])

# Demo-only single-process session/checkpoint metadata. Real bank deployment
# needs a durable checkpointer and owner records keyed to Java-authenticated user.
_sessions: dict[str, dict] = {}
_locks: dict[str, asyncio.Lock] = {}
_EXPIRY = timedelta(minutes=30)


class StartBody(BaseModel):
    message: str = Field(min_length=1, max_length=300)


class ThreadBody(BaseModel):
    threadId: str = Field(min_length=8, max_length=128)


class DecisionBody(ThreadBody):
    approved: StrictBool
    otpCode: str | None = Field(default=None, pattern=r'^\d{6}$')


def _identity(bearer: str | None) -> str:
    if not bearer or not bearer.startswith('Bearer ') or not bearer[7:].strip():
        raise HTTPException(401, '请先登录演示银行。')
    return hashlib.sha256(bearer.encode()).hexdigest()


def _owner(thread: str, bearer: str | None) -> dict:
    owner = _identity(bearer)
    rec = _sessions.get(thread)
    if not rec or rec['owner'] != owner:
        raise HTTPException(403, '任务不存在或不属于当前用户。')
    if datetime.now(timezone.utc) > rec['expires']:
        raise HTTPException(410, '任务已过期，请查询原银行订单状态，勿盲目重复操作。')
    return rec


def _config(thread: str) -> dict:
    return {'configurable': {'thread_id': thread}}


def _view(thread: str, state: dict, paused: bool = False) -> dict:
    # The top-level status belongs to the WORKFLOW; bank order status is separate.
    kind = None
    if paused:
        if state.get('transferOrder'):
            kind = 'transfer'
        elif state.get('cancellationOrder'):
            kind = 'cancel'
    status = ('WAITING_TRANSFER_APPROVAL' if kind == 'transfer' else 'WAITING_APPROVAL') if paused else state.get('status', 'UNKNOWN')
    return {
        'threadId': thread, 'status': status, 'plan': state.get('plan'),
        'results': state.get('results', {}), 'candidate': state.get('candidate'),
        'cancellationOrder': state.get('cancellationOrder'),
        'transferCandidate': state.get('transferCandidate'),
        'transferOrder': state.get('transferOrder'),
        'approvalType': kind,
        'approvalDecision': (state.get('transferDecision') if state.get('transferOrder')
                             else state.get('approvalDecision')),
        'details': state.get('details', ''),
    }


def _pending(snapshot) -> str | None:
    nodes = set(snapshot.next or ())
    if 'wait_for_transfer_approval' in nodes:
        return 'transfer'
    if 'wait_for_approval' in nodes:
        return 'cancel'
    return None


def _read_bank_order_matches(state: dict, remote: dict) -> None:
    prev = state['transferOrder']
    candidate = state['transferCandidate']
    try:
        valid = (str(remote['orderId']) == str(prev['orderId'])
                 and remote['payeeName'] == candidate['payeeName']
                 and remote['accountMasked'] == candidate['accountMasked']
                 and Decimal(str(remote['amount'])) == Decimal(str(candidate['amount']))
                 and remote['riskLevel'] in ('YELLOW', 'RED'))
    except (KeyError, ValueError, TypeError, ArithmeticError):
        valid = False
    if not valid:
        raise HTTPException(409, '银行订单与待审批的收款人或金额不一致，请停止操作。')


@router.post('/dynamic/start')
async def dynamic_start(body: StartBody, authorization: str | None = Header(default=None)):
    owner = _identity(authorization)
    thread = str(uuid4())
    try:
        state = await dynamic_graph.ainvoke({'message': body.message}, _config(thread),
                                            context={'authorization': authorization})
    except PlannerError as exc:
        raise HTTPException(422, str(exc)) from exc
    except bank.BankError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    paused = bool(state.get('__interrupt__'))
    view = _view(thread, state, paused)
    if paused:
        _sessions[thread] = {'owner': owner, 'expires': datetime.now(timezone.utc) + _EXPIRY,
                             'finished': False, 'decision': None, 'last': view}
        _locks[thread] = asyncio.Lock()
    return view


def _bank_verified_user_rejection(snapshot, state: dict, order: dict) -> bool:
    """Reconcile only a SAVED user rejection with a verified terminal Java order.

    Never derive a user's approval decision from the bank status alone, and
    never perform a bank write from the GET status endpoint.
    """
    if state.get('approvalDecision') is not False or state.get('transferOrder'):
        return False
    remaining = set(snapshot.next or ())
    if not remaining or not remaining.issubset({'reject', 'verify_rejected'}):
        return False
    saved_order = state.get('cancellationOrder') or {}
    candidate = state.get('candidate') or {}
    return (
        str(order.get('orderId')) == str(saved_order.get('orderId'))
        and order.get('subscriptionId') == candidate.get('id')
        and order.get('status') == 'CANCELLED'
        and order.get('subscriptionStatus') == 'ACTIVE'
    )


@router.get('/dynamic/{thread_id}')
async def dynamic_status(thread_id: str, authorization: str | None = Header(default=None)):
    record = _owner(thread_id, authorization)
    if record['finished']:
        return record['last']
    # Read-only recovery: never calls a bank write endpoint.
    snap = await dynamic_graph.aget_state(_config(thread_id))
    state = snap.values or {}
    paused = bool(_pending(snap))
    view = _view(thread_id, state, paused)
    if not paused and snap.next:
        view['status'] = 'NOT_CONFIRMED'
        view['details'] = '工作流存在待恢复节点；核实原银行订单后，可以使用原审批决定恢复，勿新建订单。'
    if not snap.next and state.get('status') in ('COMPLETED', 'REJECTED'):
        record.update(finished=True, decision=view['approvalDecision'], last=view)
    # Read-only bank reconciliation helps users inspect an uncertain outcome.
    try:
        if state.get('transferOrder'):
            order = await bank.get_order(str(state['transferOrder']['orderId']), authorization)
            _read_bank_order_matches(state, order)
            view['bankOrderStatus'] = order['status']
        elif state.get('cancellationOrder'):
            order = await bank.get_subscription_cancellation(
                state['cancellationOrder']['orderId'], authorization)
            if (str(order.get('orderId')) == str(state['cancellationOrder']['orderId'])
                    and order.get('subscriptionId') == state['candidate']['id']):
                view['bankOrderStatus'] = order['status']
                view['bankSubscriptionStatus'] = order.get('subscriptionStatus')
                # A failed post-decision graph step may leave a checkpoint with
                # pending 'reject' or 'verify_rejected', even though Java has
                # already closed the application.  Reconcile only when the
                # original explicit rejection is stored in the graph state.
                if _bank_verified_user_rejection(snap, state, order):
                    view['status'] = 'REJECTED'
                    view['details'] = ('已核对原银行取消申请为 CANCELLED，'
                                       '原订阅保持 ACTIVE；用户拒绝已生效。')
                    view['approvalDecision'] = False
                    view['reconciledFromBank'] = True
                    record.update(finished=True, decision=False, last=view)
    except (bank.BankError, HTTPException):
        view['bankOrderStatus'] = 'UNKNOWN'
    return view


@router.post('/dynamic/transfer/otp/request')
async def request_transfer_otp(body: ThreadBody, authorization: str | None = Header(default=None)):
    record = _owner(body.threadId, authorization)
    async with _locks[body.threadId]:
        if record['finished']:
            raise HTTPException(409, '任务已结束，不得重新申请 OTP。')
        snap = await dynamic_graph.aget_state(_config(body.threadId))
        state = snap.values or {}
        if _pending(snap) != 'transfer':
            raise HTTPException(409, '当前没有等待 OTP 验证的转账。')
        order = state['transferOrder']
        try:
            remote = await bank.get_order(str(order['orderId']), authorization)
            _read_bank_order_matches(state, remote)
            if remote['status'] != 'PENDING_APPROVAL' or remote['riskLevel'] != 'RED':
                raise HTTPException(409, '银行订单不属于待审批的 RED 风险转账。')
            result = await bank.request_transfer_otp(str(order['orderId']), authorization)
        except bank.BankError as exc:
            raise HTTPException(exc.status, str(exc)) from exc
        return {'threadId': body.threadId, 'orderId': order['orderId'],
                'status': 'OTP_REQUESTED', 'expiresInSeconds': result['expiresInSeconds']}


@router.post('/dynamic/resume')
async def dynamic_resume(body: DecisionBody, authorization: str | None = Header(default=None)):
    record = _owner(body.threadId, authorization)
    async with _locks[body.threadId]:
        if record['finished']:
            if record['decision'] != body.approved:
                raise HTTPException(409, '任务已按另一个审批决定完成，不能修改。')
            return record['last']

        config = _config(body.threadId)
        snap = await dynamic_graph.aget_state(config)
        state = snap.values or {}
        kind = _pending(snap)
        approved_before = state.get('transferDecision' if state.get('transferOrder') else 'approvalDecision')
        if kind:
            if body.approved and kind == 'transfer':
                try:
                    remote = await bank.get_order(str(state['transferOrder']['orderId']), authorization)
                    _read_bank_order_matches(state, remote)
                except bank.BankError as exc:
                    raise HTTPException(exc.status, str(exc)) from exc
                if remote['status'] not in ('PENDING_APPROVAL', 'AUTHORIZED', 'SUCCESS'):
                    raise HTTPException(409, '该转账订单不允许继续授权，请查询银行状态。')
                if remote['riskLevel'] == 'RED' and remote['status'] == 'PENDING_APPROVAL' and not body.otpCode:
                    raise HTTPException(422, '高风险转账必须提供银行 OTP 验证码。')
            elif kind == 'cancel':
                try:
                    remote = await bank.get_subscription_cancellation(
                        state['cancellationOrder']['orderId'], authorization)
                except bank.BankError as exc:
                    raise HTTPException(exc.status, str(exc)) from exc
                if remote.get('orderId') != state['cancellationOrder']['orderId'] or remote.get('subscriptionId') != state['candidate']['id']:
                    raise HTTPException(409, '银行取消申请与待审批订阅不一致。')
            command = Command(resume=body.approved)
        elif type(approved_before) is bool and approved_before == body.approved and snap.next:
            # Network/database ambiguity: keep the SAME saved requestIds.
            # Re-enter the checkpointed node, never create a fresh order.
            command = None
        else:
            raise HTTPException(409, '任务没有等待审批，或审批决定已经改变。')

        try:
            result = await dynamic_graph.ainvoke(command, config,
                          context={'authorization': authorization,
                                   'transferOtpCode': body.otpCode if body.approved else None})
        except bank.BankError as exc:
            raise HTTPException(exc.status, str(exc)) from exc
        if result.get('__interrupt__'):
            raise HTTPException(409, '工作流意外再次暂停，请查询原线程状态。')
        if result.get('status') not in ('COMPLETED', 'REJECTED'):
            raise HTTPException(409, result.get('details') or '银行未确认最终业务状态。')
        view = _view(body.threadId, result)
        record.update(finished=True, decision=body.approved, last=view)
        return view
