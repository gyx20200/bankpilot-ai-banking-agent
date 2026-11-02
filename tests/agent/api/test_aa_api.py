"""Real FastAPI AA proxy request/response flow, patched to an in-process Mock bank."""
import os
from urllib.parse import urlsplit
from uuid import uuid4
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

os.environ['BANKPILOT_STAGE1_MOCK'] = '1'
from app import banking_client as bank
from app.aa_api import router
import mock_day7_backend as mock

agent = FastAPI()
agent.include_router(router)
proxy = TestClient(agent)
mock_client = TestClient(mock.app)


def _login(name, phone):
    username = 'proxy'+uuid4().hex[:9]
    reg = mock_client.post('/api/auth/register', json={
        'username': username, 'password': 'safePassword88', 'fullName': name, 'phone': phone})
    assert reg.status_code == 201, reg.text
    login = mock_client.post('/api/auth/login', json={'username': username, 'password': 'safePassword88'})
    assert login.status_code == 200
    return {'Authorization':'Bearer '+login.json()['token']}


@pytest.fixture
def stub_bank(monkeypatch):
    async def fake_request(method, url, bearer=None, data=None):
        path = urlsplit(url).path
        headers = {'Authorization':bearer} if bearer else {}
        response = mock_client.request(method, path, headers=headers, json=data)
        if response.status_code >= 400:
            raise bank.BankError('模拟银行拒绝该操作。', response.status_code)
        return response.json()
    monkeypatch.setattr(bank, '_request', fake_request)


def test_aa_proxy_auth_and_real_payment_flow(stub_bank):
    suffix=uuid4().hex[:6]
    a=_login('发起人'+suffix, '137'+str(int(uuid4().hex[:8],16)%100000000).zfill(8))
    b=_login('付款人'+suffix, '138'+str(int(uuid4().hex[:8],16)%100000000).zfill(8))
    draft=mock_client.post('/api/aa/prepare',headers=a,json={
        'participants':['付款人'+suffix], 'amount':'120.00',
        'splitMode':'total_with_self', 'reason':'聚餐', 'requestId':uuid4().hex}).json()
    mock_client.post('/api/aa/'+draft['collectionId']+'/publish',headers=a,json={'requestId':uuid4().hex})
    assert proxy.get('/api/agent/aa/inbox').status_code==401
    assert proxy.get('/api/agent/aa/inbox',headers=a).json()==[]
    inbox=proxy.get('/api/agent/aa/inbox',headers=b)
    assert inbox.status_code==200 and len(inbox.json())==1
    item=inbox.json()[0]
    order=proxy.post('/api/agent/aa/items/'+item['itemId']+'/payment/prepare',headers=b,
                     json={'requestId':uuid4().hex})
    assert order.status_code==200 and order.json()['riskLevel']=='YELLOW'
    paid=proxy.post('/api/agent/aa/items/'+item['itemId']+'/payment/confirm',headers=b,
                    json={'requestId':uuid4().hex, 'confirmed':True})
    assert paid.status_code==200 and paid.json()['status']=='PAID'
    outgoing=proxy.get('/api/agent/aa/outgoing',headers=a).json()
    assert outgoing[0]['receivedAmount']=='60.00'
    assert mock_client.get('/api/demo/balance',headers=a).json()['balance']=='10060.00'


def test_aa_proxy_rejects_bad_confirmation_and_cross_user_action(stub_bank):
    suffix=uuid4().hex[:6]
    a=_login('单主'+suffix,'139'+str(int(uuid4().hex[:8],16)%100000000).zfill(8))
    b=_login('付主'+suffix,'136'+str(int(uuid4().hex[:8],16)%100000000).zfill(8))
    d=mock_client.post('/api/aa/prepare',headers=a,json={
        'participants':['付主'+suffix], 'amount':'20', 'splitMode':'per_person',
        'requestId':uuid4().hex}).json()
    mock_client.post('/api/aa/'+d['collectionId']+'/publish',headers=a,json={'requestId':uuid4().hex})
    iid=d['items'][0]['itemId']
    assert proxy.post('/api/agent/aa/items/'+iid+'/payment/prepare',headers=a,
                      json={'requestId':uuid4().hex}).status_code==404
    assert proxy.post('/api/agent/aa/items/'+iid+'/payment/confirm',headers=b,
                      json={'requestId':uuid4().hex, 'confirmed':False}).status_code==422
