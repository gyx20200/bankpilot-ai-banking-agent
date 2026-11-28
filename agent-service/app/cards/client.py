"""Fixed Java-only demo-card API; no MCP write tool or user-supplied URL."""
from __future__ import annotations
import os
import httpx
from app import banking_client as bank

BASE = os.getenv('BANK_CARD_API_BASE', 'http://127.0.0.1:8080/api/demo/cards').rstrip('/')

async def call(method: str, path: str, bearer: str | None, payload: dict | None = None):
    if os.getenv('BANK_API_MODE', 'java').strip().lower() != 'java':
        raise bank.BankError('D14 模拟卡仅支持 Java/MySQL 模式。', 503)
    if not isinstance(bearer, str) or not bearer.startswith('Bearer ') or not bearer[7:].strip():
        raise bank.BankError('请先登录。', 401)
    if method not in ('GET', 'POST') or (path and not path.startswith('/')):
        raise bank.BankError('不受支持的卡片工具调用。', 400)
    try:
        async with httpx.AsyncClient(timeout=12) as http:
            response = await http.request(method, BASE + path,
                    headers={'Authorization': bearer}, json=payload)
        if response.status_code >= 400:
            code = response.status_code
            raise bank.BankError('Java 卡片服务拒绝请求，请核对原申请。', code if code in (400,401,403,404,409,422) else 502)
        return response.json()
    except bank.BankError:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise bank.BankError('卡片请求结果尚未确认；先查询原申请，不要重复建单。', 502) from exc

async def cards(bearer):
    result=await call('GET','',bearer)
    if not isinstance(result,list): raise bank.BankError('卡片列表格式异常。',502)
    return result

async def applications(bearer):
    result=await call('GET','/applications',bearer)
    if not isinstance(result,list): raise bank.BankError('申请列表格式异常。',502)
    return result

async def application(bearer,aid: int):
    if type(aid) is not int or aid<=0: raise bank.BankError('申请编号无效。',400)
    result=await call('GET',f'/applications/{aid}',bearer)
    if not isinstance(result,dict) or result.get('applicationId')!=aid:
        raise bank.BankError('Java 申请编号不一致。',502)
    return result

async def prepare(bearer,rid: str):
    result=await call('POST','/applications/prepare',bearer,
        {'cardType':'VIRTUAL_DEBIT','requestId':rid})
    if not isinstance(result,dict) or result.get('status')!='PENDING_APPROVAL' or result.get('cardType')!='VIRTUAL_DEBIT':
        raise bank.BankError('卡片建单状态不正确，先查询原单。',409)
    return result

async def confirm(bearer,aid:int,approved:bool):
    if type(approved) is not bool: raise bank.BankError('必须由本人明确审批。',400)
    result=await call('POST',f'/applications/{aid}/confirm',bearer,{'confirmed':approved})
    if not isinstance(result,dict) or result.get('applicationId')!=aid:
        raise bank.BankError('Java 返回的申请编号不一致。',409)
    return result

async def restrict(bearer,cid:int,limit:str,disable_online:bool,rid:str):
    if type(cid) is not int or cid<=0 or type(disable_online) is not bool:
        raise bank.BankError('卡片限制参数无效。',400)
    result=await call('POST',f'/{cid}/restrictions',bearer,{
        'singleTransactionLimit':limit,'disableOnline':disable_online,'requestId':rid})
    if not isinstance(result,dict) or result.get('cardId')!=cid:
        raise bank.BankError('Java 限制变更响应不匹配。',409)
    return result
