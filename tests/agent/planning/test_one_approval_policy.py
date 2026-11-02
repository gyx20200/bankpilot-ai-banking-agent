"""Day 6 product rule: any number of reads, zero or one approval business."""
from datetime import date
import pytest
from app.graph.task_planner import validate_plan

NOW = date(2026, 10, 28)


@pytest.mark.parametrize('tasks', [
    [{'type': 'get_balance'}],
    [{'type': 'get_balance'}, {'type': 'list_subscriptions'}],
    [{'type': 'get_balance'}, {'type': 'monthly_analytics', 'month': '2026-09'},
     {'type': 'get_transactions'}, {'type': 'get_payees'}],
    [{'type': 'get_balance'}, {'type': 'transfer_prepare', 'payee_name': '张三', 'amount': '1600'}],
    [{'type': 'get_balance'}, {'type': 'cancel_subscription', 'target_name': '视频会员'}],
])
def test_reads_and_at_most_one_write(tasks):
    plan = validate_plan({'tasks': tasks}, NOW)
    assert plan.status == 'ready'
    if any(t.type == 'transfer_prepare' for t in plan.tasks):
        assert plan.execution_order.index('get_payees') < plan.execution_order.index('transfer_prepare')
    if any(t.type == 'cancel_subscription' for t in plan.tasks):
        assert plan.execution_order.index('list_subscriptions') < plan.execution_order.index('cancel_subscription')


def test_mixed_sensitive_tasks_are_rejected_without_execution_plan():
    task_plan = validate_plan({'tasks': [
        {'type': 'get_balance'},
        {'type': 'transfer_prepare', 'payee_name': '张三', 'amount': '1600'},
        {'type': 'cancel_subscription', 'target_name': '视频会员'}
    ]}, NOW)
    assert task_plan.status == 'needs_clarification'
    assert task_plan.execution_order == []
    assert '拆' in task_plan.clarification


def test_missing_transfer_amount_still_clarifies():
    task_plan = validate_plan({'tasks': [
        {'type': 'get_balance'},
        {'type': 'transfer_prepare', 'payee_name': '张三'},
    ]}, NOW)
    assert task_plan.status == 'needs_clarification'
    assert task_plan.execution_order == []
