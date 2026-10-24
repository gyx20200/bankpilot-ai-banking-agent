from fastapi.testclient import TestClient
import main

client = TestClient(main.app)


def test_health():
    assert client.get('/health').json()['status'] == 'ok'


def test_unsupported():
    result = client.post('/api/agent/chat', json={'message': '你好'}).json()
    assert result['intent'] == 'unsupported'
    assert result['source'] == 'none'


def test_balance(monkeypatch):
    async def fake_balance():
        return {'userName': '张小明', 'accountNoMasked': '****6688', 'balance': '100.05'}
    monkeypatch.setattr(main, 'get_balance', fake_balance)
    response = client.post('/api/agent/chat', json={'message': '我的余额是多少'})
    assert response.status_code == 200
    assert response.json()['intent'] == 'balance'
    assert '100.05' in response.json()['reply']


def test_backend_failure(monkeypatch):
    async def broken():
        raise main.BankingServiceError('后端不可用')
    monkeypatch.setattr(main, 'get_transactions', broken)
    response = client.post('/api/agent/chat', json={'message': '交易记录'})
    assert response.status_code == 502
    assert '后端不可用' in response.json()['detail']


def test_invalid_message():
    assert client.post('/api/agent/chat', json={'message': ''}).status_code == 422
