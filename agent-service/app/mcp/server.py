"""D10 MCP v2 local stdio server: bank-authorized reads, never money writes.

The bank bearer is injected into a dedicated child *process* by the trusted
FastAPI executor; it is never an MCP tool argument or a model-visible field.
Only run this server locally under the same OS account as BankPilot.
"""
from __future__ import annotations
import os

from mcp.server import MCPServer
from app import banking_client as bank
from app.rag.answer import answer_public_question
from app.rag.policy import validate_public_query
from typing import Any

mcp = MCPServer("BankPilotReadOnly")


def _authorization() -> str:
    value = os.environ.get("BANKPILOT_MCP_AUTHORIZATION", "")
    if not value.startswith("Bearer ") or not value[7:].strip() or len(value)>2048:
        raise ValueError("Bank user authentication required")
    return value


@mcp.tool()
async def bank_get_balance() -> dict[str, Any]:
    """只读：查询当前认证用户的模拟银行余额。"""
    return {
        "data": await bank.balance(_authorization())
    }


@mcp.tool()
async def bank_get_transactions() -> dict[str, Any]:
    """READ ONLY: list the authenticated user's simulated transactions."""
    return {"data": await bank.transactions(_authorization())}


@mcp.tool()
async def bank_get_payees() -> dict[str, Any]:
    """READ ONLY: list the authenticated user's saved recipients; no transfers."""
    return {"data": await bank.payees(_authorization())}


@mcp.tool()
async def bank_list_subscriptions() -> dict[str, Any]:
    """READ ONLY: inspect the authenticated user's subscriptions."""
    return {"data": await bank.subscriptions(_authorization())}


@mcp.tool()
async def bank_monthly_analytics(month: str) -> dict[str, Any]:
    """READ ONLY: return deterministic Java bank analytics for YYYY-MM."""
    return {"data": await bank.get_monthly_analytics(month, _authorization())}


@mcp.tool()
async def bank_annual_analytics(year: str) -> dict[str, Any]:
    """READ ONLY: return deterministic Java bank analytics for YYYY."""
    return {"data": await bank.get_annual_analytics(year, _authorization())}


@mcp.tool()
async def bank_transaction_anomalies(month: str) -> dict[str, Any]:
    """READ ONLY: return Java's explainable anomaly events for YYYY-MM."""
    return {"data": await bank.get_transaction_anomalies(month, _authorization())}


@mcp.tool()
async def public_knowledge_search(query: str) -> dict[str, Any]:
    """READ ONLY: answer an approved public finance question using RAG citations."""
    # Require a current BankPilot user session even for public facts.
    await bank.current_user(_authorization())
    return {"data": await answer_public_question(validate_public_query(query))}


if __name__ == "__main__":
    mcp.run()  # stdio: do not print to stdout
