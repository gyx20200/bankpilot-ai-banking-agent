"""Stage 4D: fake-bank graph tests; no HTTP or real bank writes."""
import asyncio
from datetime import date
from uuid import uuid4

import pytest
from langgraph.types import Command

from app import banking_client as bank
from app.graph import dynamic_read_workflow as reads
from app.graph import dynamic_cancellation_workflow as flow
from app.graph.task_planner import validate_plan

TOKEN = 'Bearer mock-day4-token'


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def scenario(monkeypatch):
    events = []
    order = {'orderId': 'MOCK-SC-1001', 'subscriptionId': 1,
             'status': 'PENDING_APPROVAL', 'subscriptionStatus': 'ACTIVE'}
    subscriptions = [{'id': 1, 'merchantName': '视频会员', 'status': 'ACTIVE',
                      'amount': '25.00', 'billingCycle': 'MONTHLY'}]

    async def fake_plan(message):
        return validate_plan({'tasks': [
            {'type': 'monthly_analytics', 'month': '2026-10'},
            {'type': 'cancel_subscription', 'target_name': '视频会员'},
        ]}, date(2026, 10, 28), message)

    async def fake_month(month, bearer):
        assert bearer == TOKEN
        events.append('monthly_analytics')
        return {'month': month, 'totalIncome': '8000.00', 'totalExpense': '25.00',
                'netCashFlow': '7975.00', 'currency': 'CNY', 'categories': []}

    async def fake_subs(bearer):
        assert bearer == TOKEN
        events.append('list_subscriptions')
        return subscriptions

    async def fake_prepare(sid, bearer, request_id):
        assert sid == 1 and bearer == TOKEN and len(request_id) == 32
        events.append(('prepare', request_id))
        return dict(order)

    async def fake_authorize(oid, bearer, request_id, confirmed):
        assert oid == order['orderId'] and bearer == TOKEN
        assert confirmed is True and len(request_id) == 32
        events.append(('authorize', request_id))
        assert order['status'] == 'PENDING_APPROVAL'
        order['status'] = 'AUTHORIZED'
        return dict(order)

    async def fake_execute(oid, bearer, request_id):
        assert oid == order['orderId'] and bearer == TOKEN
        assert len(request_id) == 32
        events.append(('execute', request_id))
        assert order['status'] == 'AUTHORIZED'
        order['status'] = 'SUCCESS'
        order['subscriptionStatus'] = 'CANCELLED'
        return dict(order)

    async def fake_reject(oid, bearer, request_id):
        assert oid == order['orderId'] and bearer == TOKEN
        assert len(request_id) == 32
        events.append(('reject', request_id))
        assert order['status'] == 'PENDING_APPROVAL'
        order['status'] = 'REJECTED'
        return dict(order)

    async def fake_get(oid, bearer):
        assert oid == order['orderId'] and bearer == TOKEN
        events.append('get')
        return dict(order)

    monkeypatch.setattr(flow, 'plan_tasks', fake_plan)
    monkeypatch.setattr(bank, 'get_monthly_analytics', fake_month)
    monkeypatch.setitem(reads.READ_EXECUTORS, 'subscriptions', fake_subs)
    monkeypatch.setattr(bank, 'prepare_subscription_cancellation', fake_prepare)
    monkeypatch.setattr(bank, 'authorize_subscription_cancellation', fake_authorize)
    monkeypatch.setattr(bank, 'execute_subscription_cancellation', fake_execute)
    monkeypatch.setattr(bank, 'reject_subscription_cancellation', fake_reject)
    monkeypatch.setattr(bank, 'get_subscription_cancellation', fake_get)
    return events, order


def start():
    config = {'configurable': {'thread_id': str(uuid4())}}
    result = run(flow.dynamic_graph.ainvoke(
        {'message': '分析2026年10月收支并取消视频会员代扣'},
        config, context={'authorization': TOKEN}))
    assert result.get('__interrupt__')
    assert result['status'] == 'PENDING_APPROVAL'
    assert result['cancellationOrder']['subscriptionStatus'] == 'ACTIVE'
    return config


def resume(config, approved):
    return run(flow.dynamic_graph.ainvoke(
        Command(resume=approved), config, context={'authorization': TOKEN}))


def test_approve_only_after_resume(scenario):
    events, order = scenario
    config = start()
    assert not any(isinstance(e, tuple) and e[0] in ('authorize', 'execute', 'reject') for e in events)
    checkpoint = flow.dynamic_graph.get_state(config).values
    assert checkpoint['authorizeRequestId'] and checkpoint['executeRequestId']
    result = resume(config, True)
    assert result['status'] == 'COMPLETED'
    assert result['cancellationOrder']['status'] == 'SUCCESS'
    assert result['cancellationOrder']['subscriptionStatus'] == 'CANCELLED'
    names = [e[0] for e in events if isinstance(e, tuple)]
    assert names == ['prepare', 'authorize', 'execute']
    assert 'get' in events
    assert not result.get('__interrupt__')


def test_reject_closes_order_without_execution(scenario):
    events, order = scenario
    config = start()
    result = resume(config, False)
    assert result['status'] == 'REJECTED'
    assert result['cancellationOrder']['status'] == 'REJECTED'
    assert result['cancellationOrder']['subscriptionStatus'] == 'ACTIVE'
    names = [e[0] for e in events if isinstance(e, tuple)]
    assert names == ['prepare', 'reject']
    assert events.count('get') == 1


def test_execution_error_does_not_claim_success(monkeypatch, scenario):
    events, order = scenario
    config = start()
    saved_keys = flow.dynamic_graph.get_state(config).values

    async def bad_execute(*args):
        events.append('execute_failed')
        raise bank.BankError('银行接口超时，请查询订单状态。', 502)

    monkeypatch.setattr(bank, 'execute_subscription_cancellation', bad_execute)
    with pytest.raises(bank.BankError):
        resume(config, True)
    assert order['subscriptionStatus'] == 'ACTIVE'
    snap = flow.dynamic_graph.get_state(config)
    assert 'execute' in snap.next
    assert snap.values['executeRequestId'] == saved_keys['executeRequestId']


def test_retry_after_timeout_uses_saved_execute_key(monkeypatch, scenario):
    events, order = scenario
    config = start()
    keys = flow.dynamic_graph.get_state(config).values

    async def lost_execute(oid, bearer, request_id):
        assert request_id == keys['executeRequestId']
        order['status'] = 'SUCCESS'
        order['subscriptionStatus'] = 'CANCELLED'
        raise bank.BankError('响应丢失', 502)

    monkeypatch.setattr(bank, 'execute_subscription_cancellation', lost_execute)
    result = resume(config, True)
    assert result['status'] == 'COMPLETED'
    assert result['cancellationOrder']['status'] == 'SUCCESS'
    assert events.count('get') >= 2
