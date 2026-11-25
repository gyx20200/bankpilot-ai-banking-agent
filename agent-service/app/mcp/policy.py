"""Exact allowed task/tool mapping. This is a security boundary, not a prompt."""
from __future__ import annotations
import re
from typing import Any

ALLOWED: dict[str, tuple[str, tuple[str, ...]]] = {
    "get_balance": ("bank_get_balance", ()),
    "get_transactions": ("bank_get_transactions", ()),
    "get_payees": ("bank_get_payees", ()),
    "list_subscriptions": ("bank_list_subscriptions", ()),
    "monthly_analytics": ("bank_monthly_analytics", ("month",)),
    "annual_analytics": ("bank_annual_analytics", ("year",)),
    "transaction_anomalies": ("bank_transaction_anomalies", ("month",)),
    "knowledge_search": ("public_knowledge_search", ("query",)),
}

class MCPReadError(RuntimeError):
    """Do not disclose bank credentials or untrusted MCP error text."""


def tool_for_task(task: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    if not isinstance(task, dict):
        raise MCPReadError("MCP task must be an object")
    task_type = task.get("type")
    if not isinstance(task_type, str) or task_type not in ALLOWED:
        raise MCPReadError("MCP task type not allowed")
    tool_name, fields = ALLOWED[task_type]
    args = {key: task.get(key) for key in fields}
    if set(task) != {"type", *fields}:
        # BankPilot planner may add optional null fields. Those are ignored only
        # when truly null; populated extra fields must never affect the tool call.
        if any(v is not None for k,v in task.items() if k not in {"type", *fields}):
            raise MCPReadError("Unexpected MCP task parameters")
    if any(not isinstance(x, str) or not x.strip() for x in args.values()):
        raise MCPReadError("Missing MCP tool argument")
    if "month" in args and not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", args["month"]):
        raise MCPReadError("Invalid month")
    if "year" in args and not re.fullmatch(r"[0-9]{4}", args["year"]):
        raise MCPReadError("Invalid year")
    if "query" in args:
        from app.rag.policy import validate_public_query
        try:
            args["query"] = validate_public_query(args["query"])
        except ValueError as exc:
            raise MCPReadError("Not a public knowledge query") from exc
    return tool_name, args


def read_mode() -> str:
    import os
    mode = os.getenv("BANKPILOT_MCP_READ_MODE", "off").strip().lower()
    if mode not in {"off", "on"}:
        raise MCPReadError("BANKPILOT_MCP_READ_MODE must be off/on")
    return mode
