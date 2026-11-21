"""D6 Java recovery claim client. Never retry on HTTP timeout/409.

Internal key is restricted to the Python server. All endpoints require the
current Java-verified user Bearer token plus BANKPILOT_AGENT_INTERNAL_KEY.
"""
from __future__ import annotations

import os
from urllib.parse import urlparse
from uuid import UUID

import httpx
from fastapi import HTTPException


def _base() -> str:
    value = os.getenv('BANK_RECOVERY_CLAIM_API_BASE',
                      'http://127.0.0.1:8080/api/workflow-recovery-claims').rstrip('/')
    parsed = urlparse(value)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.username or parsed.password:
        raise HTTPException(503, '恢复登记服务地址不合法')
    if parsed.scheme == 'http' and parsed.hostname not in ('localhost', '127.0.0.1', '::1'):
        raise HTTPException(503, '远程服务必须使用 HTTPS')
    return value


def _headers(authorization: str | None) -> dict[str, str]:
    if not authorization or not authorization.startswith('Bearer ') or not authorization[7:].strip():
        raise HTTPException(401, '请先重新登录银行账户')
    key = os.getenv('BANKPILOT_AGENT_INTERNAL_KEY', '')
    if len(key.encode('utf-8')) < 32:
        raise HTTPException(503, 'Agent 内部服务密钥未配置')
    return {'Authorization': authorization, 'X-Bankpilot-Agent-Key': key}


async def _request(method: str, path: str, authorization: str,
                   payload: dict | None = None, *, missing_ok: bool = False) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
            response = await client.request(method, _base() + path,
                                            headers=_headers(authorization), json=payload)
    except httpx.HTTPError as exc:
        raise HTTPException(503, 'Java 恢复登记状态不确定，请查询原线程，不要再次发起审批') from exc
    if response.status_code == 404 and missing_ok:
        return None
    if response.status_code >= 400:
        code = response.status_code if response.status_code in (400,401,403,404,409,410,422,503) else 502
        raise HTTPException(code, 'Java 恢复登记未确认，请查询原线程，禁止自动重试')
    try:
        value = response.json()
    except ValueError as exc:
        raise HTTPException(502, 'Java 恢复登记返回格式错误') from exc
    if not isinstance(value, dict):
        raise HTTPException(502, 'Java 恢复登记返回结构错误')
    return value


def _uuid(thread_id: str) -> str:
    try:
        return str(UUID(str(thread_id)))
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, '工作流编号格式错误') from exc


async def get_claim(thread_id: str, authorization: str) -> dict | None:
    return await _request('GET', '/' + _uuid(thread_id), authorization, missing_ok=True)


async def create_claim(thread_id: str, checkpoint_id: str, approved: bool,
                       action_id: str, authorization: str) -> dict:
    result = await _request('POST', '', authorization, {
        'threadId': _uuid(thread_id), 'actionId': _uuid(action_id),
        'checkpointId': checkpoint_id, 'approved': approved,
    })
    if (result.get('threadId') != _uuid(thread_id) or result.get('actionId') != _uuid(action_id)
            or result.get('checkpointId') != checkpoint_id or result.get('approved') is not approved
            or result.get('status') != 'CLAIMED'):
        raise HTTPException(502, 'Java 恢复领取响应不一致，禁止执行 Graph')
    return result


async def finalize_claim(thread_id: str, status: str, authorization: str) -> dict:
    if status not in ('COMPLETED', 'REJECTED', 'NOT_CONFIRMED'):
        raise HTTPException(422, '非法恢复结果状态')
    result = await _request('POST', '/' + _uuid(thread_id) + '/finalize',
                            authorization, {'status': status})
    if result.get('threadId') != _uuid(thread_id) or result.get('status') != status:
        raise HTTPException(502, 'Java 未确认恢复结果状态')
    return result
