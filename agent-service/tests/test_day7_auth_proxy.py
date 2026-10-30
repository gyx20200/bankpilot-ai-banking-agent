"""Day 7 auth proxy contract tests; no Java service required."""
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.auth_api import router
from app import banking_client as bank


def test_auth_proxy_contract(monkeypatch):
    requests = []

    async def fake_request(method, url, bearer=None, data=None):
        requests.append((method, url, bearer, data))
        if url.endswith('/register'):
            return {'userId': 3, 'status': 'REGISTERED'}
        if url.endswith('/login'):
            return {'token': 'fake-only-for-test', 'tokenType': 'Bearer',
                    'expiresInSeconds': 1800, 'displayName': '张三'}
        if url.endswith('/me'):
            return {'userId': 3, 'username': 'zhangsan',
                    'displayName': '张三', 'phoneMasked': '138****8000'}
        if url.endswith('/logout'):
            return {'status': 'logged_out'}
        raise AssertionError(url)

    monkeypatch.setattr(bank, '_request', fake_request)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    res = client.post('/api/agent/auth/register', json={
        'username': 'zhangsan', 'password': 'TestPassword123!',
        'fullName': '张三', 'phone': '13800138000',
    })
    assert res.status_code == 201
    assert res.json() == {'userId': 3, 'status': 'REGISTERED'}
    assert requests[0][3]['password'] == 'TestPassword123!'

    res = client.post('/api/agent/auth/login', json={
        'username': 'zhangsan', 'password': 'TestPassword123!',
    })
    assert res.status_code == 200
    assert res.json()['tokenType'] == 'Bearer'

    res = client.get('/api/agent/auth/me',
                     headers={'Authorization': 'Bearer fake-only-for-test'})
    assert res.status_code == 200
    assert res.json()['userId'] == 3
    assert requests[2][2] == 'Bearer fake-only-for-test'

    res = client.post('/api/agent/auth/logout',
                      headers={'Authorization': 'Bearer fake-only-for-test'})
    assert res.status_code == 200
    assert res.json()['status'] == 'logged_out'
    assert requests[3][2] == 'Bearer fake-only-for-test'

    assert client.get('/api/agent/auth/me').status_code == 401
    assert client.post('/api/agent/auth/register', json={
        'username': 'x', 'password': '123', 'fullName': '张三', 'phone': 'wrong',
    }).status_code == 422
    assert len(requests) == 4
