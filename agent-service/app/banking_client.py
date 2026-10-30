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
    request_id: str,
):
    if not bearer:
        raise BankError("请先登录。", 401)
    if confirmation is not True:
        raise BankError("必须由用户明确确认转账订单。", 400)
    oid = _oid(order_id)
    if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", request_id):
        raise BankError("授权请求编号无效。", 400)

    # Java and the Day4 Mock currently use distinct request/response schemas.
    if BANK_MODE == "mock":
        payload = {"confirmation": True, "otpCode": otp_code, "requestId": request_id}
    else:
        payload = {"confirmed": True, "otp": otp_code}

    approval = await _request("POST", f"{TRANSFER_URL}/{oid}/authorize", bearer, payload)
    if not isinstance(approval, dict) or str(approval.get("orderId")) != oid:
        raise BankError("银行授权响应的订单编号无效，请刷新订单状态。", 409)
    if approval.get("riskLevel") not in ("YELLOW", "RED") or approval.get("status") not in (
        "AUTHORIZED", "PENDING_APPROVAL", "CANCELLED", "LOCKED"
    ):
        raise BankError("银行授权结果格式不正确。", 409)
    if BANK_MODE != "mock" and "result" not in approval:
        raise BankError("Java 未返回明确的授权结果。", 409)

    order = await get_order(oid, bearer)
    if str(order['orderId']) != oid:
        raise BankError("银行订单编号不一致。", 409)
    order['result'] = approval.get('result', 'AUTHORIZED' if order['status'] == 'AUTHORIZED' else 'NOT_AUTHORIZED')
    order['remainingAttempts'] = approval.get('remainingAttempts', 0)
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
        bearer,
        {"requestId": request_id} if BANK_MODE == "mock" else None,
    )

    order = _validate_order(result)

    if order["status"] != "CANCELLED":
        raise BankError(
            "取消结果尚未确认，请刷新订单状态。"
        )

    return order




async def cancel_subscription(subscription_id: int, bearer: str, request_id: str):
    """Future Java endpoint; currently 404 in uploaded backend, not a fake success."""
    if not bearer:
        raise BankError('请先登录。', 401)
    if not isinstance(subscription_id, int) or subscription_id <= 0:
        raise BankError('代扣协议 ID 无效。', 400)
    base = os.getenv('BANK_SUBSCRIPTION_API_BASE', 'http://127.0.0.1:8080/api/subscriptions').rstrip('/')
    return await _request('POST', f'{base}/{subscription_id}/cancel', bearer,
                          {'requestId': request_id})


async def demo_login(password: str):
    """Local simulated bank login; forwards credentials only to Java, not LLM."""
    url = os.getenv('BANK_AUTH_API_BASE', 'http://127.0.0.1:8080/api/auth').rstrip('/')
    data = await _request('POST', f'{url}/demo-login', None,
                          {'username': 'demo', 'password': password})
    if not isinstance(data, dict) or not data.get('token'):
        raise BankError('银行未返回有效的演示登录凭证。')
    return data


async def request_transfer_otp(order_id: str, bearer: str):
    if not bearer:
        raise BankError('请先登录。', 401)
    result = await _request('POST', f'{TRANSFER_URL}/{_oid(order_id)}/otp/request', bearer)
    if not isinstance(result, dict) or 'expiresInSeconds' not in result:
        raise BankError('银行未返回有效的验证请求信息。')
    return result


# Day 6: Three-stage subscription cancellation client.
# These routes must match the Java/Mock API contract exactly.
CANCELLATION_URL = os.getenv(
    "BANK_CANCELLATION_API_BASE",
    "http://127.0.0.1:8080/api/subscription-cancellations",
).rstrip("/")


def _cancellation_request_id(request_id: str) -> str:
    # Request IDs are generated by our application and reused for retries.
    if not isinstance(request_id, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_-]{7,127}", request_id
    ):
        raise BankError("取消申请的幂等请求编号不合法。", 400)
    return request_id


def _subscription_id(subscription_id: int) -> int:
    if type(subscription_id) is not int or subscription_id <= 0:
        raise BankError("代扣协议 ID 无效。", 400)
    return subscription_id


def _cancellation_response(value: Any, order_id: str | None = None) -> dict:
    if not isinstance(value, dict) or not all(k in value for k in ("orderId", "status")):
        raise BankError("银行取消申请返回格式不正确，请查询订单状态。")
    returned_id = _oid(value["orderId"])
    if order_id is not None and returned_id != order_id:
        raise BankError("银行返回了不匹配的取消订单编号，请核查状态。")
    return value



