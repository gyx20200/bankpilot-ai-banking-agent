"""Stage 4E-1: transfer graph only prepares orders, never authorizes/executes."""
import asyncio
from datetime import date
from uuid import uuid4

import pytest

from app import banking_client as bank
from app.graph import dynamic_read_workflow as reads
from app.graph import dynamic_cancellation_workflow as flow
from app.graph.task_planner import validate_plan

TOKEN = 'Bearer mock-day4-token'


def run(message):
    config = {'configurable': {'thread_id': str(uuid4())}}
    result = asyncio.run(flow.dynamic_graph.ainvoke(
        {'message': message}, config, context={'authorization': TOKEN}))
    return result, config


def setup(monkeypatch, tasks, payees=None):
    events = []

    async def fake_plan(message):
        return validate_plan({'tasks': tasks}, date(2026, 10, 28), message)

    async def fake_payees(token):
        assert token == TOKEN
        events.append('get_payees')
        return payees if payees is not None else [
            {'id': 1, 'payeeName': '李四', 'payeeAccountMasked': '****5291'},
            {'id': 2, 'payeeName': '王五', 'payeeAccountMasked': '****8806'},
        ]

    async def fake_month(month, token):
        assert token == TOKEN
        events.append('monthly_analytics')
        return {'month': month, 'currency': 'CNY', 'totalIncome': '0.00',
                'totalExpense': '0.00', 'netCashFlow': '0.00', 'categories': []}

    async def fake_prepare(payee_id, amount, rid, token):
        assert (payee_id, amount, token) == (1, '200.00', TOKEN)
        assert len(rid) == 32
        events.append(('prepare_transfer', rid))
        return {'orderId': 'MOCK-1001', 'payeeName': '李四',
                'accountMasked': '****5291', 'amount': '200.00',
                'riskLevel': 'YELLOW', 'status': 'PENDING_APPROVAL'}

    async def not_allowed(*args, **kwargs):
        raise AssertionError('prepare stage must not authorize/execute')

    monkeypatch.setattr(flow, 'plan_tasks', fake_plan)
    monkeypatch.setitem(reads.READ_EXECUTORS, 'payees', fake_payees)
    monkeypatch.setattr(bank, 'get_monthly_analytics', fake_month)
    monkeypatch.setattr(bank, 'prepare_transfer', fake_prepare)
    monkeypatch.setattr(bank, 'authorize_transfer', not_allowed)
    monkeypatch.setattr(bank, 'execute_transfer', not_allowed)
    monkeypatch.setattr(bank, 'prepare_subscription_cancellation', not_allowed)
    return events


@pytest.mark.parametrize('tasks', [
    [{'type': 'transfer_prepare', 'payee_name': '李四', 'amount': '200'}],
    [{'type': 'monthly_analytics', 'month': '2026-10'},
     {'type': 'transfer_prepare', 'payee_name': '李四', 'amount': '200'}],
])
def test_transfer_combinations_prepare_and_pause(monkeypatch, tasks):
    events = setup(monkeypatch, tasks)

    message = (
        '分析2026年10月收支，再给李四转200元'
        if any(
            task['type'] == 'monthly_analytics'
            for task in tasks
        )
        else '给李四转200元'
    )

    result, config = run(message)

    assert result.get('__interrupt__')
    assert result['status'] == 'TRANSFER_PENDING_APPROVAL'
    assert result['transferOrder']['status'] == 'PENDING_APPROVAL'
    assert result['transferCandidate']['id'] == 1
    assert events.count('get_payees') == 1
    assert len([e for e in events if isinstance(e, tuple)]) == 1
    snapshot = flow.dynamic_graph.get_state(config)
    assert snapshot.values['transferRequestId'] == result['transferRequestId']
    assert snapshot.values['transferOrder']['orderId'] == 'MOCK-1001'
    assert 'wait_for_transfer_approval' in snapshot.next


@pytest.mark.parametrize('payees,status', [
    ([], 'PAYEE_NOT_FOUND'),
    ([{'id': 1, 'payeeName': '李四'}, {'id': 2, 'payeeName': '李四'}], 'PAYEE_AMBIGUOUS'),
    ([{'id': '1', 'payeeName': '李四'}], 'PAYEE_INVALID'),
])
def test_invalid_payee_cannot_create_order(monkeypatch, payees, status):
    events = setup(monkeypatch, [
        {'type': 'transfer_prepare', 'payee_name': '李四', 'amount': '200'}], payees)
    result, _ = run('给李四转200元')
    assert result['status'] == status
    assert not result.get('__interrupt__')
    assert 'get_payees' in events
    assert not any(isinstance(e, tuple) for e in events)


def test_two_approval_tasks_rejected_before_any_bank_operation(monkeypatch):
    """The planner rejects transfer + cancellation before any read or write."""
    events = setup(monkeypatch, [
        {'type': 'transfer_prepare', 'payee_name': '李四', 'amount': '200'},
        {'type': 'cancel_subscription', 'target_name': '视频会员'}])

    async def forbidden_subscription_lookup(auth):
        raise AssertionError('Two-approval plan must be rejected before subscription lookup')

    monkeypatch.setitem(reads.READ_EXECUTORS, 'subscriptions', forbidden_subscription_lookup)
    result, _ = run('给李四转200元并取消视频会员代扣')
    assert result['status'] == 'NEEDS_CLARIFICATION'
    assert events == []
    assert not result.get('__interrupt__')
