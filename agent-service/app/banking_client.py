"""The only module allowed to call the banking backend in the Day 2 demo."""

import os
from typing import Any

import httpx

BANK_API_BASE = os.getenv("BANK_API_BASE", "http://127.0.0.1:8080/api/demo").rstrip("/")
BANK_API_MODE = os.getenv("BANK_API_MODE", "java")  # Set to mock when running mock_backend.py


class BankingServiceError(Exception):
    """A backend call failed. Never invent a successful banking result."""


async def _get(path: str) -> Any:
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=False) as client:
            response = await client.get(f"{BANK_API_BASE}/{path}")
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise BankingServiceError("银行查询接口不可用，请检查 Java 服务和数据库连接。") from exc


async def get_balance() -> dict[str, Any]:
    value = await _get("balance")
    if not isinstance(value, dict) or "balance" not in value:
        raise BankingServiceError("余额接口返回的数据格式不正确。")
    return value


async def get_transactions() -> list[dict[str, Any]]:
    value = await _get("transactions")
    if not isinstance(value, list):
        raise BankingServiceError("交易接口返回的数据格式不正确。")
    return value


async def get_payees() -> list[dict[str, Any]]:
    value = await _get("payees")
    if not isinstance(value, list):
        raise BankingServiceError("收款人接口返回的数据格式不正确。")
    return value


async def get_subscriptions() -> list[dict[str, Any]]:
    value = await _get("subscriptions")
    if not isinstance(value, list):
        raise BankingServiceError("代扣接口返回的数据格式不正确。")
    return value
