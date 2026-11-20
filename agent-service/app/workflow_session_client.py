"""BankPilot D5: authenticated Java-owned workflow registry client.

The Java backend authorizes the JWT user and internal Agent service key on every
request. No bearer token or service key is written to a checkpoint or log.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlparse
from uuid import UUID

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

Status = Literal['RUNNING', 'WAITING', 'COMPLETED', 'REJECTED', 'ENDED', 'NOT_CONFIRMED']


class WorkflowSession(BaseModel):
    model_config = ConfigDict(extra='ignore')
    threadId: UUID
    conversationId: UUID
    sourceRequestId: str = Field(pattern=r'^[A-Za-z0-9_-]{8,64}$')
    status: Status
    createdAt: datetime
    expiresAt: datetime

    @model_validator(mode='after')
    def validate_timestamps(self):
        if self.createdAt.tzinfo is None or self.expiresAt.tzinfo is None:
            raise ValueError('workflow timestamps must be timezone-aware')
        if self.expiresAt <= self.createdAt:
            raise ValueError('workflow expiry must follow creation')
        return self

    @property
    def expired(self) -> bool:
        return datetime.now(timezone.utc) >= self.expiresAt.astimezone(timezone.utc)


def _base() -> str:
    base = os.getenv('BANK_WORKFLOW_SESSION_API_BASE',
                     'http://127.0.0.1:8080/api/workflow-sessions').rstrip('/')
    parsed = urlparse(base)
    # Never transmit the internal Agent key over plaintext to a remote host.
    if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.username or parsed.password:
        raise HTTPException(503, '工作流登记服务地址无效')
    if parsed.scheme == 'http' and (parsed.hostname not in ('127.0.0.1', 'localhost', '::1')):
        raise HTTPException(503, '非本地工作流服务必须使用 HTTPS')
    return base


def _uuid(value: str) -> str:
    try:
        return str(UUID(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise HTTPException(422, '工作流或会话UUID不合法') from exc


def _headers(authorization: str | None) -> dict[str, str]:
    if not authorization or not authorization.startswith('Bearer ') or not authorization[7:].strip():
        raise HTTPException(401, '请先登录银行账户')
    key = os.getenv('BANKPILOT_AGENT_INTERNAL_KEY', '')
    if len(key.encode('utf-8')) < 32:
        raise HTTPException(503, '工作流登记服务密钥未配置')
    return {'Authorization': authorization, 'X-Bankpilot-Agent-Key': key}


async def _request(method: str, path: str, authorization: str,
                   *, json: dict | None = None, params: dict | None = None) -> dict:
    headers = _headers(authorization)
    url = _base() + path
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=False) as client:
            response = await client.request(method, url, headers=headers,
                                            json=json, params=params)
    except httpx.HTTPError as exc:
        raise HTTPException(503, 'Java 工作流登记服务无法访问，银行任务未确认；勿重复提交') from exc
    if response.status_code >= 400:
        status = response.status_code
        if status not in (400, 401, 403, 404, 409, 410, 422, 503):
            status = 502
        raise HTTPException(status, '银行工作流登记请求未成功，请查询原会话，勿重复提交')
    try:
        data = response.json()
    except ValueError as exc:
        raise HTTPException(502, '银行工作流登记响应不是合法 JSON') from exc
    if not isinstance(data, dict):
        raise HTTPException(502, '银行工作流登记响应结构不合法')
    return data


def _session(data: dict, *, thread: str | None = None,
             conversation: str | None = None) -> WorkflowSession:
    try:
        result = WorkflowSession.model_validate(data)
    except ValidationError as exc:
        raise HTTPException(502, 'Java 工作流登记返回字段不完整或不合法') from exc
    if thread is not None and str(result.threadId) != _uuid(thread):
        raise HTTPException(502, 'Java 返回工作流编号不匹配')
    if conversation is not None and str(result.conversationId) != _uuid(conversation):
        raise HTTPException(502, 'Java 返回聊天会话不匹配')
    return result


async def register_session(thread_id: str, conversation_id: str,
                           source_request_id: str, message: str,
                           authorization: str) -> WorkflowSession:
    thread = _uuid(thread_id)
    conversation = _uuid(conversation_id)
    data = await _request('POST', '', authorization, json={
        'threadId': thread, 'conversationId': conversation,
        'sourceRequestId': source_request_id, 'userMessageContent': message,
    })
    session = _session(data, thread=thread, conversation=conversation)
    if session.sourceRequestId != source_request_id or session.status != 'RUNNING':
        raise HTTPException(502, '工作流登记返回的消息或初始状态不一致')
    return session


async def get_session(thread_id: str, authorization: str) -> WorkflowSession:
    thread = _uuid(thread_id)
    data = await _request('GET', '/' + thread, authorization)
    return _session(data, thread=thread)


async def list_sessions(conversation_id: str, authorization: str,
                        limit: int = 20) -> list[WorkflowSession]:
    conversation = _uuid(conversation_id)
    if not 1 <= limit <= 100:
        raise HTTPException(422, '工作流列表数量无效')
    data = await _request('GET', '', authorization,
                          params={'conversationId': conversation, 'limit': limit})
    items = data.get('items')
    if not isinstance(items, list) or len(items) > limit:
        raise HTTPException(502, 'Java 工作流列表结构不合法')
    return [_session(item, conversation=conversation) for item in items]


async def update_session_status(thread_id: str, status: Status,
                                authorization: str) -> WorkflowSession:
    thread = _uuid(thread_id)
    if status not in ('RUNNING', 'WAITING', 'COMPLETED', 'REJECTED', 'ENDED', 'NOT_CONFIRMED'):
        raise HTTPException(422, '非法工作流状态')
    data = await _request('PATCH', '/' + thread + '/status', authorization,
                          json={'status': status})
    result = _session(data, thread=thread)
    if result.status != status:
        raise HTTPException(502, 'Java 未确认工作流状态更新')
    return result
