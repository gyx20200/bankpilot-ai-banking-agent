"""Use current shell BANKPILOT_TEST_BEARER (never a CLI argument).
Do not print raw customer data or secret environment values.
"""
import asyncio
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.mcp.dispatch import execute_mcp_read

async def main():
    bearer = os.environ.get('BANKPILOT_TEST_BEARER', '')
    result = await execute_mcp_read({'type': 'get_balance'}, bearer)
    assert isinstance(result, dict) and 'balance' in result
    print('MCP_BANK_BALANCE_SUCCESS; bank returned validated balance data (value suppressed)')
    result = await execute_mcp_read({'type': 'monthly_analytics', 'month': '2026-10'}, bearer)
    assert isinstance(result, dict) and result.get('month') == '2026-10'
    print('MCP_MONTHLY_ANALYTICS_SUCCESS')

if __name__ == '__main__':
    asyncio.run(main())