async def _complete_subscription_status(
    order: dict,
    bearer: str
) -> dict:
    """从真实银行订阅查询补全取消订单缺少的订阅状态。"""

    if order.get("subscriptionStatus") in ("ACTIVE", "CANCELLED"):
        return order

    sid = order.get("subscriptionId")

    if type(sid) is not int or sid <= 0:
        raise BankError("取消订单缺少有效订阅 ID。", 409)

    # 使用同一个登录用户查询真实订阅
    all_subscriptions = await subscriptions(bearer)

    matches = [
        sub for sub in all_subscriptions
        if isinstance(sub, dict)
        and type(sub.get("id")) is int
        and sub["id"] == sid
    ]

    if len(matches) != 1:
        raise BankError("无法唯一核实原订阅状态。", 409)

    actual = matches[0]

    if actual.get("merchantName") != order.get("merchantName"):
        raise BankError("取消订单与银行订阅商户不一致。", 409)

    status = actual.get("status")

    if status not in ("ACTIVE", "CANCELLED"):
        raise BankError("原订阅状态无法确认。", 409)

    return {**order, "subscriptionStatus": status}



async def prepare_subscription_cancellation(
        subscription_id: int, bearer: str | None, request_id: str
) -> dict:
    """Only creates an approval order; never cancels the subscription."""
    if not bearer:
        raise BankError("请先登录。", 401)
    sid = _subscription_id(subscription_id)
    rid = _cancellation_request_id(request_id)
    response = _cancellation_response(await _request(
        "POST", f"{CANCELLATION_URL}/prepare", bearer,
        {"subscriptionId": sid, "requestId": rid}
    ))
    if response["status"] != "PENDING_APPROVAL" or response.get("subscriptionId") != sid:
        raise BankError("取消申请未获银行确认，请查询订单状态。")
    return response


async def authorize_subscription_cancellation(
        order_id: str, bearer: str | None, request_id: str, confirmed: bool
) -> dict:
    """Only call after an explicit user approval, never on model output alone."""
    if not bearer:
        raise BankError("请先登录。", 401)
    if confirmed is not True:
        raise BankError("未获得用户明确批准，禁止授权取消代扣。", 400)
    oid = _oid(order_id)
    rid = _cancellation_request_id(request_id)
    response = _cancellation_response(await _request(
        "POST", f"{CANCELLATION_URL}/{oid}/authorize", bearer,
        {"confirmed": True, "requestId": rid}
    ), oid)
    if response["status"] != "AUTHORIZED":
        raise BankError("银行尚未确认取消授权，请查询订单状态。")
    return response


async def execute_subscription_cancellation(
        order_id: str, bearer: str | None, request_id: str
) -> dict:
    """Java must independently enforce authorization, ownership, and idempotency."""
    if not bearer:
        raise BankError("请先登录。", 401)
    oid = _oid(order_id)
    rid = _cancellation_request_id(request_id)
    response = _cancellation_response(await _request(
        "POST", f"{CANCELLATION_URL}/{oid}/execute", bearer,
        {"requestId": rid}
    ), oid)
    response = await _complete_subscription_status(response, bearer)
    if response["status"] != "SUCCESS" or response.get("subscriptionStatus") != "CANCELLED":
        raise BankError("银行未确认代扣取消成功，请查询订单状态。")
    return response



async def get_subscription_cancellation(
    order_id: str,
    bearer: str | None
) -> dict:
    if not bearer:
        raise BankError("请先登录。", 401)

    oid = _oid(order_id)

    response = _cancellation_response(
        await _request(
            "GET",
            f"{CANCELLATION_URL}/{oid}",
            bearer
        ),
        oid
    )

    response = await _complete_subscription_status(response, bearer)

    if (
        response["status"] == "SUCCESS"
        and response["subscriptionStatus"] != "CANCELLED"
    ):
        raise BankError(
            "订单成功状态与协议状态不一致，请核查银行记录。",
            409
        )

    return response


# Day 6 阶段 4D：拒绝待审批的取消申请


async def reject_subscription_cancellation(
        order_id: str, bearer: str | None, request_id: str
) -> dict:
    """拒绝取消申请，兼容 Java 与 Mock 后端。"""

    if not bearer:
        raise BankError("请先登录。", 401)

    oid = _oid(order_id)
    rid = _cancellation_request_id(request_id)

    if BANK_MODE == "mock":
        url = f"{CANCELLATION_URL}/{oid}/reject"
        payload = {"requestId": rid}
        expected_status = "REJECTED"
    else:
        url = f"{CANCELLATION_URL}/{oid}/authorize"
        payload = {"confirmed": False}
        expected_status = "CANCELLED"

    response = _cancellation_response(
        await _request("POST", url, bearer, payload),
        oid,
    )
    response = await _complete_subscription_status(response, bearer)

    if (
        response.get("status") != expected_status
        or response.get("subscriptionStatus") != "ACTIVE"
    ):
        raise BankError(
            "银行未确认拒绝取消申请，请查询订单状态。",
            409,
        )

    return response



