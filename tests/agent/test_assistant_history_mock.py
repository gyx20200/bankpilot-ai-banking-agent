"""Run with: python -m pytest -q tests/agent/test_assistant_history_mock.py"""
import asyncio
import json

import httpx
import pytest

from app import assistant_history as history

CONV = '550e8400-e29b-41d4-a716-446655440000'
USER_REQ = 'request-123456'
AUTH = 'Bearer test-user-token'
SECRET = 'local-only-example-of-long-server-secret-123456'


def _save(**kwargs):
    return asyncio.run(history.save_assistant_reply(
        conversation_id=CONV,
        user_message_request_id=USER_REQ,
        user_message_content='查询我的余额',
        authorization=AUTH,
        reply='模拟银行当时余额 ¥100.00。',
        **kwargs,
    ))


def test_reply_summary_from_verified_balance():
    view = {
        'status': 'COMPLETED',
        'results': {'get_balance': {'status': 'SUCCESS', 'data': {'balance': '123.45'}}},
    }
    text = history.assistant_reply_text(view)
    assert '¥123.45' in text
    assert '当时' in text


def test_deterministic_assistant_request_id():
    a = history.assistant_request_id(CONV, USER_REQ)
    b = history.assistant_request_id(CONV, USER_REQ)
    assert a == b
    assert len(a) <= 64
    assert a != history.assistant_request_id(CONV, 'request-999999')


def test_save_assistant_reply_with_server_only_key(monkeypatch):
    monkeypatch.setenv('BANKPILOT_AGENT_INTERNAL_KEY', SECRET)
    captured = []
    real_client = httpx.AsyncClient

    def handler(request):
        captured.append(request)
        payload = json.loads(request.content)
        assert request.headers['authorization'] == AUTH
        assert request.headers['x-bankpilot-agent-key'] == SECRET
        assert request.url.path.endswith(f'/{CONV}/assistant-messages')
        assert payload['userMessageRequestId'] == USER_REQ
        assert payload['userMessageContent'] == '查询我的余额'
        assert payload['requestId'].startswith('asst-')
        assert 'role' not in payload
        return httpx.Response(201, json={
            'messageId': 99, 'role': 'ASSISTANT',
            'content': payload['content'], 'createdAt': '2026-11-18T12:00:00Z',
        })

    def fake_client(*args, **kwargs):
        return real_client(*args, transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(history.httpx, 'AsyncClient', fake_client)
    assert _save() == '模拟银行当时余额 ¥100.00。'
    assert len(captured) == 1


def test_missing_key_refuses_without_network(monkeypatch):
    monkeypatch.delenv('BANKPILOT_AGENT_INTERNAL_KEY', raising=False)
    with pytest.raises(history.AssistantHistoryError, match='尚未配置'):
        _save()


def test_java_403_never_reports_persisted(monkeypatch):
    monkeypatch.setenv('BANKPILOT_AGENT_INTERNAL_KEY', SECRET)
    real_client = httpx.AsyncClient

    def fake_client(*args, **kwargs):
        return real_client(*args, transport=httpx.MockTransport(
            lambda _: httpx.Response(403, json={'detail': 'forbidden'})
        ), **kwargs)

    monkeypatch.setattr(history.httpx, 'AsyncClient', fake_client)
    with pytest.raises(history.AssistantHistoryError, match='HTTP 403'):
        _save()


def test_timeout_never_reports_persisted(monkeypatch):
    monkeypatch.setenv('BANKPILOT_AGENT_INTERNAL_KEY', SECRET)
    real_client = httpx.AsyncClient

    def raise_timeout(request):
        raise httpx.ReadTimeout('timed out', request=request)

    def fake_client(*args, **kwargs):
        return real_client(*args, transport=httpx.MockTransport(raise_timeout), **kwargs)

    monkeypatch.setattr(history.httpx, 'AsyncClient', fake_client)
    with pytest.raises(history.AssistantHistoryError, match='未确认回复保存'):
        _save()
