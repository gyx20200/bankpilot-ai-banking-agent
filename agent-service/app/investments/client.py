"""Static Java-only investment URLs; no MCP write capability and no user-controlled paths."""
from __future__ import annotations
import os
from decimal import Decimal
import httpx
from app import banking_client as bank

BASE = os.getenv('BANK_INVESTMENT_API_BASE', 'http://127.0.0.1:8080/api/demo/investments').rstrip('/')


def _auth(bearer: str | None) -> dict[str, str]:
    if os.getenv('BANK_API_MODE','java').strip().lower() != 'java':
        raise bank.BankError('模拟理财仅支持 Java/MySQL 模式。', 503)
    if not isinstance(bearer, str) or not bearer.startswith('Bearer ') or not bearer[7:].strip():
        raise bank.BankError('请先登录。', 401)
    return {'Authorization': bearer}


async def call(method: str, path: str, bearer: str, payload: dict | None = None):
    # Only this trusted module may construct fixed investment API paths.
    if method not in ('GET', 'POST') or not path.startswith('/'):
        raise bank.BankError('理财接口调用不受支持。', 400)
    headers = _auth(bearer)
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.request(method, BASE + path, headers=headers, json=payload)
        if response.status_code >= 400:
            status = response.status_code
            raise bank.BankError('银行未接受该理财操作；请查询原始订单。', status if status in (400,401,403,404,409,422) else 502)
        return response.json()
    except bank.BankError:
        raise
    except (httpx.HTTPError, ValueError) as ex:
        raise bank.BankError('理财订单结果不明确，请查询原单，不要创建新申请。', 502) from ex


async def products(bearer: str) -> list[dict]:
    value = await call('GET', '/products', bearer)
    if not isinstance(value, list):
        raise bank.BankError('理财产品返回格式不正确。', 502)
    return value


async def portfolio(bearer: str) -> list[dict]:
    value = await call('GET', '/portfolio', bearer)
    if not isinstance(value, list):
        raise bank.BankError('持仓返回格式不正确。', 502)
    return value


async def profile(bearer: str) -> dict:
    value = await call('GET', '/profile', bearer)
    if not isinstance(value, dict) or not isinstance(value.get('riskLevel'),int):
        raise bank.BankError('风险测评状态不明确。', 502)
    return value


async def assess(bearer: str, scores: dict) -> dict:
    return await call('POST', '/profile/assess', bearer, scores)


async def prepare(bearer: str, product_id: int, action: str, units: str, request_id: str) -> dict:
    value = await call('POST', '/orders/prepare', bearer, {
        'productId': product_id, 'action': action, 'units': units, 'requestId': request_id,
    })
    if not isinstance(value,dict) or value.get('status') != 'PENDING_APPROVAL' or value.get('productId') != product_id or value.get('action') != action or Decimal(str(value.get('units'))) != Decimal(units):
        raise bank.BankError('银行准备订单不符合请求，请查询原单。', 409)
    return value


async def order(bearer: str, order_id: int) -> dict:
    if type(order_id) is not int or order_id <= 0: raise bank.BankError('订单编号无效。',400)
    value = await call('GET', f'/orders/{order_id}', bearer)
    if not isinstance(value, dict) or value.get('orderId') != order_id:
        raise bank.BankError('银行订单返回异常。', 502)
    return value


async def orders(bearer: str) -> list[dict]:
    value = await call('GET', '/orders', bearer)
    if not isinstance(value,list): raise bank.BankError('理财订单列表异常。',502)
    return value


async def confirm(bearer: str, order_id: int, approved: bool) -> dict:
    if type(approved) is not bool:
        raise bank.BankError('必须由用户明确选择批准或拒绝。',400)
    value=await call('POST', f'/orders/{order_id}/confirm',bearer,{'confirmed':approved})
    if not isinstance(value,dict) or value.get('orderId') != order_id:
        raise bank.BankError('银行确认响应订单不匹配。',409)
    return value
