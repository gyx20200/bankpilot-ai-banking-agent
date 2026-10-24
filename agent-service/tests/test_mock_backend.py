import pytest
from fastapi.testclient import TestClient
import mock_backend as bank

client = TestClient(bank.app)
AUTH = {'Authorization': 'Bearer mock-day4-token'}


@pytest.fixture(autouse=True)
def reset_bank():
    bank.reset_demo()


def prep(amount, req='prep-request-001', payee=1):
    return client.post('/api/transfers/prepare', headers=AUTH, json={'payeeId':payee,'amount':amount,'remark':'测试','requestId':req})


def authorize(oid, otp=None, confirmation=True):
    return client.post(f'/api/transfers/{oid}/authorize', headers=AUTH, json={'confirmation':confirmation,'otpCode':otp,'requestId':'approval-req-001'})


def execute(oid):
    return client.post(f'/api/transfers/{oid}/execute', headers=AUTH, json={'requestId':'exec-request-001'})


def cancel(oid):
    return client.post(f'/api/transfers/{oid}/cancel', headers=AUTH, json={'requestId':'cancel-request-001'})


def test_no_auth_is_rejected():
    assert client.post('/api/transfers/prepare', json={'payeeId':1,'amount':'200.00','requestId':'prep-request-001'}).status_code == 401


def test_yellow_requires_authorize_execute_and_idempotent():
    initial = client.get('/api/demo/balance').json()['balance']
    order = prep('200.00').json()
    assert order['riskLevel'] == 'YELLOW' and order['status'] == 'PENDING_APPROVAL'
    assert execute(order['orderId']).status_code == 409
    assert authorize(order['orderId'], confirmation=False).status_code == 400
    assert authorize(order['orderId']).json()['status'] == 'AUTHORIZED'
    assert client.get('/api/demo/balance').json()['balance'] == initial
    finished = execute(order['orderId'])
    assert finished.status_code == 200 and finished.json()['status'] == 'SUCCESS'
    assert finished.json()['balanceAfter'] == '12380.50'
    assert execute(order['orderId']).json()['transferId'] == finished.json()['transferId']
    assert client.get('/api/demo/balance').json()['balance'] == '12380.50'
    assert len(client.get('/api/demo/transactions').json()) == 5
    assert cancel(order['orderId']).status_code == 409


def test_cancel_before_execution():
    order = prep('200.00').json()
    assert cancel(order['orderId']).json()['status'] == 'CANCELLED'
    assert cancel(order['orderId']).json()['status'] == 'CANCELLED'
    assert execute(order['orderId']).status_code == 409
    assert client.get('/api/demo/balance').json()['balance'] == '12580.50'


def test_red_requires_otp_and_locks_on_third_failure():
    order = prep('1500.00').json()
    oid = order['orderId']
    assert order['riskLevel'] == 'RED'
    assert authorize(oid).status_code == 403
    assert authorize(oid, '000000').status_code == 403
    assert authorize(oid, '111111').status_code == 403
    assert client.get(f'/api/transfers/{oid}', headers=AUTH).json()['status'] == 'LOCKED'
    assert authorize(oid, '246810').status_code == 409
    assert execute(oid).status_code == 409


def test_red_otp_happy_path():
    oid = prep('1500').json()['orderId']
    assert authorize(oid,'246810').json()['status'] == 'AUTHORIZED'
    assert execute(oid).json()['balanceAfter'] == '11080.50'


def test_daily_cumulative_escalation():
    a = prep('800.00', 'prep-request-first').json()
    b = prep('500.00', 'prep-request-second').json()
    assert a['riskLevel'] == 'YELLOW'
    assert b['riskLevel'] == 'RED'
    assert authorize(a['orderId']).status_code == 403  # escalated to red because in-flight b
    assert authorize(a['orderId'],'246810').json()['riskLevel'] == 'RED'
    assert execute(a['orderId']).status_code == 200


def test_idempotency_key_mismatch_rejected():
    one=prep('200.00').json()
    assert prep('200.00').json()['orderId'] == one['orderId']
    assert prep('250.00').status_code == 409


def test_unauthorized_order_status():
    order=prep('200').json()
    assert client.get(f'/api/transfers/{order["orderId"]}').status_code == 401
    assert client.get('/api/transfers/does-not-exist',headers=AUTH).status_code == 404
