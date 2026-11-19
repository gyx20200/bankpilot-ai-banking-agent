"""Contract, planning, banking-client and Graph-node tests for D4 new tools.
No live Java, DeepSeek, MySQL or credentials needed.
"""
import asyncio
from datetime import date
from types import SimpleNamespace

import pytest

from app import banking_client as bank
from app.analytics_contract import (
    AnalyticsContractError, explicit_annual_year,
    validate_annual_report, validate_anomaly_report,
)
from app.assistant_history import assistant_reply_text
from app.graph.task_registry import TASK_REGISTRY, resolve_execution_order
from app.graph.task_planner import validate_plan
from app.graph.dynamic_read_workflow import READ_TASK_TYPES, execute_read

TODAY = date(2026, 11, 19)
TOKEN = 'Bearer fake-test-token'


def annual():
    return dict(year='2026', currency='CNY', totalIncome=8800.0,
                totalExpense=218.0, netCashFlow=8582.0,
                categories=[dict(name='餐饮', amount=218.0, count=1)],
                monthlyBreakdown=[dict(month=f'2026-{m:02d}',
                    totalIncome=8800.0 if m == 9 else 0,
                    totalExpense=218.0 if m == 9 else 0) for m in range(1, 12)],
                periodType='YEAR_TO_DATE', source='mysql',
                periodStart='2026-01-01T00:00', periodEndExclusive='2026-11-19T09:00')


def anomalies():
    return dict(month='2026-10', currency='CNY', scannedCount=2, anomalyCount=1,
                items=[dict(transactionId=2, ruleCode='POSSIBLE_DUPLICATE',
                            amount=25.0, category='订阅', merchantName='测试商户',
                            occurredAt='2026-10-08T08:10', relatedTransactionId=1,
                            reason='同组支出在10分钟内，建议核实')],
                largeOutflowThreshold=1000.0, duplicateWindowMinutes=10,
                source='mysql', periodStart='2026-10-01T00:00',
                periodEndExclusive='2026-11-01T00:00')


def plan(task, message, **extra):
    return validate_plan({'tasks': [task]}, today=TODAY, message=message, **extra)


def test_registry_preserves_writes_and_adds_read_tools():
    for name in ('annual_analytics', 'transaction_anomalies'):
        assert TASK_REGISTRY[name].risk_level == 'LOW'
        assert name in READ_TASK_TYPES
    assert TASK_REGISTRY['transfer_prepare'].risk_level == 'HIGH'
    assert 'transfer_prepare' not in READ_TASK_TYPES
    assert resolve_execution_order(['transfer_prepare']) == ['get_payees', 'transfer_prepare']


@pytest.mark.parametrize('message,expected', [
    ('分析2026年度收支', '2026'),
    ('分析2026年收支，并检查2026年10月的异常交易', '2026'),
    ('分析2026年10月收支', None),
    ('分析2025年和2026年年度收支', None),
])
def test_explicit_annual_period(message, expected):
    assert explicit_annual_year(message) == expected


def test_annual_and_anomaly_composite_plan():
    p = validate_plan({'tasks': [
        {'type': 'annual_analytics', 'year': '2026'},
        {'type': 'transaction_anomalies', 'month': '2026-10'}]},
        today=TODAY, message='分析2026年度收支，并检查2026年10月的异常交易')
    assert p.status == 'ready'
    assert set(p.execution_order) == {'annual_analytics', 'transaction_anomalies'}


@pytest.mark.parametrize('task,message', [
    ({'type': 'annual_analytics', 'year': '2026'}, '分析2026年10月收支'),
    ({'type': 'annual_analytics', 'year': '2025'}, '分析2026年度收支'),
    ({'type': 'annual_analytics', 'year': '2027'}, '分析2027年度收支'),
    ({'type': 'annual_analytics', 'year': '0999'}, '分析0999年度收支'),
    ({'type': 'transaction_anomalies', 'month': '2026-10'}, '那10月呢？'),
    ({'type': 'transaction_anomalies', 'month': '2026-12'}, '检查2026年12月异常交易'),
    ({'type': 'transaction_anomalies', 'month': '2026-09'}, '检查2026年10月异常交易'),
])
def test_invalid_or_inherited_period_needs_clarification(task, message):
    p = plan(task, message, contextual_month='2026-10')
    assert p.status == 'needs_clarification'


def test_monthly_context_still_works():
    p = plan({'type': 'monthly_analytics', 'month': '2026-10'},
             '那10月呢？', contextual_month='2026-10')
    assert p.status == 'ready'


