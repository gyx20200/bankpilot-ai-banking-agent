"""Day 7 auth edge cases: Java is authoritative, no fabricated login success."""
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app import banking_client as bank
from app.auth_api import router


def test_auth_invalid_java_payload_and_logout_failure(monkeypatch):
    app = FastAPI(); app.include_router(router)
    client = TestClient(app)
    async def invalid_login(method, url, bearer=None, data=None):
        return {'tokenType': 'Bearer', 'expiresInSeconds': 1800} # no token
    monkeypatch.setattr(bank, '_request', invalid_login)
    res = client.post('/api/agent/auth/login', json={'username':'zhangsan','password':'passpass123'})
    assert res.status_code == 502
    async def invalid_logout(method, url, bearer=None, data=None):
        return {'status': 'not_logged_out'}
    monkeypatch.setattr(bank, '_request', invalid_logout)
    assert client.post('/api/agent/auth/logout',headers={'Authorization':'Bearer example'}).status_code == 502


def test_auth_no_password_logs_no_trusting_username_as_identity(monkeypatch):
    app = FastAPI(); app.include_router(router)
    client = TestClient(app)
    async def rejected(method, url, bearer=None, data=None):
        raise bank.BankError('账号或密码错误。', 401)
    monkeypatch.setattr(bank, '_request', rejected)
    res = client.post('/api/agent/auth/login',json={'username':'zhangsan','password':'secret-pass-123'})
    assert res.status_code == 401
    assert 'secret-pass-123' not in res.text
    assert client.post('/api/agent/auth/logout').status_code == 401
    assert client.get('/api/agent/auth/me').status_code == 401
