"""Stage 1 identity regression without requiring a running Java/LLM/LangGraph.

The real dynamic graph is replaced ONLY inside this unit test. This verifies
FastAPI authorization guards; it is not an end-to-end graph regression.
"""
import importlib.util
import sys
import types
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app import banking_client as bank


def _load_workflow_api(monkeypatch):
    # isolate native LangGraph imports; test only the changed HTTP owner checks
    stub_langgraph = types.ModuleType('langgraph')
    stub_types = types.ModuleType('langgraph.types')
    stub_types.Command = lambda **kwargs: kwargs
    stub_graph = types.ModuleType('app.graph.dynamic_cancellation_workflow')

    class DummyGraph:
        async def ainvoke(self, *args, **kwargs):
            return {
                '__interrupt__': [{'value': 'waiting'}],
                'status': 'WAITING_APPROVAL', 'plan': {'tasks': []},
            }

        async def aget_state(self, config):
            return types.SimpleNamespace(values={}, next=('wait_for_approval',))

    stub_graph.dynamic_graph = DummyGraph()
    monkeypatch.setitem(sys.modules, 'langgraph', stub_langgraph)
    monkeypatch.setitem(sys.modules, 'langgraph.types', stub_types)
    monkeypatch.setitem(sys.modules, 'app.graph.dynamic_cancellation_workflow', stub_graph)
    path = Path(__file__).resolve().parents[3] / 'agent-service' / 'app' / 'workflow_api.py'
    spec = importlib.util.spec_from_file_location('bankpilot_day7_workflow_test_module', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_workflow_userid_ownership_and_revocation(monkeypatch):
    workflow = _load_workflow_api(monkeypatch)
    identities = {'Bearer token-A': 1, 'Bearer token-B': 1, 'Bearer token-C': 2}

    async def java_me(bearer):
        if bearer not in identities:
            raise bank.BankError('登录状态无效，请重新登录。', 401)
        return {'userId': identities[bearer], 'displayName': '张小明' if identities[bearer] == 1 else '张三'}

    monkeypatch.setattr(workflow.bank, 'current_user', java_me)
    app = FastAPI()
    app.include_router(workflow.router)
    client = TestClient(app)

    assert client.post('/api/agent/workflows/dynamic/start', json={'message': '查余额'}).status_code == 401
    started = client.post('/api/agent/workflows/dynamic/start', json={'message': '取消订阅'},
                          headers={'Authorization': 'Bearer token-A'})
    assert started.status_code == 200
    tid = started.json()['threadId']
    assert workflow._sessions[tid]['ownerUserId'] == 1
    assert 'owner' not in workflow._sessions[tid]

    # Same verified bank user can inspect an old thread with a NEW login token.
    workflow._sessions[tid]['finished'] = True
    assert client.get(f'/api/agent/workflows/dynamic/{tid}',
                      headers={'Authorization': 'Bearer token-B'}).status_code == 200
    # Different bank user must never inspect or operate the saved workflow.
    assert client.get(f'/api/agent/workflows/dynamic/{tid}',
                      headers={'Authorization': 'Bearer token-C'}).status_code == 403
    assert client.post('/api/agent/workflows/dynamic/resume', json={'threadId': tid, 'approved': True},
                       headers={'Authorization': 'Bearer token-C'}).status_code == 403
    assert client.post('/api/agent/workflows/dynamic/transfer/otp/request', json={'threadId': tid},
                       headers={'Authorization': 'Bearer token-C'}).status_code == 403
    # Revoked/expired login must be rejected even when threadId is known.
    del identities['Bearer token-A']
    assert client.get(f'/api/agent/workflows/dynamic/{tid}',
                      headers={'Authorization': 'Bearer token-A'}).status_code == 401


def test_workflow_does_not_trust_fake_user_id(monkeypatch):
    workflow = _load_workflow_api(monkeypatch)
    async def invalid_principal(token):
        return {'userId': '1', 'displayName': 'not trusted'}
    monkeypatch.setattr(workflow.bank, 'current_user', invalid_principal)
    app = FastAPI(); app.include_router(workflow.router)
    res = TestClient(app).post('/api/agent/workflows/dynamic/start', json={'message': '查余额'},
                               headers={'Authorization': 'Bearer any'})
    assert res.status_code == 502