def test_annual_contract_valid_and_rejects_malformed():
    assert validate_annual_report(annual(), '2026')['totalIncome'] == 8800
    for key, value in [('year', '2025'), ('totalIncome', True),
                       ('source', 'mock'), ('monthlyBreakdown', [])]:
        bad = annual()
        bad[key] = value
        with pytest.raises(AnalyticsContractError):
            validate_annual_report(bad, '2026')


def test_anomaly_contract_valid_and_rejects_malformed():
    assert validate_anomaly_report(anomalies(), '2026-10')['anomalyCount'] == 1
    for key, value in [('month', '2026-09'), ('anomalyCount', 2),
                       ('scannedCount', 10001), ('duplicateWindowMinutes', 11)]:
        bad = anomalies()
        bad[key] = value
        with pytest.raises(AnalyticsContractError):
            validate_anomaly_report(bad, '2026-10')
    bad = anomalies()
    bad['items'][0]['relatedTransactionId'] = None
    with pytest.raises(AnalyticsContractError):
        validate_anomaly_report(bad, '2026-10')


def test_read_executor_and_banking_client(monkeypatch):
    calls = []
    async def fake_request(method, url, bearer):
        calls.append((method, url, bearer))
        return annual() if '/annual?' in url else anomalies()
    monkeypatch.setattr(bank, '_request', fake_request)
    runtime = SimpleNamespace(context={'authorization': TOKEN})
    async def run():
        a = await execute_read({'task': {'type': 'annual_analytics', 'year': '2026'}}, runtime)
        b = await execute_read({'task': {'type': 'transaction_anomalies', 'month': '2026-10'}}, runtime)
        return {**a['results'], **b['results']}
    result = asyncio.run(run())
    assert calls == [('GET', f'{bank.READ_URL}/analytics/annual?year=2026', TOKEN),
                     ('GET', f'{bank.READ_URL}/analytics/anomalies?month=2026-10', TOKEN)]
    reply = assistant_reply_text({'status': 'COMPLETED', 'results': result})
    assert '年度累计' in reply and '8,800.00' in reply
    assert '1条待核实规则事件' in reply and '不代表确认盗刷' in reply


def test_invalid_response_is_not_success(monkeypatch):
    async def fake_request(*args):
        return {'year': '2026', 'source': 'mysql'}
    monkeypatch.setattr(bank, '_request', fake_request)
    with pytest.raises(bank.BankError):
        asyncio.run(bank.get_annual_analytics('2026', TOKEN))


def test_missing_token_and_invalid_period_do_not_call_bank(monkeypatch):
    async def unexpected(*args):
        raise AssertionError('should not call bank')
    monkeypatch.setattr(bank, '_request', unexpected)
    with pytest.raises(bank.BankError) as e:
        asyncio.run(bank.get_annual_analytics('2026', None))
    assert e.value.status == 401
    with pytest.raises(bank.BankError) as e:
        asyncio.run(bank.get_transaction_anomalies('2026-13', TOKEN))
    assert e.value.status == 400


def test_main_graph_composite_reads(monkeypatch):
    from uuid import uuid4
    from app.graph import dynamic_cancellation_workflow as workflow
    calls = []
    async def fake_plan(message):
        return validate_plan({'tasks': [
            {'type': 'annual_analytics', 'year': '2026'},
            {'type': 'transaction_anomalies', 'month': '2026-10'},
        ]}, today=TODAY, message=message)
    async def fake_annual(year, bearer):
        assert year == '2026' and bearer == TOKEN
        calls.append('annual_analytics')
        return annual()
    async def fake_anomaly(month, bearer):
        assert month == '2026-10' and bearer == TOKEN
        calls.append('transaction_anomalies')
        return anomalies()
    monkeypatch.setattr(workflow, 'plan_tasks', fake_plan)
    monkeypatch.setattr(bank, 'get_annual_analytics', fake_annual)
    monkeypatch.setattr(bank, 'get_transaction_anomalies', fake_anomaly)
    result = asyncio.run(workflow.dynamic_graph.ainvoke(
        {'message': '分析2026年度收支，并检查2026年10月的异常交易'},
        {'configurable': {'thread_id': str(uuid4())}},
        context={'authorization': TOKEN},
    ))
    assert result['status'] == 'COMPLETED'
    assert set(calls) == set(result['results']) == {'annual_analytics', 'transaction_anomalies'}
