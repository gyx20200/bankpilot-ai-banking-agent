"""Discover MCP tool schemas with a fake bearer; never makes a bank read."""
from __future__ import annotations
import asyncio
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mcp import Client, StdioServerParameters
from app.mcp.dispatch import child_env
from app.mcp.policy import ALLOWED

async def main():
    params=StdioServerParameters(command=sys.executable,
                                args=['-m','app.mcp.server'],
                                env=child_env('Bearer discovery-only-not-a-real-token'))
    async with Client(params) as client:
        tools=(await client.list_tools()).tools
        names={t.name for t in tools}
        assert names == {tool for tool, _ in ALLOWED.values()}, sorted(names)
        for tool in tools:
            text=str(tool.input_schema).lower()
            assert 'token' not in text and 'authorization' not in text and 'otp' not in text
            print(tool.name, 'inputSchema=', tool.input_schema)
        print(f'MCP_DISCOVERY_SUCCESS tools={len(names)} no_sensitive_parameters=true')

if __name__=='__main__':
    asyncio.run(main())
