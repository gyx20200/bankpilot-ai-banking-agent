import os
import pytest
from app.mcp.policy import ALLOWED, MCPReadError, tool_for_task
from app.mcp.dispatch import child_env


def test_only_low_risk_read_tasks_are_available():
    from app.graph.task_registry import TASK_REGISTRY
    assert ALLOWED
    assert all(TASK_REGISTRY[key].risk_level == 'LOW' for key in ALLOWED)
    assert not any('transfer' in name or 'authorize' in name or 'execute' in name or 'cancel' in name
                   for name, _ in ALLOWED.values())


@pytest.mark.parametrize('task', [
    {'type': 'transfer_prepare', 'amount': '10'},
    {'type': 'schedule_transfer'},
    {'type': 'cancel_subscription'},
    {'type': 'bank_transfer_execute'},
    {'type': 'monthly_analytics', 'month': '2026-13'},
    {'type': 'monthly_analytics', 'month': '2026-10', 'amount': '100'},
    {'type': 'knowledge_search', 'query': '查询我的余额'},
])
def test_refuses_sensitive_or_invalid_mcp_tool(task):
    with pytest.raises(MCPReadError):
        tool_for_task(task)


def test_read_tools_have_fixed_inputs():
    assert tool_for_task({'type': 'get_balance'}) == ('bank_get_balance', {})
    assert tool_for_task({'type': 'monthly_analytics', 'month': '2026-10'}) == (
        'bank_monthly_analytics', {'month': '2026-10'})


def test_token_is_not_an_mcp_tool_argument(monkeypatch):
    monkeypatch.setenv('BANK_API_MODE', 'java')
    token = 'Bearer test_mcp_session_token_12345678'
    result = child_env(token)
    assert result['BANKPILOT_MCP_AUTHORIZATION'] == token
    assert 'BANKPILOT_MCP_AUTHORIZATION' not in tool_for_task({'type':'get_balance'})[1]
    assert 'BANKPILOT_TEST_BEARER' not in result


def test_requires_current_bearer(monkeypatch):
    monkeypatch.setenv('BANK_API_MODE', 'java')
    with pytest.raises(MCPReadError):
        child_env('')
