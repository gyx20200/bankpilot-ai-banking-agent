"""Single Day 6 dynamic entrypoint: concurrent bank reads + at most one approval.

The model only plans tasks. Only the authenticated /resume endpoint can supply a
human approval. OTP stays in runtime context, never in graph state or responses.
Banking backends independently enforce user ownership, risk controls and idempotency.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, HTTPException
from langgraph.types import Command
from pydantic import BaseModel, Field, StrictBool

from app import banking_client as bank
from app.assistant_history import (
    AssistantHistoryError, assistant_reply_text, save_assistant_reply,
)
from app.context.history_client import load_planner_context
from app.graph.dynamic_cancellation_workflow import dynamic_graph
from app.graph.task_planner import PlannerError
from app.checkpoint_runtime import persistent_enabled
from app.workflow_session_client import (
    register_session, get_session, list_sessions, update_session_status,
)

router = APIRouter(prefix='/api/agent/workflows', tags=['Dynamic Workflow'])

# Demo-only single-process session/checkpoint metadata, keyed by Java-verified
# userId rather than bearer token. Restart loses checkpoints: bank orders remain
# queryable through Java, but old graph threads must not be fabricated.
_sessions: dict[str, dict] = {}
_locks: dict[str, asyncio.Lock] = {}
_EXPIRY = timedelta(minutes=30)


class StartBody(BaseModel):
    message: str = Field(min_length=1, max_length=300)
    conversationId: UUID | None = None
    userMessageRequestId: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9_-]{8,64}$"
    )


class ThreadBody(BaseModel):
    threadId: str = Field(min_length=8, max_length=128)


class RecipientSelectBody(ThreadBody):
    recipientId: int = Field(gt=0)


class DecisionBody(ThreadBody):
    approved: StrictBool
    otpCode: str | None = Field(default=None, pattern=r'^\d{6}$')


async def _authenticated_user(bearer: str | None) -> int:
    """Resolve identity with Java on EVERY protected workflow operation.

    Do not trust userId from browser, model, stale tokens or a decoded token.
    This also rejects logged-out/expired tokens before touching a checkpoint.
    """
    try:
        principal = await bank.current_user(bearer)
    except bank.BankError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    user_id = principal.get('userId')
    if type(user_id) is not int or user_id <= 0:
        raise HTTPException(502, '银行认证身份缺失，不能执行工作流。')
    return user_id


async def _owner(thread: str, bearer: str | None, *, read_only: bool = False) -> dict:
    user_id = await _authenticated_user(bearer)
    if persistent_enabled():
        # This call enforces user ownership in Java; never trust a browser-supplied thread ID.
        session = await get_session(thread, bearer)
        if session.expired:
            raise HTTPException(410, '工作流已过期；只能查看银行原始订单。')
        if not read_only and session.status != 'WAITING':
            raise HTTPException(409, '当前工作流未处于可交互的等待状态。')
    rec = _sessions.get(thread)
    if not rec or rec.get('ownerUserId') != user_id:
        # NEVER reconstruct _sessions from a checkpoint in D5.
        raise HTTPException(409 if persistent_enabled() else 403,
                            '工作流不属于当前进程的可操作任务；请使用只读恢复查看，勿重复建单。')
    if datetime.now(timezone.utc) > rec['expires']:
        raise HTTPException(410, '任务已过期，请查询原银行订单状态，勿盲目重复操作。')
    return rec

async def _invoke_graph(value, config, *, context):
    options = {'context': context}
    if persistent_enabled():
        options['durability'] = 'sync'
    return await dynamic_graph.ainvoke(value, config, **options)


def _lifecycle(view: dict, paused: bool) -> str:
    if paused:
        return 'WAITING'
    status = view.get('status')
    if status in ('COMPLETED', 'REJECTED'):
        return status
    if status in ('UNKNOWN', 'NOT_CONFIRMED', 'INCOMPLETE'):
        return 'NOT_CONFIRMED'
    return 'ENDED'


async def _sync_workflow_status(thread: str, view: dict, paused: bool,
                                authorization: str | None) -> None:
    if not persistent_enabled():
        return
    try:
        await update_session_status(thread, _lifecycle(view, paused), authorization)
    except HTTPException as exc:
        # A bank side effect may already have happened. Freeze the in-memory
        # interactive capability and require explicit read-only reconciliation.
        _sessions.pop(thread, None)
        _locks.pop(thread, None)
        raise HTTPException(503,
            f'工作流持久化状态未确认，原threadId={thread}；请查询原银行订单，勿重复发起。') from exc


def _config(thread: str) -> dict:
    return {'configurable': {'thread_id': thread}}


def _view(thread: str, state: dict, paused: bool = False) -> dict:
    # The top-level status belongs to the WORKFLOW; bank order status is separate.
    kind = None
    if paused:
        if state.get('scheduledDraft'):
            kind = 'schedule'
        elif state.get('aaDraft'):
            kind = 'aa'
        elif state.get('recipientChoices') and not state.get('transferOrder'):
            kind = 'recipient'
        elif state.get('transferOrder'):
            kind = 'transfer'
        elif state.get('cancellationOrder'):
            kind = 'cancel'
    status = ({'transfer': 'WAITING_TRANSFER_APPROVAL',
               'cancel': 'WAITING_APPROVAL',
               'recipient': 'WAITING_RECIPIENT_SELECTION',
               'aa': 'WAITING_AA_CONFIRMATION',
               'schedule': 'WAITING_SCHEDULE_AUTH'}.get(kind, 'UNKNOWN')
              if paused else state.get('status', 'UNKNOWN'))
    return {
        'threadId': thread, 'status': status, 'plan': state.get('plan'),
        'results': state.get('results', {}), 'candidate': state.get('candidate'),
        'cancellationOrder': state.get('cancellationOrder'),
        'transferCandidate': state.get('transferCandidate'),
        'recipientChoices': state.get('recipientChoices', []),
        'transferOrder': state.get('transferOrder'),
        'aaCollection': state.get('aaDraft'),
        'scheduledTransfer': state.get('scheduledDraft'),
        'approvalType': kind,
        'approvalDecision': (state.get('aaDecision') if state.get('aaDraft')
                             else state.get('scheduledDecision') if state.get('scheduledDraft')
                             else state.get('transferDecision') if state.get('transferOrder')
                             else state.get('approvalDecision')),
        'details': state.get('details', ''),
    }


def _pending(snapshot) -> str | None:
    nodes = set(snapshot.next or ())
    if 'wait_aa_confirmation' in nodes:
        return 'aa'
    if 'wait_schedule_confirmation' in nodes:
        return 'schedule'
    if 'wait_for_recipient_selection' in nodes:
        return 'recipient'
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
                 and (not candidate.get('remark') or remote.get('remark') == candidate['remark'])
                 and remote['riskLevel'] in ('YELLOW', 'RED'))
    except (KeyError, ValueError, TypeError, ArithmeticError):
        valid = False
    if not valid:
        raise HTTPException(409, '银行订单与待审批的收款人或金额不一致，请停止操作。')


def _aa_draft_matches(expected: dict, actual: dict) -> bool:
    return (expected.get('collectionId') == actual.get('collectionId')
            and expected.get('initiatorId') == actual.get('initiatorId')
            and expected.get('requestedAmount') == actual.get('requestedAmount')
            and [(x.get('itemId'), x.get('payerId'), x.get('amount')) for x in expected.get('items', [])]
                == [(x.get('itemId'), x.get('payerId'), x.get('amount')) for x in actual.get('items', [])])


@router.post('/dynamic/start')
async def dynamic_start(body: StartBody, authorization: str | None = Header(default=None)):
    owner_user_id = await _authenticated_user(authorization)
    has_conversation = body.conversationId is not None
    has_source = body.userMessageRequestId is not None
    if has_conversation != has_source:
        raise HTTPException(422, 'conversationId 与 userMessageRequestId 必须同时提供。')
    if persistent_enabled() and not has_conversation:
        raise HTTPException(422, '持久化模式要求会话ID和本轮USER消息requestId，禁止无归属建单。')
    thread = str(uuid4())

    # Verify the D3 conversation and load its history BEFORE registering the graph.
    planner_context = None
    if has_conversation:
        planner_context = await load_planner_context(
            conversation_id=body.conversationId,
            current_message=body.message,
            authorization=authorization,
        )

    registered = False
    if persistent_enabled():
        # Java checks JWT owner, active conversation, actual USER message and
        # unique (conversation_id, source_request_id) before ANY graph side effect.
        # Java failure or duplicate registration prevents Graph execution.
        await register_session(thread, str(body.conversationId),
                               body.userMessageRequestId, body.message, authorization)
        registered = True

    try:
        state = await _invoke_graph(
            {'message': body.message},
            _config(thread),
            context={'authorization': authorization,
                     'planner_context': planner_context},
        )
    except Exception as exc:
        if registered:
            try:
                await update_session_status(thread, 'NOT_CONFIRMED', authorization)
            except Exception:
                pass  # Keep the original threadId; never retry graph execution.
        if isinstance(exc, PlannerError):
            raise HTTPException(422, str(exc)) from exc
        if isinstance(exc, bank.BankError):
            raise HTTPException(exc.status,
                f'{exc}；原threadId={thread}，不得重复发起资金任务。') from exc
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(503,
            f'工作流执行结果不确定，原threadId={thread}；请核对银行原订单，勿重复提交。') from exc

    paused = bool(state.get('__interrupt__'))
    view = _view(thread, state, paused)
    await _sync_workflow_status(thread, view, paused, authorization)
    if paused:
        _sessions[thread] = {
            'ownerUserId': owner_user_id,
            'expires': datetime.now(timezone.utc) + _EXPIRY,
            'finished': False, 'decision': None, 'last': view,
        }
        _locks[thread] = asyncio.Lock()

    # Reply text is persisted by Java independently. Never rerun the graph just
    # because assistant history failed or timed out.
    reply = assistant_reply_text(view)
    view['assistantReply'] = reply
    if has_conversation:
        try:
            view['assistantReply'] = await save_assistant_reply(
                conversation_id=str(body.conversationId),
                user_message_request_id=body.userMessageRequestId,
                user_message_content=body.message,
                authorization=authorization,
                reply=reply,
            )
            view['assistantPersisted'] = True
        except AssistantHistoryError as exc:
            print(f'[D3 AssistantHistory] {exc}', flush=True)
            view['assistantPersisted'] = False
            view['assistantHistoryWarning'] = (
                '助手回复未确认写入历史。请核对当前会话记录；'
                '不要为了保存回复而重复发送转账或审批指令。'
            )
    else:
        view['assistantPersisted'] = False
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
    record = await _owner(thread_id, authorization, read_only=True)
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
        if state.get('scheduledDraft'):
            value = await bank.scheduled_get(state['scheduledDraft']['scheduleId'], authorization)
            view['bankOrderStatus'] = value['status']
        elif state.get('aaDraft'):
            value = await bank.aa_get(state['aaDraft']['collectionId'], authorization)
            view['bankOrderStatus'] = value['status']
        elif state.get('transferOrder'):
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


@router.get('/sessions')
async def workflow_sessions(conversationId: UUID,
                            authorization: str | None = Header(default=None)):
    await _authenticated_user(authorization)
    if not persistent_enabled():
        raise HTTPException(409, '当前未启用持久化 Checkpoint。')
    rows = await list_sessions(str(conversationId), authorization)
    return {'conversationId': str(conversationId), 'items': [
        {**item.model_dump(mode='json'), 'expired': item.expired}
        for item in rows
    ]}


@router.get('/dynamic/{thread_id}/recovery')
async def workflow_recovery(thread_id: UUID,
                            authorization: str | None = Header(default=None)):
    await _authenticated_user(authorization)
    if not persistent_enabled():
        raise HTTPException(409, '当前未启用持久化 Checkpoint。')
    thread = str(thread_id)
    # Java performs owner + session checks; never read SQLite first.
    rec = await get_session(thread, authorization)
    snap = await dynamic_graph.aget_state(_config(thread))
    state = snap.values or {}
    found = bool(state or snap.next or snap.tasks)
    paused = bool(_pending(snap)) if found else False
    order_id = None
    bank_status = 'UNKNOWN'
    if found:
        try:
            if state.get('transferOrder'):
                order_id = str(state['transferOrder']['orderId'])
                remote = await bank.get_order(order_id, authorization)
                _read_bank_order_matches(state, remote)
                bank_status = remote['status']
            elif state.get('scheduledDraft'):
                order_id = str(state['scheduledDraft']['scheduleId'])
                remote = await bank.scheduled_get(order_id, authorization)
                _check_scheduled(state, remote)
                bank_status = remote['status']
            elif state.get('aaDraft'):
                order_id = str(state['aaDraft']['collectionId'])
                remote = await bank.aa_get(order_id, authorization)
                if not _aa_draft_matches(state['aaDraft'], remote):
                    raise ValueError('AA draft mismatch')
                bank_status = remote['status']
            elif state.get('cancellationOrder'):
                order_id = str(state['cancellationOrder']['orderId'])
                remote = await bank.get_subscription_cancellation(order_id, authorization)
                if (str(remote.get('orderId')) != order_id
                        or remote.get('subscriptionId') != (state.get('candidate') or {}).get('id')):
                    raise ValueError('subscription order mismatch')
                bank_status = remote['status']
        except (bank.BankError, HTTPException, KeyError, ValueError, TypeError):
            bank_status = 'UNKNOWN'
    return {
        'threadId': thread,
        'conversationId': str(rec.conversationId),
        'checkpointFound': found,
        'nextNodes': list(snap.next or ())[:20] if found else [],
        'status': _view(thread, state, paused)['status'] if found else 'UNKNOWN',
        'lifecycleStatus': rec.status,
        'orderId': order_id,
        'bankOrderStatus': bank_status,
        'expired': rec.expired,
        'readOnly': True,
        'canResume': False,
    }


@router.post('/dynamic/recipient/select')
async def select_recipient(body: RecipientSelectBody,
                           authorization: str | None = Header(default=None)):
    """Human selection is a distinct action, not approval of a transfer."""
    record = await _owner(body.threadId, authorization)
    async with _locks[body.threadId]:
        if record['finished']:
            raise HTTPException(409, '工作流已经结束。')
        config = _config(body.threadId)
        snap = await dynamic_graph.aget_state(config)
        if _pending(snap) != 'recipient':
            raise HTTPException(409, '目前没有等待选择的收款人。')
        state = snap.values or {}
        choices = state.get('recipientChoices') or []
        if not any(item.get('recipientId') == body.recipientId for item in choices):
            raise HTTPException(422, '选择不属于银行返回的候选收款人。')
        try:
            result = await _invoke_graph(Command(resume=body.recipientId), config,
                         context={'authorization': authorization})
        except bank.BankError as exc:
            raise HTTPException(exc.status, str(exc)) from exc
        paused = bool(result.get('__interrupt__'))
        view = _view(body.threadId, result, paused)
        if not paused and result.get('status') not in ('COMPLETED', 'REJECTED'):
            # Do not create a fresh order after uncertain bank-side effects.
            raise HTTPException(409, '收款人选择未进入审批状态，请刷新原线程核查。')
        await _sync_workflow_status(body.threadId, view, paused, authorization)
        if not paused:
            record.update(finished=True, last=view)
        return view


@router.post('/dynamic/recipient/cancel')
async def cancel_recipient_selection(body: ThreadBody,
                                     authorization: str | None = Header(default=None)):
    record = await _owner(body.threadId, authorization)
    async with _locks[body.threadId]:
        if record['finished']:
            return record['last']
        config = _config(body.threadId)
        snap = await dynamic_graph.aget_state(config)
        if _pending(snap) != 'recipient':
            raise HTTPException(409, '当前没有等待选择的收款人。')
        result = await _invoke_graph(Command(resume=False), config,
                          context={'authorization': authorization})
        if result.get('__interrupt__') or result.get('status') != 'REJECTED' or result.get('transferOrder'):
            raise HTTPException(409, '无法确认已退出收款人选择，请查询原任务状态。')
        view = _view(body.threadId, result)
        await _sync_workflow_status(body.threadId, view, False, authorization)
        record.update(finished=True, decision=False, last=view)
        return view


@router.post('/dynamic/transfer/otp/request')
async def request_transfer_otp(body: ThreadBody, authorization: str | None = Header(default=None)):
    record = await _owner(body.threadId, authorization)
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


@router.post('/dynamic/schedule/otp/request')
async def request_schedule_otp(body: ThreadBody, authorization: str | None = Header(default=None)):
    record = await _owner(body.threadId, authorization)
    async with _locks[body.threadId]:
        if record['finished']:
            raise HTTPException(409, '任务已经结束。')
        snap = await dynamic_graph.aget_state(_config(body.threadId))
        if _pending(snap) != 'schedule':
            raise HTTPException(409, '当前没有等待 OTP 的预约申请。')
        state = snap.values or {}
        draft = state.get('scheduledDraft') or {}
        try:
            remote = await bank.scheduled_get(draft['scheduleId'], authorization)
            _check_scheduled(state, remote)
            if remote['status'] != 'PENDING_AUTH':
                raise HTTPException(409, '预约已不处于待强验证状态。')
            res = await bank.scheduled_otp_request(remote['scheduleId'], authorization)
        except bank.BankError as exc:
            raise HTTPException(exc.status, str(exc)) from exc
        return {'threadId': body.threadId, 'scheduleId': draft['scheduleId'],
                'expiresInSeconds': res['expiresInSeconds'], 'status': 'OTP_REQUESTED'}


def _check_scheduled(state: dict, remote: dict) -> None:
    c = state.get('transferCandidate') or {}
    d = state.get('scheduledDraft') or {}
    try:
        valid = (d.get('scheduleId') == remote.get('scheduleId')
                 and remote.get('payeeName') == c.get('payeeName')
                 and remote.get('accountMasked') == c.get('accountMasked')
                 and Decimal(str(remote['amount'])) == Decimal(str(c['amount']))
                 and remote.get('remark') == c.get('remark')
                 and remote.get('executeAt') == c.get('executeAt'))
    except (ValueError, TypeError, KeyError, ArithmeticError):
        valid = False
    if not valid:
        raise HTTPException(409, '银行预约信息与待授权内容不一致。')


@router.post('/dynamic/resume')
async def dynamic_resume(body: DecisionBody, authorization: str | None = Header(default=None)):
    record = await _owner(body.threadId, authorization)
    async with _locks[body.threadId]:
        if record['finished']:
            if record['decision'] != body.approved:
                raise HTTPException(409, '任务已按另一个审批决定完成，不能修改。')
            return record['last']

        config = _config(body.threadId)
        snap = await dynamic_graph.aget_state(config)
        state = snap.values or {}
        kind = _pending(snap)
        approved_before = (state.get('aaDecision') if state.get('aaDraft') else
                           state.get('scheduledDecision') if state.get('scheduledDraft') else
                           state.get('transferDecision' if state.get('transferOrder') else 'approvalDecision'))
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
            elif kind == 'schedule':
                try:
                    remote = await bank.scheduled_get(state['scheduledDraft']['scheduleId'], authorization)
                    _check_scheduled(state, remote)
                    if remote['status'] not in ('PENDING_AUTH', 'SCHEDULED', 'SUCCESS'):
                        raise HTTPException(409, '预约已不是待授权状态。')
                except bank.BankError as exc:
                    raise HTTPException(exc.status, str(exc)) from exc
                if body.approved and remote['status'] == 'PENDING_AUTH':
                    if not body.otpCode:
                        raise HTTPException(422, '所有定时转账必须预先完成 OTP 验证。')
                    # Before advancing the graph interrupt, verify OTP using the
                    # checkpoint-stable idempotency key. Invalid codes leave the
                    # interrupt pending, so the same user may request a fresh OTP.
                    try:
                        signed = await bank.scheduled_authorize(
                            remote['scheduleId'], state['scheduledAuthorizeRequestId'],
                            body.otpCode, authorization)
                        _check_scheduled(state, signed)
                        if signed['status'] not in ('SCHEDULED', 'SUCCESS'):
                            raise HTTPException(409, '银行未确认专属预授权。')
                    except bank.BankError as exc:
                        raise HTTPException(exc.status, str(exc)) from exc
            elif kind == 'aa':
                try:
                    remote = await bank.aa_get(state['aaDraft']['collectionId'], authorization)
                    if remote['status'] != 'DRAFT' or not _aa_draft_matches(state['aaDraft'], remote):
                        raise HTTPException(409, '银行 AA 草稿发生变化，无法确认发布。')
                except bank.BankError as exc:
                    raise HTTPException(exc.status, str(exc)) from exc
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
            result = await _invoke_graph(command, config,
                          context={'authorization': authorization,
                                   'transferOtpCode': body.otpCode if body.approved else None})
        except bank.BankError as exc:
            raise HTTPException(exc.status, str(exc)) from exc
        if result.get('__interrupt__'):
            raise HTTPException(409, '工作流意外再次暂停，请查询原线程状态。')
        if result.get('status') not in ('COMPLETED', 'REJECTED'):
            raise HTTPException(409, result.get('details') or '银行未确认最终业务状态。')
        view = _view(body.threadId, result)
        await _sync_workflow_status(body.threadId, view, False, authorization)
        record.update(finished=True, decision=body.approved, last=view)
        return view
