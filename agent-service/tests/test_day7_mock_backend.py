"""Isolated functional checks against the opt-in RAM-only Day7 mock bank."""
import os
os.environ['BANKPILOT_STAGE1_MOCK'] = '1'

import pytest
from fastapi.testclient import TestClient
import mock_day7_backend as mock


@pytest.fixture
def bank():
    with mock._lock:
        for table in (mock._users, mock._username_to_id, mock._phone_to_id,
                      mock._tokens, mock._accounts, mock._transactions,
                      mock._subscriptions, mock._orders, mock._transfer_request_keys,
                      mock._cancellations, mock._cancel_request_keys):
            table.clear()
    with TestClient(mock.app) as client:
        yield client


def register(client, username, fullname, phone):
    return client.post('/api/auth/register', json={
        'username': username, 'fullName': fullname, 'phone': phone,
        'password': 'TestBank_987654',
    })


def login(client, username):
    res = client.post('/api/auth/login', json={'username': username, 'password': 'TestBank_987654'})
    assert res.status_code == 200, res.text
    return {'Authorization': 'Bearer ' + res.json()['token']}


def setup_two(bank):
    assert register(bank, 'zhangsan', '张三', '13800138000').status_code == 201
    assert register(bank, 'lisi', '李四', '13900139000').status_code == 201
    return login(bank, 'zhangsan'), login(bank, 'lisi')


def test_register_login_logout_relogin_and_duplicate(bank):
    one = register(bank, 'zhangsan', '张三', '13800138000')
    assert one.status_code == 201 and one.json() == {'userId': 1, 'status': 'REGISTERED'}
    assert bank.get('/api/auth/me').status_code == 401
    assert register(bank, 'zhangsan', '张三', '13900139000').status_code == 409
    assert register(bank, 'zhangsan2', '张三', '13800138000').status_code == 409
    assert bank.post('/api/auth/login', json={'username': 'zhangsan', 'password': 'bad'}).status_code == 401
    h = login(bank, 'zhangsan')
    assert bank.get('/api/auth/me', headers=h).json()['userId'] == 1
    assert bank.post('/api/auth/logout', headers=h).json()['status'] == 'logged_out'
    assert bank.get('/api/auth/me', headers=h).status_code == 401
    h2 = login(bank, 'zhangsan')
    assert h != h2
    assert bank.get('/api/auth/me', headers=h2).json()['userId'] == 1


def test_user_isolation_for_balance_payees_subscriptions_analytics(bank):
    z, l = setup_two(bank)
    assert bank.get('/api/demo/balance').status_code == 401
    assert bank.get('/api/demo/balance', headers=z).json()['userName'] == '张三'
    assert bank.get('/api/demo/balance', headers=l).json()['userName'] == '李四'
    assert bank.get('/api/demo/balance', headers=l).json()['balance'] == '10000.00'
    assert bank.get('/api/demo/payees', headers=z).json()[0]['payeeName'] == '李四'
    assert all(x['payeeName'] != '张三' for x in bank.get('/api/demo/payees', headers=z).json())
    first_sub = bank.get('/api/demo/subscriptions', headers=z).json()[0]['id']
    second_sub = bank.get('/api/demo/subscriptions', headers=l).json()[0]['id']
    assert first_sub != second_sub
    month = bank.get('/api/demo/analytics/monthly?month=2026-10', headers=z)
    assert month.status_code == 200 and month.json()['totalExpense'] == '0.00'
    assert bank.get('/api/demo/transactions', headers=z).json() == []


def test_transfer_is_bilateral_and_ownership_protected(bank):
    z, l = setup_two(bank)
    prep = bank.post('/api/transfers/prepare', headers=z,
                     json={'payeeId': 2, 'amount': '200', 'requestId': 'transfer-0001'})
    assert prep.status_code == 200, prep.text
    oid = prep.json()['orderId']
    assert prep.json()['riskLevel'] == 'YELLOW'
    assert bank.get(f'/api/transfers/{oid}', headers=l).status_code == 404
    assert bank.post(f'/api/transfers/{oid}/authorize', headers=l,
                     json={'confirmation': True, 'requestId': 'authorize-0001'}).status_code == 404
    assert bank.get('/api/demo/balance', headers=z).json()['balance'] == '10000.00'
    auth = bank.post(f'/api/transfers/{oid}/authorize', headers=z,
                     json={'confirmation': True, 'requestId': 'authorize-0001'})
    assert auth.status_code == 200 and auth.json()['status'] == 'AUTHORIZED'
    done = bank.post(f'/api/transfers/{oid}/execute', headers=z,
                     json={'requestId': 'execute-0001'})
    assert done.status_code == 200 and done.json()['status'] == 'SUCCESS'
    assert bank.get('/api/demo/balance', headers=z).json()['balance'] == '9800.00'
    assert bank.get('/api/demo/balance', headers=l).json()['balance'] == '10200.00'
    assert bank.get('/api/demo/transactions', headers=z).json()[0]['direction'] == 'OUT'
    assert bank.get('/api/demo/transactions', headers=l).json()[0]['direction'] == 'IN'
    assert bank.post(f'/api/transfers/{oid}/execute', headers=z,
                     json={'requestId': 'execute-0001'}).status_code == 200
    assert bank.get('/api/demo/balance', headers=l).json()['balance'] == '10200.00'
    other = bank.post('/api/transfers/prepare', headers=z,
                      json={'payeeId': 2, 'amount': '250', 'requestId': 'transfer-0001'})
    assert other.status_code == 409


