"""Stage 2 security and mock integration checks; no external Java or model."""
import asyncio
import os

os.environ['BANKPILOT_STAGE1_MOCK'] = '1'

import pytest
from fastapi.testclient import TestClient

from app import banking_client as bank
from app.graph.task_planner import validate_plan
from app.graph.transfer_prepare import prepare_verified_transfer
import mock_day7_backend as mock
from datetime import date

TODAY = date(2026, 10, 30)


@pytest.fixture
def client():
    with mock._lock:
        for t in (mock._users, mock._username_to_id, mock._phone_to_id,
                  mock._tokens, mock._accounts, mock._transactions, mock._subscriptions,
                  mock._orders, mock._transfer_request_keys, mock._cancellations,
                  mock._cancel_request_keys):
            t.clear()
    with TestClient(mock.app) as c:
        yield c


def register(client, username, name, phone):
    r = client.post('/api/auth/register', json={
        'username': username, 'fullName': name, 'phone': phone, 'password': 'BankPilotTest_9876'})
    assert r.status_code == 201, r.text
    r = client.post('/api/auth/login', json={'username': username, 'password': 'BankPilotTest_9876'})
    assert r.status_code == 200, r.text
    return {'Authorization': 'Bearer ' + r.json()['token']}


def test_phone_only_and_remark_planner():
    raw = {'tasks': [{'type': 'transfer_prepare', 'payee_phone': '13800138000',
                     'amount': '200', 'remark': '周末聚餐'}]}
    result = validate_plan(raw, TODAY, '给13800138000转200元，备注周末聚餐')
    assert result.status == 'ready'
    task = result.tasks[0]
    assert task.payee_phone == '13800138000' and task.payee_name is None
    assert task.amount == '200.00' and task.remark == '周末聚餐'
    assert result.execution_order == ['get_payees', 'transfer_prepare']


@pytest.mark.parametrize('raw,phrase', [
    ({'payee_phone': '13800138001', 'amount': '200'}, '给13800138000转200元'),
    ({'payee_phone': '13800138000', 'amount': '200', 'remark': '不存在的理由'}, '给13800138000转200元'),
    ({'payee_name': '张三', 'amount': '200', 'remark': 'a'*81}, '给张三转200元，备注'+'a'*81),
    ({'payee_phone': '00000000000', 'amount': '200'}, '给00000000000转200元'),
    ({'amount': '200'}, '转200元'),
    ({'payee_name': '张三', 'amount': '200', 'remark': '跨行\n转账'}, '给张三转200元，备注跨行\n转账'),
])
def test_planner_fails_closed_for_spoofed_recipient_or_remark(raw, phrase):
    result = validate_plan({'tasks': [{'type': 'transfer_prepare', **raw}]}, TODAY, phrase)
    assert result.status == 'needs_clarification'


def test_directory_duplicate_and_phone_self_protection(client):
    z = register(client, 'payer', '张小明', '13700137000')
    z1 = register(client, 'receiver1', '张三', '13800138000')
    z2 = register(client, 'receiver2', '张三', '13900139000')
    assert client.get('/api/transfers/recipients/search?name=张三').status_code == 401
    found = client.get('/api/transfers/recipients/search?name=张三', headers=z)
    assert found.status_code == 200
    assert [x['recipientId'] for x in found.json()] == [2, 3]
    unique = client.get('/api/transfers/recipients/search?phone=13900139000', headers=z)
    assert len(unique.json()) == 1 and unique.json()[0]['recipientId'] == 3
    both = client.get('/api/transfers/recipients/search?name=张三&phone=13800138000', headers=z)
    assert len(both.json()) == 1 and both.json()[0]['recipientId'] == 2
    mismatch = client.get('/api/transfers/recipients/search?name=张三&phone=13700137000', headers=z)
    assert mismatch.json() == []
    assert client.get('/api/transfers/recipients/search?phone=13700137000', headers=z).json() == []
    assert client.post('/api/transfers/recipients/confirm', headers=z,
                       json={'recipientId': 1}).status_code == 404
    assert client.post('/api/transfers/recipients/confirm', headers=z,
                       json={'recipientId': 3}).json()['id'] == 3
    assert client.post('/api/transfers/recipients/confirm', headers=z1,
                       json={'recipientId': 3}).json()['id'] == 3


