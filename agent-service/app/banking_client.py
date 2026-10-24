"""HTTP client for known banking endpoints only; no model-generated URLs or SQL."""
import os
from typing import Any
import httpx

BANK_READ_API_BASE = os.getenv("BANK_API_BASE", "http://127.0.0.1:8080/api/demo").rstrip("/")
BANK_TRANSFER_API_BASE = os.getenv("BANK_TRANSFER_API_BASE", "http://127.0.0.1:8080/api/transfers").rstrip("/")
BANK_API_MODE = os.getenv("BANK_API_MODE", "java").lower()


class BankingServiceError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


def _headers(authorization: str | None) -> dict[str, str]:
    if not authorization:
        return {}
    if len(authorization) > 2048 or not authorization.startswith("Bearer ") or not authorization[7:].strip():
        raise BankingServiceError("身份凭证格式无效。", 401)
    return {"Authorization": authorization}


def _handle_error(exc: httpx.HTTPStatusError) -> BankingServiceError:
    code = exc.response.status_code
    messages = {
        400: "业务参数错误，请核对订单内容。",
        401: "请先登录并获取有效的银行登录凭证。",
        403: "当前账户无权执行该操作。",
        404: "收款人或业务资源不存在。",
        409: "业务状态冲突或重复请求，请查询原订单状态。",
        422: "银行接口拒绝了参数，请核对金额与收款人。",
        429: "操作过于频繁，请稍后再试。",
    }
    return BankingServiceError(messages.get(code, "银行业务服务暂时不可用。"), code if code in messages else 502)


async def _call(method: str, url: str, authorization: str | None = None, payload: dict | None = None) -> Any:
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=False) as client:
            response = await client.request(method, url, headers=_headers(authorization), json=payload)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        raise _handle_error(exc) from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise BankingServiceError("银行接口不可用或返回格式错误，请检查后端服务。") from exc


async def _get(path: str, authorization: str | None = None) -> Any:
    return await _call("GET", f"{BANK_READ_API_BASE}/{path}", authorization)


async def get_balance(authorization: str | None = None) -> dict[str, Any]:
    value = await _get("balance", authorization)
    if not isinstance(value, dict) or "balance" not in value:
        raise BankingServiceError("余额接口数据结构不正确。")
    return value


async def get_transactions(authorization: str | None = None) -> list[dict[str, Any]]:
    value = await _get("transactions", authorization)
    if not isinstance(value, list):
        raise BankingServiceError("交易接口数据结构不正确。")
    return value


async def get_payees(authorization: str | None = None) -> list[dict[str, Any]]:
    value = await _get("payees", authorization)
    if not isinstance(value, list):
        raise BankingServiceError("收款人接口数据结构不正确。")
    return value


async def get_subscriptions(authorization: str | None = None) -> list[dict[str, Any]]:
    value = await _get("subscriptions", authorization)
    if not isinstance(value, list):
        raise BankingServiceError("订阅接口数据结构不正确。")
    return value


async def prepare_transfer(payee_id: int, amount: str, request_id: str,
                           authorization: str | None, remark: str = "") -> dict[str, Any]:
    if not authorization:
        raise BankingServiceError("请先取得后端登录令牌，才能创建待确认订单。", 401)
    payload = {"payeeId": payee_id, "amount": amount, "requestId": request_id, "remark": remark}
    value = await _call("POST", f"{BANK_TRANSFER_API_BASE}/prepare", authorization, payload)
    required = ("orderId", "payeeName", "accountMasked", "amount", "riskLevel", "status")
    if not isinstance(value, dict) or any(key not in value for key in required):
        raise BankingServiceError("转账建单接口返回的数据格式不正确。")
    if value["status"] != "PENDING_APPROVAL" or value["riskLevel"] not in ("YELLOW", "RED"):
        raise BankingServiceError("银行返回的订单状态或风险级别异常，请人工核实。")
    return value