# Day 7: Proposed Java API contract. Do not simulate authenticated success.
AUTH_URL = os.getenv("BANK_AUTH_API_BASE", "http://127.0.0.1:8080/api/auth").rstrip("/")


async def register_user(payload: dict) -> dict:
    data = await _request("POST", f"{AUTH_URL}/register", None, payload)
    if (not isinstance(data, dict) or type(data.get("userId")) is not int
            or data["userId"] <= 0 or data.get("status") != "REGISTERED"):
        raise BankError("银行注册结果格式不正确。", 502)
    return {"userId": data["userId"], "status": "REGISTERED"}


async def login_user(username: str, password: str) -> dict:
    data = await _request("POST", f"{AUTH_URL}/login", None,
                          {"username": username, "password": password})
    if (not isinstance(data, dict) or not isinstance(data.get("token"), str)
            or not data["token"] or data.get("tokenType") != "Bearer"
            or type(data.get("expiresInSeconds")) is not int
            or data["expiresInSeconds"] <= 0):
        raise BankError("银行登录结果格式不正确。", 502)
    if not isinstance(data.get("displayName"), str) or not data["displayName"].strip():
        raise BankError("银行登录用户信息格式不正确。", 502)
    return data


async def current_user(bearer: str | None) -> dict:
    if not bearer:
        raise BankError("请先登录。", 401)
    data = await _request("GET", f"{AUTH_URL}/me", bearer)
    if (not isinstance(data, dict) or type(data.get("userId")) is not int
            or data["userId"] <= 0 or not isinstance(data.get("displayName"), str)
            or not data["displayName"].strip()):
        raise BankError("银行当前用户信息格式不正确。", 502)
    return data


async def logout_user(bearer: str | None) -> dict:
    if not bearer:
        raise BankError("请先登录。", 401)
    data = await _request("POST", f"{AUTH_URL}/logout", bearer)
    if not isinstance(data, dict) or data.get("status") != "logged_out":
        raise BankError("无法确认登录凭证已撤销，请检查登录状态。", 502)
    return data


async def search_registered_recipients(bearer: str | None, *, name: str | None = None,
                                       phone: str | None = None) -> list[dict]:
    """Bank-authoritative, current-user scoped directory search. Never trust model IDs."""
    if not bearer:
        raise BankError('请先登录。', 401)
    if not name and not phone:
        raise BankError('需要收款人姓名或手机号。', 400)
    if name and (len(name) > 50 or not name.strip()):
        raise BankError('收款人姓名无效。', 400)
    if phone and not re.fullmatch(r'1[3-9]\d{9}', phone):
        raise BankError('手机号格式无效。', 400)
    query = urlencode({k: v for k, v in (('name', name), ('phone', phone)) if v})
    items = await _request('GET', f'{TRANSFER_URL}/recipients/search?{query}', bearer)
    if not isinstance(items, list) or len(items) > 30:
        raise BankError('银行收款人目录响应异常。', 502)
    results, seen = [], set()
    for item in items:
        if (not isinstance(item, dict) or type(item.get('recipientId')) is not int
                or item['recipientId'] <= 0 or not isinstance(item.get('payeeName'), str)
                or not item['payeeName'].strip() or not isinstance(item.get('accountMasked'), str)
                or not item['accountMasked'].strip()):
            raise BankError('银行收款人目录包含不合法的候选资料。', 502)
        if (name and item['payeeName'].strip() != name.strip()) or (item['recipientId'] in seen):
            raise BankError('银行收款人目录结果与查询不一致。', 502)
        seen.add(item['recipientId'])
        results.append({'recipientId': item['recipientId'],
                        'payeeName': item['payeeName'].strip(),
                        'accountMasked': item['accountMasked']})
    return results


async def confirm_registered_recipient(recipient_id: int, bearer: str | None) -> dict:
    """Java rechecks recipient then returns existing or upserted current-user payeeId."""
    if not bearer or type(recipient_id) is not int or recipient_id <= 0:
        raise BankError('收款人选择不合法。', 400)
    value = await _request('POST', f'{TRANSFER_URL}/recipients/confirm', bearer,
                           {'recipientId': recipient_id})
    if (not isinstance(value, dict) or type(value.get('id')) is not int or value['id'] <= 0
            or not isinstance(value.get('payeeName'), str)
            or not isinstance(value.get('payeeAccountMasked'), str)):
        raise BankError('银行未返回可信的收款人绑定结果。', 502)
    return value


