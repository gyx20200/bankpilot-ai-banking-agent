"""Read-only security regressions for D5; no bank writes or DeepSeek calls."""
import asyncio
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from app import workflow_api as api

THREAD = str(uuid4())
CONVERSATION = str(uuid4())
TOKEN = 'Bearer d5-test-only'


def owned(status='WAITING'):
    return SimpleNamespace(
        threadId=THREAD, conversationId=CONVERSATION,
        status=status, expired=False,
    )


def test_recovery_reads_snapshot_without_advancing_graph(monkeypatch):
    async def user(_): return 17
    async def session(thread, _):
        assert thread == THREAD
        return owned()
    async def bank_get(order, _):
        assert order == '1001'
        return dict(orderId='1001', payeeName='李四', accountMasked='****1234',
                    amount='10.00', remark='D5测试', riskLevel='YELLOW',
                    status='PENDING_APPROVAL')
    async def no_graph_resume(*args, **kwargs):
        raise AssertionError('recovery must never invoke graph')
    state=dict(
        status='RUNNING',
        transferOrder=dict(orderId='1001'),
        transferCandidate=dict(payeeName='李四', accountMasked='****1234',
                               amount='10.00', remark='D5测试'),
    )
    async def get_state(config):
        assert config['configurable']['thread_id'] == THREAD
        return SimpleNamespace(values=state, next=('wait_for_transfer_approval',), tasks=(1,))
    monkeypatch.setattr(api, '_authenticated_user', user)
    monkeypatch.setattr(api, 'persistent_enabled', lambda: True)
    monkeypatch.setattr(api, 'get_session', session)
    monkeypatch.setattr(api.bank, 'get_order', bank_get)
    monkeypatch.setattr(api, 'dynamic_graph', SimpleNamespace(
        aget_state=get_state, ainvoke=no_graph_resume,
    ))
    view=asyncio.run(api.workflow_recovery(UUID(THREAD), TOKEN))
    assert view['checkpointFound'] is True
    assert view['orderId'] == '1001'
    assert view['bankOrderStatus'] == 'PENDING_APPROVAL'
    assert view['nextNodes'] == ['wait_for_transfer_approval']
    assert view['canResume'] is False and view['readOnly'] is True


def test_java_foreign_ownership_blocks_checkpoint_read(monkeypatch):
    async def user(_): return 22
    async def session(*args): raise HTTPException(404, 'not found')
    async def unauthorized_get_state(*args):
        raise AssertionError('do not read sqlite before Java identity check')
    monkeypatch.setattr(api, '_authenticated_user', user)
    monkeypatch.setattr(api, 'persistent_enabled', lambda: True)
    monkeypatch.setattr(api, 'get_session', session)
    monkeypatch.setattr(api, 'dynamic_graph', SimpleNamespace(aget_state=unauthorized_get_state))
    with pytest.raises(HTTPException) as e:
        asyncio.run(api.workflow_recovery(UUID(THREAD), TOKEN))
    assert e.value.status_code == 404


def test_after_restart_no_mutation_even_with_checkpoint(monkeypatch):
    async def user(_): return 22
    async def session(*args): return owned()
    monkeypatch.setattr(api, '_authenticated_user', user)
    monkeypatch.setattr(api, 'persistent_enabled', lambda: True)
    monkeypatch.setattr(api, 'get_session', session)
    monkeypatch.setattr(api, '_sessions', {})
    with pytest.raises(HTTPException) as e:
        asyncio.run(api._owner(THREAD, TOKEN))
    assert e.value.status_code == 409


def test_duplicate_registration_prevents_graph_execution(monkeypatch):
    async def user(_): return 22
    async def load_planner_context(**kwargs): return None
    async def register_session(*args): raise HTTPException(409, 'duplicate')
    async def should_never_invoke(*args, **kwargs):
        raise AssertionError('no graph invocation after duplicate')
    monkeypatch.setattr(api, '_authenticated_user', user)
    monkeypatch.setattr(api, 'load_planner_context', load_planner_context)
    monkeypatch.setattr(api, 'persistent_enabled', lambda: True)
    monkeypatch.setattr(api, 'register_session', register_session)
    monkeypatch.setattr(api, '_invoke_graph', should_never_invoke)
    body=api.StartBody(message='查询余额', conversationId=UUID(CONVERSATION),
                       userMessageRequestId='d5-unique-test-001')
    with pytest.raises(HTTPException) as e:
        asyncio.run(api.dynamic_start(body, TOKEN))
    assert e.value.status_code == 409
