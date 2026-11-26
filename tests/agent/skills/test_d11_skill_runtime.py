"""D11 unit tests using a stubbed D10 MCP read dispatcher; no network or money writes."""
from __future__ import annotations
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
import pytest
from app.skills import runtime
from app.skills.catalog import SkillError
from app.skills.runtime import SkillExecutionError
from app.mcp.policy import MCPReadError

MONTH='2026-10'


def fake_response(task):
    name=task['type']
    if name=='monthly_analytics':return {'source':'mysql','month':task['month'],'totalIncome':'8000.00','totalExpense':'60.00','netCashFlow':'7940.00'}
    if name=='transaction_anomalies':return {'source':'mysql','month':task['month'],'anomalyCount':2}
    if name=='get_balance':return {'balance':'100.00'}
    if name=='get_transactions':return [{'id':1,'direction':'OUT','amount':'10.00'}]
    if name=='list_subscriptions':return [{'id':5,'status':'ACTIVE'},{'id':6,'status':'CANCELLED'}]
    raise AssertionError('unauthorized tool called')


def test_monthly_skill_calls_only_approved_steps_in_order(monkeypatch):
    calls=[]
    async def mock(task,bearer):
        calls.append((task.copy(),bearer));return fake_response(task)
    monkeypatch.setattr(runtime,'execute_mcp_read',mock)
    monkeypatch.setenv('BANKPILOT_MCP_READ_MODE','on')
    result=asyncio.run(runtime.run_skill('skill_monthly_finance_review',{'month':MONTH},'Bearer USER_A'))
    assert result['status']=='COMPLETED' and result['readOnly'] is True
    assert [t['type'] for t,_ in calls]==['monthly_analytics','transaction_anomalies']
    assert all(bearer=='Bearer USER_A' for _,bearer in calls)
    assert '2 条规则提示' in result['summary']
    assert result['dataOrigin']=='JAVA_MYSQL_VIA_MCP'


def test_account_snapshot_uses_only_current_bearer(monkeypatch):
    calls=[]
    async def mock(task,bearer):calls.append((task['type'],bearer));return fake_response(task)
    monkeypatch.setattr(runtime,'execute_mcp_read',mock)
    monkeypatch.setenv('BANKPILOT_MCP_READ_MODE','on')
    result=asyncio.run(runtime.run_skill('skill_account_snapshot',{},'Bearer USER_B'))
    assert calls==[('get_balance','Bearer USER_B'),('get_transactions','Bearer USER_B')]
    assert '¥100.00' in result['summary']


def test_subscription_skill_never_mutates(monkeypatch):
    calls=[]
    async def mock(task,bearer):calls.append(task['type']);return fake_response(task)
    monkeypatch.setattr(runtime,'execute_mcp_read',mock)
    monkeypatch.setenv('BANKPILOT_MCP_READ_MODE','on')
    result=asyncio.run(runtime.run_skill('skill_subscription_review',{},'Bearer AUTH'))
    assert calls==['list_subscriptions','get_transactions']
    assert '未取消任何订阅' in result['summary']


@pytest.mark.parametrize('name,params',[('skill_monthly_finance_review',{}),('skill_monthly_finance_review',{'month':'2026-13'}),('skill_monthly_finance_review',{'month':MONTH,'otpCode':'123456'}),('skill_account_snapshot',{'month':MONTH}),('skill_transfer',{})])
def test_invalid_arguments_cannot_call_mcp(name,params,monkeypatch):
    async def forbidden(*args):raise AssertionError('MCP should not be called')
    monkeypatch.setattr(runtime,'execute_mcp_read',forbidden)
    monkeypatch.setenv('BANKPILOT_MCP_READ_MODE','on')
    with pytest.raises(SkillError):asyncio.run(runtime.run_skill(name,params,'Bearer AUTH'))


def test_future_month_rejected(monkeypatch):
    year=datetime.now(ZoneInfo('Asia/Shanghai')).year+1
    with pytest.raises(SkillError):runtime.validate_skill_input('skill_monthly_finance_review',{'month':f'{year}-01'})


def test_mcp_off_blocks_skill_without_fallback(monkeypatch):
    monkeypatch.setenv('BANKPILOT_MCP_READ_MODE','off')
    async def forbidden(*args):raise AssertionError('no fallback allowed')
    monkeypatch.setattr(runtime,'execute_mcp_read',forbidden)
    with pytest.raises(SkillError,match='require'):
        asyncio.run(runtime.run_skill('skill_account_snapshot',{},'Bearer AUTH'))


def test_missing_identity_rejected_before_mcp(monkeypatch):
    monkeypatch.setenv('BANKPILOT_MCP_READ_MODE','on')
    with pytest.raises(SkillError,match='authenticated'):
        asyncio.run(runtime.run_skill('skill_account_snapshot',{},''))


def test_partial_mcp_failure_cannot_claim_success(monkeypatch):
    calls=[]
    async def fails(task,bearer):
        calls.append(task['type'])
        if len(calls)==2:raise MCPReadError('internal: SECRET=1234')
        return fake_response(task)
    monkeypatch.setattr(runtime,'execute_mcp_read',fails)
    monkeypatch.setenv('BANKPILOT_MCP_READ_MODE','on')
    with pytest.raises(SkillExecutionError,match='no completed report') as e:
        asyncio.run(runtime.run_skill('skill_account_snapshot',{},'Bearer AUTH'))
    assert 'SECRET' not in str(e.value)


def test_bank_response_source_and_month_mismatch_rejected(monkeypatch):
    async def fake(task,bearer):
        v=fake_response(task)
        if task['type']=='monthly_analytics':v['month']='2025-10'
        return v
    monkeypatch.setenv('BANKPILOT_MCP_READ_MODE','on')
    monkeypatch.setattr(runtime,'execute_mcp_read',fake)
    with pytest.raises(SkillExecutionError,match='response invalid'):
        asyncio.run(runtime.run_skill('skill_monthly_finance_review',{'month':MONTH},'Bearer AUTH'))


def test_nan_amount_rejected():
    with pytest.raises(SkillError):
        runtime.validate_step_result('get_balance',{'balance':'NaN'}, {})
