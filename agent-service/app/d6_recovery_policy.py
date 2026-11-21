"""D6 pure, testable guard: only a verified transfer approval interrupt is resumable.

This module does not invoke LangGraph or any bank write. All decisions in this
module are based on an authenticated Java-owned session, the original SQLite
checkpoint and a freshly fetched authoritative Java bank order.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any


class RecoveryRefused(ValueError):
    """Fail closed: never silently fall back to starting a new workflow."""


def _amount(raw: Any) -> Decimal:
    try:
        value = Decimal(str(raw))
        if not value.is_finite() or value <= 0:
            raise ValueError('invalid amount')
        return value
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise RecoveryRefused('待恢复转账金额无效') from exc


def verify_transfer_recovery(session, snapshot, remote_order: dict,
                             claim: dict | None = None) -> dict:
    """Return safe summary, or deny recovery; never mutate state/bank.

    session: app.workflow_session_client.WorkflowSession
    snapshot: LangGraph StateSnapshot
    remote_order: authorized bank.get_order() response
    claim: Java claim, if any. CLAIMED/finished claims are non-replayable.
    """
    if claim is not None:
        raise RecoveryRefused('此线程已经领取过恢复操作，请只读核对银行订单，不要重复执行')
    if session.status != 'WAITING' or session.expired:
        raise RecoveryRefused('工作流未处于有效待审批状态或已过期')
    if not session.sourceRequestId:
        raise RecoveryRefused('工作流来源消息缺失')
    if list(snapshot.next or []) != ['wait_for_transfer_approval']:
        raise RecoveryRefused('检查点不是明确的转账人工审批中断点')
    if not any(getattr(t, 'interrupts', ()) for t in (snapshot.tasks or ())):
        raise RecoveryRefused('检查点缺少可验证的人工中断记录')
    state = snapshot.values or {}
    if not isinstance(state, dict):
        raise RecoveryRefused('检查点状态不合法')
    if isinstance(state.get('transferDecision'), bool):
        raise RecoveryRefused('原审批决定已经写入图状态，禁止再次授权')
    candidate = state.get('transferCandidate')
    saved_order = state.get('transferOrder')
    if not isinstance(candidate, dict) or not isinstance(saved_order, dict):
        raise RecoveryRefused('检查点没有完整的银行订单数据')
    for key in ('transferAuthorizeRequestId', 'transferExecuteRequestId',
                'transferCancelRequestId'):
        if not isinstance(state.get(key), str) or len(state[key]) < 8:
            raise RecoveryRefused('检查点缺少原有的幂等请求编号')
    try:
        saved_id = str(saved_order['orderId'])
        actual_id = str(remote_order['orderId'])
        payee = str(candidate['payeeName'])
        masked = str(candidate['accountMasked'])
        amount = _amount(candidate['amount'])
        matched = (
            actual_id == saved_id
            and remote_order['payeeName'] == payee
            and remote_order['accountMasked'] == masked
            and _amount(remote_order['amount']) == amount
            and remote_order.get('remark') == candidate.get('remark')
            and remote_order['riskLevel'] == saved_order['riskLevel']
            and remote_order['riskLevel'] in ('YELLOW', 'RED')
            and remote_order['status'] == 'PENDING_APPROVAL'
        )
    except (KeyError, TypeError, ValueError):
        matched = False
    if not matched:
        raise RecoveryRefused('银行真实订单与原检查点不匹配，或订单已不再待审批')
    config = snapshot.config or {}
    checkpoint_id = (config.get('configurable') or {}).get('checkpoint_id')
    if not isinstance(checkpoint_id, str) or len(checkpoint_id) < 8:
        raise RecoveryRefused('缺少稳定的检查点编号')
    return {
        'threadId': str(session.threadId),
        'conversationId': str(session.conversationId),
        'checkpointId': checkpoint_id,
        'orderId': saved_id,
        'payeeName': payee,
        'accountMasked': masked,
        'amount': f'{amount:.2f}',
        'remark': candidate.get('remark') or '',
        'riskLevel': remote_order['riskLevel'],
        'bankOrderStatus': 'PENDING_APPROVAL',
        'canResume': True,
        'requiresOtp': remote_order['riskLevel'] == 'RED',
        'expiresAt': session.expiresAt.isoformat(),
    }
