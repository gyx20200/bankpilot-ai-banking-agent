"""D5 Java registry contract tests; no MySQL, JWT, or live banking APIs needed."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import asyncio
import pytest
from fastapi import HTTPException

from app import workflow_session_client as mod

THREAD = str(uuid4())
CONV = str(uuid4())
REQUEST = 'd5-test-req-0001'
TOKEN = 'Bearer mock.jwt.test'


def session(**overrides):
    now = datetime.now(timezone.utc)
    result = dict(threadId=THREAD, conversationId=CONV,
                  sourceRequestId=REQUEST, status='RUNNING',
                  createdAt=(now - timedelta(seconds=1)).isoformat(),
                  expiresAt=(now + timedelta(minutes=30)).isoformat())
    result.update(overrides)
    return result


def test_register_and_update(monkeypatch):
    monkeypatch.setenv('BANKPILOT_AGENT_INTERNAL_KEY', 'secure-test-key-' + 'x'*32)
    # Avoid monkeypatching httpx.AsyncClient globally, which can recurse;
    # intercept mod._request instead and verify Java-bound arguments.
    calls=[]
    async def fake_request(method,path,auth,*,json=None,params=None):
        calls.append((method,path,auth,json,params))
        if method == 'PATCH': return session(status='WAITING')
        return session()
    monkeypatch.setattr(mod, '_request', fake_request)
    result=asyncio.run(mod.register_session(THREAD,CONV,REQUEST,'查询余额',TOKEN))
    assert str(result.threadId)==THREAD and result.status=='RUNNING'
    asyncio.run(mod.update_session_status(THREAD,'WAITING',TOKEN))
    assert calls[0][3]['userMessageContent']=='查询余额'
    assert calls[1][0]=='PATCH' and calls[1][3]=={'status':'WAITING'}


def test_invalid_java_record_rejected(monkeypatch):
    async def wrong(*args, **kwargs): return session(threadId=str(uuid4()))
    monkeypatch.setattr(mod,'_request',wrong)
    with pytest.raises(HTTPException) as e:
        asyncio.run(mod.get_session(THREAD,TOKEN))
    assert e.value.status_code == 502


def test_list_cannot_leak_other_conversation(monkeypatch):
    async def wrong(*args, **kwargs):
        return {'items': [session(conversationId=str(uuid4()))]}
    monkeypatch.setattr(mod,'_request',wrong)
    with pytest.raises(HTTPException) as e:
        asyncio.run(mod.list_sessions(CONV,TOKEN))
    assert e.value.status_code == 502


def test_missing_bearer_and_internal_key_fail_closed(monkeypatch):
    monkeypatch.delenv('BANKPILOT_AGENT_INTERNAL_KEY', raising=False)
    with pytest.raises(HTTPException) as e:
        mod._headers(TOKEN)
    assert e.value.status_code == 503
    with pytest.raises(HTTPException) as e:
        mod._headers(None)
    assert e.value.status_code == 401


def test_plaintext_remote_java_rejected(monkeypatch):
    monkeypatch.setenv('BANK_WORKFLOW_SESSION_API_BASE',
                       'http://bank.example.org/api/workflow-sessions')
    with pytest.raises(HTTPException) as e:
        mod._base()
    assert e.value.status_code == 503


def test_finite_expiry_and_aware_timestamps():
    result=mod.WorkflowSession.model_validate(session())
    assert not result.expired
    bad=session(expiresAt='2026-11-20T14:00:00')
    with pytest.raises(Exception):
        mod.WorkflowSession.model_validate(bad)
