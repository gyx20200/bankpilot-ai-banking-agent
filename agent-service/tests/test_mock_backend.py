from fastapi.testclient import TestClient
import mock_backend

client = TestClient(mock_backend.app)


def test_mock_requires_token_and_never_debits_balance():
    before = client.get('/api/demo/balance').json()['balance']
    data = {'payeeId': 1, 'amount': '200.00', 'requestId': 'mock-test-001', 'remark': 'AA'}
    assert client.post('/api/transfers/prepare', json=data).status_code == 401
    h = {'Authorization': 'Bearer mock-day3-token'}
    r = client.post('/api/transfers/prepare', json=data, headers=h)
    assert r.status_code == 200 and r.json()['status'] == 'PENDING_APPROVAL'
    assert client.post('/api/transfers/prepare', json=data, headers=h).json()['orderId'] == r.json()['orderId']
    assert client.get('/api/demo/balance').json()['balance'] == before
    different = dict(data, amount='300.00')
    assert client.post('/api/transfers/prepare', json=different, headers=h).status_code == 409


def test_mock_exposes_no_execution_endpoint():
    assert client.post('/api/transfers/execute', json={}).status_code == 404