# Day 7 stage 3: AA collection is bank-owned. This API never lets the
# originator authorize or debit another account.
AA_URL = os.getenv('BANK_AA_API_BASE', 'http://127.0.0.1:8080/api/aa').rstrip('/')


def _aa_view(value: Any) -> dict:
    if (not isinstance(value, dict) or not isinstance(value.get('collectionId'), str)
            or not ORDER_RE.fullmatch(value['collectionId'])
            or value.get('status') not in ('DRAFT', 'PUBLISHED', 'CANCELLED', 'PARTIAL', 'COMPLETED')
            or type(value.get('initiatorId')) is not int
            or not isinstance(value.get('items'), list)):
        raise BankError('AA 银行收款单响应无效。', 502)
    for item in value['items']:
        if (not isinstance(item, dict) or not isinstance(item.get('itemId'), str)
                or not ORDER_RE.fullmatch(item['itemId'])
                or type(item.get('payerId')) is not int
                or item.get('status') not in ('PENDING', 'PAYING', 'PAID', 'DECLINED', 'FAILED')
                or not isinstance(item.get('amount'), str)):
            raise BankError('AA 银行付款明细无效。', 502)
    return value


async def aa_prepare(people: list[str], amount: str, mode: str, reason: str,
                     request_id: str, bearer: str | None) -> dict:
    if not bearer or not people or mode not in ('total_with_self', 'per_person'):
        raise BankError('AA 发起参数不完整。', 400)
    value = await _request('POST', f'{AA_URL}/prepare', bearer,
                           {'participants': people, 'amount': amount,
                            'splitMode': mode, 'reason': reason, 'requestId': request_id})
    value = _aa_view(value)
    if value['status'] != 'DRAFT' or len(value['items']) != len(people):
        raise BankError('银行没有正确创建待确认 AA 明细。', 502)
    return value


async def aa_get(collection_id: str, bearer: str | None) -> dict:
    return _aa_view(await _request('GET', f'{AA_URL}/{_oid(collection_id)}', bearer))


async def aa_publish(collection_id: str, request_id: str, bearer: str | None) -> dict:
    return _aa_view(await _request('POST', f'{AA_URL}/{_oid(collection_id)}/publish', bearer,
                                   {'requestId': request_id}))


async def aa_cancel_draft(collection_id: str, request_id: str, bearer: str | None) -> dict:
    return _aa_view(await _request('POST', f'{AA_URL}/{_oid(collection_id)}/cancel-draft', bearer,
                                   {'requestId': request_id}))


async def aa_outgoing(bearer: str | None) -> list[dict]:
    value = await _request('GET', f'{AA_URL}/outgoing', bearer)
    if not isinstance(value, list):
        raise BankError('银行 AA 发起列表响应无效。', 502)
    return [_aa_view(x) for x in value]


async def aa_inbox(bearer: str | None) -> list[dict]:
    value = await _request('GET', f'{AA_URL}/inbox', bearer)
    if not isinstance(value, list):
        raise BankError('银行 AA 待付款列表响应无效。', 502)
    for item in value:
        if (not isinstance(item, dict) or not ORDER_RE.fullmatch(str(item.get('itemId', '')))
                or item.get('status') not in ('PENDING', 'PAYING', 'PAID', 'DECLINED', 'FAILED')
                or not isinstance(item.get('amount'), str)):
            raise BankError('银行 AA 待付款明细格式无效。', 502)
    return value


async def aa_payment_prepare(item_id: str, request_id: str, bearer: str | None) -> dict:
    value = await _request('POST', f'{AA_URL}/items/{_oid(item_id)}/payment/prepare', bearer,
                           {'requestId': request_id})
    if (not isinstance(value, dict) or not value.get('orderId')
            or value.get('status') != 'PENDING_APPROVAL'
            or value.get('riskLevel') not in ('YELLOW', 'RED')):
        raise BankError('AA 付款订单未进入银行审批状态。', 502)
    return value


async def aa_payment_otp(item_id: str, bearer: str | None) -> dict:
    return await _request('POST', f'{AA_URL}/items/{_oid(item_id)}/otp/request', bearer)


