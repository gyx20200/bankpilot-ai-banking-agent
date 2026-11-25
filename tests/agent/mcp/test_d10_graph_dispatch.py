import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.graph import dynamic_read_workflow as workflow


def test_mcp_mode_executes_read_task_via_protocol(monkeypatch):
    monkeypatch.setenv('BANKPILOT_MCP_READ_MODE', 'on')
    stub=AsyncMock(return_value={'balance':'12.34'})
    monkeypatch.setattr(workflow, 'execute_mcp_read', stub)
    result=asyncio.run(workflow.execute_read({'task':{'type':'get_balance'}},
                  SimpleNamespace(context={'authorization':'Bearer dummy-session'})))
    assert result['results']['get_balance']['status']=='SUCCESS'
    assert result['results']['get_balance']['data']['balance']=='12.34'
    stub.assert_awaited_once_with({'type':'get_balance'}, 'Bearer dummy-session')


def test_mcp_mode_refuses_to_dispatch_bank_write(monkeypatch):
    monkeypatch.setenv('BANKPILOT_MCP_READ_MODE', 'on')
    stub=AsyncMock()
    monkeypatch.setattr(workflow, 'execute_mcp_read', stub)
    try:
        asyncio.run(workflow.execute_read({'task':{'type':'transfer_prepare'}},
                  SimpleNamespace(context={'authorization':'Bearer dummy-session'})))
    except ValueError:
        pass
    else:
        raise AssertionError('write task must be rejected')
    stub.assert_not_called()
