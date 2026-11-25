"""Trusted LangGraph executor -> isolated per-request stdio MCP v2 child."""
from __future__ import annotations
import os
import sys
import logging
from pathlib import Path
from typing import Any
from .policy import MCPReadError, ALLOWED, tool_for_task

logger = logging.getLogger("bankpilot.mcp")

ALLOWED_ENV = (
    "PATH", "SYSTEMROOT", "COMSPEC", "TMP", "TEMP", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA",
    "BANK_API_MODE", "BANK_API_BASE", "BANK_TRANSFER_API_BASE",
    "BANKPILOT_RAG_DIR", "BANKPILOT_RAG_MIN_SIMILARITY", "BANKPILOT_RERANK_MODE", "BANKPILOT_RAG_TRACE_ENABLED",
    "MODEL_MODE", "MODEL_API_KEY", "MODEL_BASE_URL", "MODEL_NAME",
    "HF_HOME", "HF_HUB_CACHE", "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE",
)


def child_env(bearer: str) -> dict[str, str]:
    if not isinstance(bearer, str) or not bearer.startswith("Bearer ") or not bearer[7:].strip() or len(bearer) > 2048:
        raise MCPReadError("Missing user authentication for MCP")
    env = {key: os.environ[key] for key in ALLOWED_ENV if key in os.environ}
    # In each isolated process, identity cannot be changed through MCP tool args.
    env["BANKPILOT_MCP_AUTHORIZATION"] = bearer
    agent_root = Path(__file__).resolve().parents[2]
    env["PYTHONPATH"] = str(agent_root)
    # D10 must not accidentally read Mock responses during real-bank acceptance.
    if env.get("BANK_API_MODE", "java").lower() != "java":
        raise MCPReadError("MCP read integration requires Java bank mode")
    return env


async def execute_mcp_read(task: dict[str, Any], bearer: str) -> Any:
    tool_name, args = tool_for_task(task)
    logger.info("MCP_READ_START tool=%s", tool_name)
    env = child_env(bearer)
    # Imported lazily: previous D1-D9 tests continue to work without MCP installed.
    from mcp import Client, StdioServerParameters
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "app.mcp.server"],
        env=env,
    )
    try:
        async with Client(params) as client:
            # Discovery is a runtime allowlist check, not permission granting.
            available = {x.name for x in (await client.list_tools()).tools}
            if not available.issubset(set(name for name, _ in ALLOWED.values())):
                raise MCPReadError("Unexpected MCP tools advertised")
            if tool_name not in available:
                raise MCPReadError("Required MCP tool not registered")
            response = await client.call_tool(tool_name, args)
            if response.is_error:
                raise MCPReadError("MCP tool rejected the read; no banking writes performed")
            structured = response.structured_content
            if not isinstance(structured, dict) or "data" not in structured:
                raise MCPReadError("MCP structured response invalid")
            logger.info("MCP_READ_SUCCESS tool=%s", tool_name)
            return structured["data"]
    except MCPReadError:
        raise
    except Exception as exc:
        # Do not include raw errors: they may include credentials, URLs or output.
        raise MCPReadError("MCP read transport failed; no automatic fallback") from exc