async def aa_payment_confirm(item_id: str, request_id: str, otp: str | None,
                             bearer: str | None) -> dict:
    value = await _request('POST', f'{AA_URL}/items/{_oid(item_id)}/payment/confirm', bearer,
                           {'requestId': request_id, 'confirmed': True, 'otpCode': otp})
    if not isinstance(value, dict) or value.get('status') != 'PAID' or not value.get('transferOrderId'):
        raise BankError('银行未确认 AA 付款及交易流水完成。', 502)
    return value


async def aa_decline(item_id: str, request_id: str, bearer: str | None) -> dict:
    value = await _request('POST', f'{AA_URL}/items/{_oid(item_id)}/decline', bearer,
                           {'requestId': request_id})
    if not isinstance(value, dict) or value.get('status') != 'DECLINED':
        raise BankError('银行尚未确认 AA 拒绝。', 502)
    return value


async def aa_payment_get(item_id: str, bearer: str | None) -> dict:
    value = await _request('GET', f'{AA_URL}/items/{_oid(item_id)}/payment', bearer)
    if not isinstance(value, dict) or not value.get('orderId') or value.get('status') not in ('PENDING_APPROVAL', 'AUTHORIZED', 'SUCCESS', 'FAILED', 'CANCELLED'):
        raise BankError('AA 原付款订单数据无效。', 502)
    return value

# Stage 4: scheduled transfers use bank-owned durable authorization and execution.
# In mock mode, default to the configured mock service host to avoid an AA-like 8080 mismatch.
_SCHEDULE_DEFAULT = ((READ_URL.rsplit('/api/demo', 1)[0] if BANK_MODE == 'mock'
                      else TRANSFER_URL.rsplit('/api/transfers', 1)[0])
                     + '/api/scheduled-transfers')
SCHEDULE_URL = os.getenv('BANK_SCHEDULE_API_BASE', _SCHEDULE_DEFAULT).rstrip('/')


def _schedule(value: Any) -> dict:
    if (not isinstance(value, dict) or not isinstance(value.get('scheduleId'), str)
            or value.get('status') not in ('PENDING_AUTH', 'SCHEDULED', 'PROCESSING',
                                           'SUCCESS', 'FAILED', 'CANCELLED', 'MISSED', 'UNKNOWN')
            or not isinstance(value.get('amount'), str)
            or not isinstance(value.get('executeAt'), str)):
        raise BankError('银行预约返回数据格式不正确。')
    return value


async def scheduled_prepare(payee_id: int, amount: str, execute_at: str, remark: str,
                            request_id: str, bearer: str | None) -> dict:
    if not bearer:
        raise BankError('请先登录。', 401)
    return _schedule(await _request('POST', f'{SCHEDULE_URL}/prepare', bearer, {
        'payeeId': payee_id, 'amount': amount, 'executeAt': execute_at,
        'remark': remark, 'requestId': request_id,
    }))


async def scheduled_get(schedule_id: str, bearer: str | None) -> dict:
    if not bearer:
        raise BankError('请先登录。', 401)
    return _schedule(await _request('GET', f'{SCHEDULE_URL}/{_oid(schedule_id)}', bearer))


async def scheduled_list(bearer: str | None) -> list[dict]:
    if not bearer:
        raise BankError('请先登录。', 401)
    response = await _request('GET', f'{SCHEDULE_URL}/mine', bearer)
    if not isinstance(response, list):
        raise BankError('银行预约列表格式不正确。')
    return [_schedule(v) for v in response]


async def scheduled_otp_request(schedule_id: str, bearer: str | None) -> dict:
    if not bearer:
        raise BankError('请先登录。', 401)
    res = await _request('POST', f'{SCHEDULE_URL}/{_oid(schedule_id)}/otp/request', bearer)
    if not isinstance(res, dict) or res.get('scheduleId') != schedule_id or not isinstance(res.get('expiresInSeconds'), int):
        raise BankError('预约 OTP 返回数据无效。')
    return res


async def scheduled_authorize(schedule_id: str, request_id: str, otp_code: str,
                              bearer: str | None) -> dict:
    if not bearer or not re.fullmatch(r'\d{6}', otp_code):
        raise BankError('预约必须由本人完成六位 OTP 强验证。', 422)
    return _schedule(await _request('POST', f'{SCHEDULE_URL}/{_oid(schedule_id)}/authorize', bearer, {
        'requestId': request_id, 'confirmed': True, 'otpCode': otp_code,
    }))


async def scheduled_cancel(schedule_id: str, request_id: str, bearer: str | None) -> dict:
    if not bearer:
        raise BankError('请先登录。', 401)
    return _schedule(await _request('POST', f'{SCHEDULE_URL}/{_oid(schedule_id)}/cancel', bearer, {
        'requestId': request_id,
    }))
