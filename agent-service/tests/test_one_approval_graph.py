"""Real LangGraph tests. Run in the local project venv with LangGraph installed."""
import asyncio
from datetime import date
from uuid import uuid4
import pytest
pytest.importorskip('langgraph')

from app import banking_client as bank
from app.graph import dynamic_cancellation_workflow as flow
from app.graph import dynamic_read_workflow as reads
from app.graph.task_planner import validate_plan

TOKEN = 'Bearer demo-test-token'


def test_two_writes_create_no_orders_or_reads(monkeypatch):
    calls = []
    async def fake_plan(message):
        return validate_plan({'tasks': [
            {'type': 'get_balance'},
            {'type': 'transfer_prepare', 'payee_name': '张三', 'amount': '1600'},
            {'type': 'cancel_subscription', 'target_name': '视频会员'},
        ]}, date(2026, 10, 28))
    async def forbidden(*args, **kwargs):
        calls.append('bank_called')
        raise AssertionError('Cannot access bank on rejected plan')
    monkeypatch.setattr(flow, 'plan_tasks', fake_plan)
    monkeypatch.setitem(reads.READ_EXECUTORS, 'balance', forbidden)
    monkeypatch.setattr(bank, 'prepare_transfer', forbidden)
    monkeypatch.setattr(bank, 'prepare_subscription_cancellation', forbidden)
    out = asyncio.run(flow.dynamic_graph.ainvoke(
        {'message': '查余额、取消视频会员并向张三转1600元'},
        {'configurable': {'thread_id': str(uuid4())}},
        context={'authorization': TOKEN}))
    assert out['status'] == 'NEEDS_CLARIFICATION'
    assert not calls
    assert not out.get('__interrupt__')


def test_read_only_two_tasks_parallel_then_end(monkeypatch):
    seen = []
    async def fake_plan(_):
        return validate_plan({'tasks': [
            {'type': 'get_balance'}, {'type': 'list_subscriptions'}]}, date(2026, 10, 28))
    async def balance(_):
        seen.append('balance'); await asyncio.sleep(0)
        return {'balance': '900.00'}
    async def subscriptions(_):
        seen.append('subscriptions'); await asyncio.sleep(0)
        return []
    monkeypatch.setattr(flow, 'plan_tasks', fake_plan)
    monkeypatch.setitem(reads.READ_EXECUTORS, 'balance', balance)
    monkeypatch.setitem(reads.READ_EXECUTORS, 'subscriptions', subscriptions)
    out = asyncio.run(flow.dynamic_graph.ainvoke(
        {'message': '余额和订阅'}, {'configurable': {'thread_id': str(uuid4())}},
        context={'authorization': TOKEN}))
    assert out['status'] == 'COMPLETED'
    assert set(out['results']) == {'get_balance', 'list_subscriptions'}
    assert set(seen) == {'balance', 'subscriptions'}
    assert not out.get('__interrupt__')
