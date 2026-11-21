"""D6 pure recovery preflight tests; no network, LLM, bank write, or LangGraph dependency."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'agent-service'))
from app.d6_recovery_policy import RecoveryRefused, verify_transfer_recovery


def example(*, risk='YELLOW'):
    order_id = str(uuid4())
    session = SimpleNamespace(status='WAITING', expired=False,
                              threadId=uuid4(), conversationId=uuid4(),
                              sourceRequestId='request-12345678',
                              expiresAt=datetime.now(timezone.utc)+timedelta(minutes=15))
    order = {'orderId': order_id, 'payeeName': '李四', 'accountMasked': '****17A4',
             'amount': '10.00', 'remark': 'D6测试', 'riskLevel': risk,
             'status': 'PENDING_APPROVAL'}
    state = {
        'transferOrder': dict(order),
        'transferCandidate': {'payeeName': '李四', 'accountMasked': '****17A4',
                              'amount': '10.00', 'remark': 'D6测试'},
        'transferAuthorizeRequestId': 'authorize-123456789',
        'transferExecuteRequestId': 'execute-123456789',
        'transferCancelRequestId': 'cancel-123456789',
    }
    snapshot = SimpleNamespace(values=state, next=('wait_for_transfer_approval',),
                               tasks=(SimpleNamespace(interrupts=('APPROVAL',)),),
                               config={'configurable': {'checkpoint_id': str(uuid4())}})
    return session, snapshot, order


def test_valid_yellow_transfer_can_recover():
    args = example()
    result = verify_transfer_recovery(*args)
    assert result['canResume'] is True
    assert result['requiresOtp'] is False
    assert result['orderId'] == args[2]['orderId']


def test_valid_red_transfer_requires_fresh_otp():
    result = verify_transfer_recovery(*example(risk='RED'))
    assert result['requiresOtp'] is True


@pytest.mark.parametrize('changed', [
    {'status': 'AUTHORIZED'}, {'status': 'SUCCESS'}, {'amount': '11.00'},
    {'payeeName': '其他人'}, {'accountMasked': '****9999'}, {'riskLevel': 'RED'},
    {'remark': '篡改'}
])
def test_order_mismatch_or_no_longer_pending_is_denied(changed):
    session, snapshot, remote = example()
    remote.update(changed)
    with pytest.raises(RecoveryRefused):
        verify_transfer_recovery(session, snapshot, remote)


def test_claim_existing_blocks_replay():
    with pytest.raises(RecoveryRefused):
        verify_transfer_recovery(*example(), {'status': 'CLAIMED'})


def test_not_exact_interrupt_blocks_resume():
    session, snap, order = example()
    snap.next = ('transfer_execute',)
    with pytest.raises(RecoveryRefused):
        verify_transfer_recovery(session, snap, order)


def test_missing_interrupt_metadata_blocks_resume():
    session, snap, order = example()
    snap.tasks = ()
    with pytest.raises(RecoveryRefused):
        verify_transfer_recovery(session, snap, order)


def test_prior_decision_blocks_resume():
    session, snap, order = example()
    snap.values['transferDecision'] = True
    with pytest.raises(RecoveryRefused):
        verify_transfer_recovery(session, snap, order)


def test_missing_stable_idempotency_key_blocks_resume():
    session, snap, order = example()
    del snap.values['transferExecuteRequestId']
    with pytest.raises(RecoveryRefused):
        verify_transfer_recovery(session, snap, order)


@pytest.mark.parametrize('mutate', [
    lambda s: setattr(s, 'expired', True),
    lambda s: setattr(s, 'status', 'COMPLETED'),
    lambda s: setattr(s, 'sourceRequestId', None),
])
def test_invalid_session_blocks_recovery(mutate):
    session, snap, order = example()
    mutate(session)
    with pytest.raises(RecoveryRefused):
        verify_transfer_recovery(session, snap, order)
