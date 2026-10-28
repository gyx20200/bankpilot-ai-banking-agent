"""Strict whitelist of backend routes, no dynamic paths from model responses.

Only the browser's user action may invoke authorize/execute/cancel endpoints.
Java must independently authenticate, authorize, enforce idempotency/transactions.
"""
import os
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode
from typing import Any
import httpx

READ_URL = os.environ.get("BANK_API_BASE", "http://127.0.0.1:8080/api/demo").rstrip("/")
TRANSFER_URL = os.environ.get("BANK_TRANSFER_API_BASE", "http://127.0.0.1:8080/api/transfers").rstrip("/")
BANK_MODE = os.environ.get("BANK_API_MODE", "java").lower()
ORDER_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class BankError(Exception):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def _headers(bearer: str | None) -> dict[str, str]:
    if not bearer:
        return {}
    if len(bearer) > 2048 or not bearer.startswith("Bearer ") or not bearer[7:].strip():
        raise BankError("登录凭证格式错误。", 401)
    return {"Authorization": bearer}


def _oid(order_id: str) -> str:
    if not ORDER_RE.fullmatch(str(order_id)):
        raise BankError("订单编号格式错误。", 400)
    return str(order_id)


async def _request(method: str, url: str, bearer: str | None = None, data: dict | None = None) -> Any:
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
            response = await client.request(method, url, headers=_headers(bearer), json=data)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as ex:
        status = ex.response.status_code
        mapping = {
            400: "请求参数不正确。", 401: "登录状态无效，请重新登录。",
            403: "授权失败、验证码错误或没有操作权限。", 404: "订单不存在。",
            409: "订单状态冲突，请刷新订单状态后处理。",
            422: "业务参数不满足要求。", 429: "操作太频繁，暂时无法继续。",
        }
        raise BankError(mapping.get(status, "银行业务服务异常。"), status if status in mapping else 502) from ex
    except (httpx.HTTPError, ValueError) as ex:
        raise BankError("无法确定银行接口的处理结果，请查询订单状态，勿立即重复执行。") from ex


async def balance(bearer: str | None):
    value = await _request("GET", f"{READ_URL}/balance", bearer)
    if not isinstance(value, dict) or "balance" not in value: raise BankError("余额数据格式不正确。")
    return value


async def transactions(bearer: str | None):
    value = await _request("GET", f"{READ_URL}/transactions", bearer)
    if not isinstance(value, list): raise BankError("交易流水数据格式不正确。")
    return value


async def payees(bearer: str | None):
    value = await _request("GET", f"{READ_URL}/payees", bearer)
    if not isinstance(value, list): raise BankError("收款人数据格式不正确。")
    return value


async def subscriptions(bearer: str | None):
    value = await _request("GET", f"{READ_URL}/subscriptions", bearer)
    if not isinstance(value, list): raise BankError("代扣数据格式不正确。")
    return value


async def get_monthly_analytics(month: str, bearer: str | None):
    """Fetch SQL-backed monthly totals; model input never controls API path or SQL."""
    if not bearer:
        raise BankError("请先登录。", 401)
    if not isinstance(month, str) or not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", month):
        raise BankError("月份必须使用 YYYY-MM 格式。", 400)

    query = urlencode({"month": month})
    report = await _request("GET", f"{READ_URL}/analytics/monthly?{query}", bearer)

    required = ("month", "currency", "totalIncome", "totalExpense", "netCashFlow", "categories")
    if not isinstance(report, dict) or any(field not in report for field in required):
        raise BankError("月度分析结果格式不正确。")
    if report["month"] != month or not isinstance(report["categories"], list):
        raise BankError("银行返回的月份或分类信息不正确。")
    for name in ("totalIncome", "totalExpense", "netCashFlow"):
        try:
            amount = Decimal(str(report[name]))
        except (InvalidOperation, TypeError, ValueError) as ex:
            raise BankError("银行返回的收支金额格式不正确。") from ex
        if not amount.is_finite():
            raise BankError("银行返回的收支金额格式不正确。")
    return report


def _validate_order(value):
    if not isinstance(value, dict) or any(field not in value for field in ("orderId", "status", "amount", "riskLevel")):
        raise BankError("银行订单返回数据格式不正确。")
    return value


async def prepare_transfer(payee_id: int, amount: str, request_id: str, bearer: str | None, remark: str = ""):
    if not bearer: raise BankError("请先登录后再创建订单。", 401)
    order = await _request("POST", f"{TRANSFER_URL}/prepare", bearer,
                           {"payeeId": payee_id, "amount": amount, "requestId": request_id, "remark": remark})
    _validate_order(order)
    if order["status"] != "PENDING_APPROVAL" or order["riskLevel"] not in ("YELLOW", "RED"):
        raise BankError("建单状态异常，未报告成功。")
    return order


async def get_order(order_id: str, bearer: str | None):
    if not bearer: raise BankError("请先登录。", 401)
    return _validate_order(await _request("GET", f"{TRANSFER_URL}/{_oid(order_id)}", bearer))



async def authorize_transfer(
    order_id: str,
    bearer: str | None,
    confirmation: bool,
    otp_code: str | None,
    request_id: str
):
    if not bearer:
        raise BankError("请先登录。", 401)

    # 1. 调用 Java 的授权接口
    approval = await _request(
        "POST",
        f"{TRANSFER_URL}/{_oid(order_id)}/authorize",
        bearer,
        {
            "confirmed": confirmation,
            "otp": otp_code
        }
    )

    # 2. 校验授权响应，而非使用订单响应校验器
    if (
        not isinstance(approval, dict)
        or any(
            key not in approval
            for key in ("orderId", "riskLevel", "status", "result")
        )
        or str(approval["orderId"]) != str(order_id)
    ):
        raise BankError(
            "银行授权返回数据格式不正确，请刷新订单状态。"
        )

    # 3. 查询最新订单状态，获取完整订单字段
    order = await get_order(order_id, bearer)

    # 4. 保留授权结果，供 Agent 判断后续动作
    order["result"] = approval["result"]
    order["remainingAttempts"] = approval.get(
        "remainingAttempts", 0
    )

    return order



async def execute_transfer(order_id: str, bearer: str | None, request_id: str):
    if not bearer: raise BankError("请先登录。", 401)
    return _validate_order(await _request("POST", f"{TRANSFER_URL}/{_oid(order_id)}/execute", bearer,
                                          {"requestId": request_id}))




async def cancel_transfer(
    order_id: str,
    bearer: str | None,
    request_id: str
):
    if not bearer:
        raise BankError("请先登录。", 401)

    oid = _oid(order_id)

    current = await get_order(oid, bearer)

    if current["status"] not in (
        "PENDING_APPROVAL",
        "AUTHORIZED",
        "CANCELLED"
    ):
        raise BankError(
            "订单已经执行或不允许取消。",
            409
        )

    # Java 负责真正的取消、并发控制和审计
    result = await _request(
        "POST",
        f"{TRANSFER_URL}/{oid}/cancel",
        bearer
    )

    order = _validate_order(result)

    if order["status"] != "CANCELLED":
        raise BankError(
            "取消结果尚未确认，请刷新订单状态。"
        )

    return order


