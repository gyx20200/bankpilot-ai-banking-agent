"""D6 safe post-restart transfer recovery routes.

Only the exact, verified transfer-approval interrupt is resumable. Graph is
invoked AFTER a durable one-shot Java claim. Ambiguous outcomes are frozen for
manual bank order reconciliation; never auto-replay an approval.

D6 P0 scope: TRANSFER YELLOW/RED approval or rejection. Other approvals remain
D5 read-only until independently audited and tested.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, HTTPException
from langgraph.types import Command
from pydantic import BaseModel, Field, StrictBool

from app import banking_client as bank
from app import workflow_api as wf  # Module reference picks up lifespan's persistent graph!
from app.checkpoint_runtime import persistent_enabled
from app.workflow_session_client import get_session
from app.d6_recovery_claim_client import get_claim, create_claim, finalize_claim
from app.d6_recovery_policy import RecoveryRefused, verify_transfer_recovery

router = APIRouter(prefix='/api/agent/workflows/recovery', tags=['D6 Safe Recovery'])


class ResumeRequest(BaseModel):
    approved: StrictBool
    expectedCheckpointId: str = Field(min_length=8, max_length=128)
    expectedOrderId: str = Field(min_length=1, max_length=128)
    expectedAccountMasked: str = Field(min_length=1, max_length=80)
    expectedAmount: str = Field(min_length=1, max_length=32)
    otpCode: str | None = Field(default=None, pattern=r'^\d{6}$')


async def _preflight(thread: str, authorization: str):
    if not persistent_enabled():
        raise HTTPException(409, 'D6 恢复只在 SQLite Checkpoint 持久化模式开放')
    await wf._authenticated_user(authorization)
    # A current-process workflow must use the existing live approval endpoint.
    if thread in wf._sessions:
        raise HTTPException(409, '该任务仍在当前进程中，请使用原审批入口')
    # Java authorizes ownership BEFORE we read any stored checkpoint.
    session = await get_session(thread, authorization)
    claimed = await get_claim(thread, authorization)
    if claimed is not None:
        raise HTTPException(409, '恢复已经领取或结束；请只读核对原银行订单')
    snapshot = await wf.dynamic_graph.aget_state(wf._config(thread))
    state = snapshot.values or {}
    order = state.get('transferOrder') if isinstance(state, dict) else None
    if not isinstance(order, dict) or not order.get('orderId'):
        raise HTTPException(409, '原 Checkpoint 没有可验证的转账订单')
    try:
        remote = await bank.get_order(str(order['orderId']), authorization)
    except bank.BankError as exc:
        raise HTTPException(exc.status, '银行订单无法核实，不能继续恢复审批') from exc
    try:
        summary = verify_transfer_recovery(session, snapshot, remote, claimed)
    except RecoveryRefused as exc:
        raise HTTPException(409, str(exc)) from exc
    return snapshot, summary


@router.get('/{thread_id}/preview')
async def preview(thread_id: UUID, authorization: str | None = Header(default=None)):
    _snap, safe = await _preflight(str(thread_id), authorization)
    return safe


@router.post('/{thread_id}/otp/request')
async def request_recovered_otp(thread_id: UUID,
                                authorization: str | None = Header(default=None)):
    _snap, safe = await _preflight(str(thread_id), authorization)
    if not safe['requiresOtp']:
        raise HTTPException(409, '此订单不是 RED 风险，无需 OTP')
    try:
        result = await bank.request_transfer_otp(safe['orderId'], authorization)
    except bank.BankError as exc:
        raise HTTPException(exc.status, '银行 OTP 请求失败') from exc
    return {'threadId': str(thread_id), 'orderId': safe['orderId'],
            'status': 'OTP_REQUESTED', 'expiresInSeconds': result['expiresInSeconds']}


@router.post('/{thread_id}/resume')
async def resume_recovered_transfer(thread_id: UUID, body: ResumeRequest,
                                    authorization: str | None = Header(default=None)):
    thread = str(thread_id)
    # Single-worker lock helps with simultaneous browser clicks, but the Java
    # claim is the authoritative cross-process serialization boundary.
    lock = wf._locks.setdefault(thread, asyncio.Lock())
    async with lock:
        _snap, safe = await _preflight(thread, authorization)
        if (body.expectedCheckpointId != safe['checkpointId']
                or body.expectedOrderId != safe['orderId']
                or body.expectedAccountMasked != safe['accountMasked']):
            raise HTTPException(409, '预检快照发生变化，请重新查看原银行订单')
        try:
            amount_matches = Decimal(body.expectedAmount) == Decimal(safe['amount'])
        except (InvalidOperation, ValueError):
            amount_matches = False
        if not amount_matches:
            raise HTTPException(409, '用户确认的金额与银行订单不一致')
        if body.approved and safe['requiresOtp'] and body.otpCode is None:
            raise HTTPException(422, 'RED 风险恢复转账必须提供新的银行 OTP')
        if body.otpCode is not None and (not body.approved or not safe['requiresOtp']):
            raise HTTPException(422, '当前恢复动作不接受 OTP')

        # One durable approval/rejection attempt per original workflow. A 409 or
        # timeout here must NEVER lead to a Graph invocation or a new workflow.
        await create_claim(thread, safe['checkpointId'], body.approved,
                           str(uuid4()), authorization)
        try:
            result = await wf._invoke_graph(
                Command(resume=body.approved), wf._config(thread),
                context={'authorization': authorization,
                         'transferOtpCode': body.otpCode if body.approved else None},
            )
            if result.get('__interrupt__'):
                raise RuntimeError('Graph unexpectedly interrupted during recovery')
            target = 'COMPLETED' if body.approved else 'REJECTED'
            if result.get('status') != target:
                raise RuntimeError('Graph did not confirm the expected outcome')
            verified = await bank.get_order(safe['orderId'], authorization)
            # Recheck immutable fields and the FINAL bank order status.
            wf._read_bank_order_matches(result, verified)
            if verified.get('status') != ('SUCCESS' if body.approved else 'CANCELLED'):
                raise RuntimeError('Bank did not confirm the expected final order status')
            # This Java transaction finalizes both claim and D5 workflow lifecycle.
            await finalize_claim(thread, target, authorization)
            view = wf._view(thread, result)
            view.update({'recovered': True, 'bankOrderStatus': verified['status'],
                         'approvalPersisted': True, 'canResume': False})
            return view
        except BaseException as exc:
            # The bank may have committed. A best-effort NOT_CONFIRMED freezes
            # the claim. If this write also fails, CLAIMED remains non-replayable.
            try:
                await finalize_claim(thread, 'NOT_CONFIRMED', authorization)
            except Exception:
                pass
            if isinstance(exc, (KeyboardInterrupt, SystemExit, asyncio.CancelledError)):
                raise
            raise HTTPException(503,
                '原恢复操作结果未确认，可能已有银行副作用。请查询原订单及恢复记录；禁止重复审批或建单。') from exc