def test_red_transfer_requires_otp_and_request(bank):
    z, l = setup_two(bank)
    prep = bank.post('/api/transfers/prepare', headers=z,
                     json={'payeeId': 2, 'amount': '1500', 'requestId': 'transfer-red01'})
    assert prep.json()['riskLevel'] == 'RED'
    oid = prep.json()['orderId']
    base = f'/api/transfers/{oid}'
    assert bank.post(base+'/authorize', headers=z,
                     json={'confirmation': True, 'otpCode': '246810', 'requestId': 'auth-red-0001'}).status_code == 403
    assert bank.post(base+'/otp/request', headers=l).status_code == 404
    issued = bank.post(base+'/otp/request', headers=z)
    assert issued.status_code == 200 and issued.json()['expiresInSeconds'] == 120
    assert bank.post(base+'/authorize', headers=z,
                     json={'confirmation': True, 'otpCode': '111111', 'requestId': 'auth-red-0001'}).status_code == 403
    assert bank.post(base+'/authorize', headers=z,
                     json={'confirmation': True, 'otpCode': '246810', 'requestId': 'auth-red-0001'}).status_code == 200
    assert bank.post(base+'/execute', headers=z, json={'requestId': 'exec-red-0001'}).status_code == 200
    assert bank.get('/api/demo/balance', headers=l).json()['balance'] == '11500.00'


def test_subscription_cancellation_is_owned_and_stateful(bank):
    z, l = setup_two(bank)
    sub_id = bank.get('/api/demo/subscriptions', headers=z).json()[0]['id']
    prep = bank.post('/api/subscription-cancellations/prepare', headers=z,
                     json={'subscriptionId': sub_id, 'requestId': 'sub-cancel-0001'})
    assert prep.status_code == 200 and prep.json()['status'] == 'PENDING_APPROVAL'
    oid = prep.json()['orderId']
    assert bank.get(f'/api/subscription-cancellations/{oid}', headers=l).status_code == 404
    assert bank.post('/api/subscription-cancellations/prepare', headers=l,
                     json={'subscriptionId': sub_id, 'requestId': 'sub-cancel-0002'}).status_code == 404
    assert bank.post(f'/api/subscription-cancellations/{oid}/authorize', headers=z,
                     json={'confirmed': True, 'requestId': 'sub-auth-00001'}).status_code == 200
    finished = bank.post(f'/api/subscription-cancellations/{oid}/execute', headers=z,
                         json={'requestId': 'sub-exec-00001'})
    assert finished.status_code == 200 and finished.json()['subscriptionStatus'] == 'CANCELLED'
    assert bank.get('/api/demo/subscriptions', headers=l).json()[0]['status'] == 'ACTIVE'
    assert bank.post(f'/api/subscription-cancellations/{oid}/execute', headers=z,
                     json={'requestId': 'sub-exec-00001'}).status_code == 200


def test_logout_revocation_blocks_existing_order(bank):
    z, l = setup_two(bank)
    oid = bank.post('/api/transfers/prepare', headers=z,
                    json={'payeeId': 2, 'amount': '100', 'requestId': 'transfer-0002'}).json()['orderId']
    assert bank.post('/api/auth/logout', headers=z).status_code == 200
    assert bank.get(f'/api/transfers/{oid}', headers=z).status_code == 401
    new_z = login(bank, 'zhangsan')
    assert bank.get(f'/api/transfers/{oid}', headers=new_z).status_code == 200
    assert bank.get(f'/api/transfers/{oid}', headers=l).status_code == 404


def test_expired_token_and_blank_name(bank):
    assert bank.post('/api/auth/register', json={
        'username': 'zhangsan', 'fullName': '   ', 'phone': '13800138000',
        'password': 'TestBank_987654',
    }).status_code == 422
    assert register(bank, 'zhangsan', '张三', '13800138000').status_code == 201
    h = login(bank, 'zhangsan')
    with mock._lock:
        mock._tokens[h['Authorization'][7:]]['expires'] = mock._now() - mock.timedelta(seconds=1)
    assert bank.get('/api/auth/me', headers=h).status_code == 401
    assert bank.get('/api/demo/subscriptions', headers=h).status_code == 401