def test_remark_bilateral_ledger_and_no_duplicate_debit(client):
    z = register(client, 'payer', '张小明', '13700137000')
    l = register(client, 'receiver', '李四', '13800138000')
    target = client.get('/api/transfers/recipients/search?phone=13800138000', headers=z).json()[0]
    bound = client.post('/api/transfers/recipients/confirm', headers=z,
                        json={'recipientId': target['recipientId']}).json()
    order = client.post('/api/transfers/prepare', headers=z,
                        json={'payeeId': bound['id'], 'amount': '200.00',
                              'remark': '晚餐AA', 'requestId': 'stage2-req-001'}).json()
    assert order['remark'] == '晚餐AA' and order['payeeName'] == '李四'
    oid = order['orderId']
    assert client.post(f'/api/transfers/{oid}/authorize', headers=z,
                       json={'confirmation': True, 'requestId': 'stage2-auth-01'}).status_code == 200
    assert client.post(f'/api/transfers/{oid}/execute', headers=z,
                       json={'requestId': 'stage2-exec-01'}).json()['status'] == 'SUCCESS'
    assert client.post(f'/api/transfers/{oid}/execute', headers=z,
                       json={'requestId': 'stage2-exec-01'}).json()['status'] == 'SUCCESS'
    assert client.get('/api/demo/balance', headers=z).json()['balance'] == '9800.00'
    assert client.get('/api/demo/balance', headers=l).json()['balance'] == '10200.00'
    for headers in (z, l):
        records = client.get('/api/demo/transactions', headers=headers).json()
        assert len(records) == 1 and records[0]['remark'] == '晚餐AA'


def test_prepared_remark_response_mismatch_blocks(monkeypatch):
    async def fake(*args, **kwargs):
        return {'orderId': 'MOCK-TF-1', 'payeeName': '李四',
                'accountMasked': '****6602', 'amount': '200.00',
                'remark': '其他备注', 'riskLevel': 'YELLOW', 'status': 'PENDING_APPROVAL'}
    monkeypatch.setattr(bank, 'prepare_transfer', fake)
    candidate = {'id': 2, 'payeeName': '李四', 'accountMasked': '****6602',
                 'amount': '200.00', 'remark': '用户原文备注'}
    with pytest.raises(bank.BankError, match='不一致'):
        asyncio.run(prepare_verified_transfer(candidate, 'request-001', 'Bearer xyz'))


def test_bank_directory_validates_response_and_confirms(monkeypatch):
    calls = []
    async def fake_request(method, url, bearer=None, data=None):
        calls.append((method, url, bearer, data))
        if method == 'GET':
            return [{'recipientId': 4, 'payeeName': '李四', 'accountMasked': '****7711'}]
        return {'id': 9, 'payeeName': '李四', 'payeeAccountMasked': '****7711'}
    monkeypatch.setattr(bank, '_request', fake_request)
    found = asyncio.run(bank.search_registered_recipients('Bearer xyz', phone='13800138000'))
    assert found[0]['recipientId'] == 4
    bound = asyncio.run(bank.confirm_registered_recipient(4, 'Bearer xyz'))
    assert bound['id'] == 9
    assert 'phone=13800138000' in calls[0][1]
    assert calls[1][3] == {'recipientId': 4}


def test_bank_directory_does_not_accept_spoofed_bank_fields(monkeypatch):
    async def invalid(*args, **kwargs):
        return [{'recipientId': True, 'payeeName': '张三', 'accountMasked': '****1111'}]
    monkeypatch.setattr(bank, '_request', invalid)
    with pytest.raises(bank.BankError):
        asyncio.run(bank.search_registered_recipients('Bearer xyz', name='张三'))
