"""Protocol-level in-memory tests (skip cleanly before MCP v2 install)."""
import pytest
mcp = pytest.importorskip('mcp')
from mcp import Client
from app.mcp.server import mcp as server

@pytest.fixture
def anyio_backend():
    return 'asyncio'

@pytest.mark.anyio
async def test_tool_discovery_has_no_writes():
    async with Client(server, raise_exceptions=True) as client:
        result = await client.list_tools()
        names = {x.name for x in result.tools}
        assert 'bank_get_balance' in names
        assert 'public_knowledge_search' in names
        assert 'bank_authorize_transfer' not in names
        assert 'bank_execute_transfer' not in names
        assert 'bank_cancel_subscription' not in names

@pytest.mark.anyio
async def test_in_memory_bank_tool_calls_existing_client(monkeypatch):
    from app.mcp import server as module
    async def fake_balance(auth):
        assert auth == 'Bearer test-only-token'
        return {'balance':'12.34','currency':'CNY'}
    monkeypatch.setenv('BANKPILOT_MCP_AUTHORIZATION', 'Bearer test-only-token')
    monkeypatch.setattr(module.bank, 'balance', fake_balance)
    async with Client(server, raise_exceptions=True) as client:
        result = await client.call_tool('bank_get_balance', {})
        assert result.is_error is False
        assert result.structured_content['data']['balance'] == '12.34'
