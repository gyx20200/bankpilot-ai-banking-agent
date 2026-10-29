"""Stage 4C regression: dynamic reads + prepare + interrupt, no authorize/execute."""
import asyncio
from datetime import date
from uuid import uuid4

import pytest

from app import banking_client as bank
from app.graph import dynamic_read_workflow as reads
from app.graph import dynamic_cancellation_workflow as flow
from app.graph.task_planner import validate_plan

TOKEN = 'Bearer local-demo-user'


def setup(monkeypatch, tasks, subscriptions=None):
    async def fake_plan(message):
        return validate_plan({'tasks': tasks}, date(2026, 10, 28), message)
    monkeypatch.setattr(flow, 'plan_tasks', fake_plan)
    events = []

    async def fake_monthly(month, auth):
        events.append('monthly_analytics')
        assert auth == TOKEN
        return {'month': month, 'totalIncome': '0.00', 'totalExpense': '25.00',
                'netCashFlow': '-25.00', 'categories': [], 'currency': 'CNY'}

    async def fake_subscriptions(auth):
        events.append('list_subscriptions')
        assert auth == TOKEN
        return subscriptions if subscriptions is not None else [
            {'id': 1, 'merchantName': '视频会员', 'amount': '25.00',
             'billingCycle': 'MONTHLY', 'status': 'ACTIVE'},
        ]

    async def fake_prepare(sid, auth, request_id):
        events.append('prepare')
        assert sid == 1 and auth == TOKEN and len(request_id) == 32
        return {'orderId': 'MOCK-SC-1001', 'subscriptionId': sid,
                'status': 'PENDING_APPROVAL', 'subscriptionStatus': 'ACTIVE'}

    async def must_not_run(*args, **kwargs):
        raise AssertionError('4C must not authorize or execute cancellation')

    monkeypatch.setattr(bank, 'get_monthly_analytics', fake_monthly)
    monkeypatch.setitem(reads.READ_EXECUTORS, 'subscriptions', fake_subscriptions)
    monkeypatch.setattr(bank, 'prepare_subscription_cancellation', fake_prepare)
    monkeypatch.setattr(bank, 'authorize_subscription_cancellation', must_not_run)
    monkeypatch.setattr(bank, 'execute_subscription_cancellation', must_not_run)
    return events


def run(message):
    tid = str(uuid4())
    config = {'configurable': {'thread_id': tid}}
    result = asyncio.run(flow.dynamic_graph.ainvoke(
        {'message': message}, config, context={'authorization': TOKEN}))
    return result, config


def test_readonly_combination_finishes_without_prepare(monkeypatch):
    events = setup(monkeypatch, [
        {'type': 'monthly_analytics', 'month': '2026-09'},
        {'type': 'list_subscriptions'}])
    result, _ = run('分析2026年9月收支并查询订阅')
    assert result['status'] == 'COMPLETED'
    assert set(result['results']) == {'monthly_analytics', 'list_subscriptions'}
    assert set(events) == {'monthly_analytics', 'list_subscriptions'}
    assert not result.get('__interrupt__')


@pytest.mark.parametrize('tasks,message', [
    ([{'type': 'cancel_subscription', 'target_name': '视频会员'}], '取消视频会员代扣'),
    ([{'type': 'monthly_analytics', 'month': '2026-09'},
      {'type': 'cancel_subscription', 'target_name': '视频会员'}],
     '分析2026年9月收支并取消视频会员代扣'),
    ([{'type': 'list_subscriptions'},
      {'type': 'cancel_subscription', 'target_name': '视频会员'}],
     '查询订阅并取消视频会员代扣'),
    ([{'type': 'monthly_analytics', 'month': '2026-09'},
      {'type': 'list_subscriptions'},
      {'type': 'cancel_subscription', 'target_name': '视频会员'}],
     '分析2026年9月收支、查询订阅并取消视频会员代扣'),
])
def test_cancel_combinations_pause_before_authorization(monkeypatch, tasks, message):
    events = setup(monkeypatch, tasks)
    result, config = run(message)
    assert result.get('__interrupt__')
    assert result['status'] == 'PENDING_APPROVAL'
    assert result['candidate']['id'] == 1
    assert result['cancellationOrder']['orderId'] == 'MOCK-SC-1001'
    assert result['cancellationOrder']['status'] == 'PENDING_APPROVAL'
    assert events.count('prepare') == 1
    assert events.count('list_subscriptions') == 1
    assert result['prepareRequestId']
    # The stable key and order are checkpointed before the approval interrupt.
    snapshot = flow.dynamic_graph.get_state(config)
    assert snapshot.values['prepareRequestId'] == result['prepareRequestId']
    assert snapshot.values['cancellationOrder']['orderId'] == 'MOCK-SC-1001'


@pytest.mark.parametrize('subscriptions,status', [
    ([], 'TARGET_NOT_FOUND'),
    ([{'id': 1, 'merchantName': '视频会员', 'status': 'CANCELLED'}], 'TARGET_NOT_FOUND'),
    ([{'id': 1, 'merchantName': '视频会员', 'status': 'ACTIVE'},
      {'id': 2, 'merchantName': '视频会员', 'status': 'ACTIVE'}], 'TARGET_AMBIGUOUS'),
])
def test_missing_or_ambiguous_cancel_target_does_not_prepare(monkeypatch, subscriptions, status):
    events = setup(monkeypatch, [{'type': 'cancel_subscription', 'target_name': '视频会员'}], subscriptions)
    result, _ = run('取消视频会员代扣')
    assert result['status'] == status
    assert 'prepare' not in events
    assert not result.get('__interrupt__')


def test_transfer_plus_monthly_now_prepares_but_does_not_execute(monkeypatch):
    events = setup(monkeypatch, [
        {'type': 'monthly_analytics', 'month': '2026-09'},
        {'type': 'transfer_prepare', 'payee_name': '李四', 'amount': '200'}])

    async def fake_payees(token):
        events.append('get_payees')
        return [{'id': 1, 'payeeName': '李四', 'payeeAccountMasked': '****5291'}]

    async def fake_transfer(payee_id, amount, request_id, token):
        assert (payee_id, amount, token) == (1, '200.00', TOKEN)
        events.append('prepare_transfer')
        return {'orderId': 'MOCK-1001', 'status': 'PENDING_APPROVAL',
                'riskLevel': 'YELLOW', 'amount': amount, 'payeeName': '李四',
                'accountMasked': '****5291'}

    monkeypatch.setitem(reads.READ_EXECUTORS, 'payees', fake_payees)
    monkeypatch.setattr(bank, 'prepare_transfer', fake_transfer)
    result, _ = run('分析2026年9月收支，再给李四转200元')
    assert result['status'] == 'TRANSFER_PENDING_APPROVAL'
    assert result['transferOrder']['orderId'] == 'MOCK-1001'
    assert result.get('__interrupt__')
    assert set(events) == {'monthly_analytics', 'get_payees', 'prepare_transfer'}


def test_missing_month_asks_clarification_without_calls(monkeypatch):
    events = setup(monkeypatch, [{'type': 'monthly_analytics'}])
    result, _ = run('分析收支')
    assert result['status'] == 'NEEDS_CLARIFICATION'
    assert events == []
