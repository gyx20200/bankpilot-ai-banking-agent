import asyncio
import pytest
from fastapi.testclient import TestClient
from app import banking_client as bank
import mock_backend as mock

TOKEN = 'Bearer mock-day4-token'
H = {'Authorization': TOKEN}


def run(c):
    return asyncio.run(c)


def test_mock_yellow_authorize_client(monkeypatch):
    monkeypatch.setattr(bank, 'BANK_MODE', 'mock')
    async def fake_request(method, url, bearer, data=None):
        assert bearer == TOKEN
        if method == 'POST':
            assert data == {'confirmation': True, 'otpCode': None, 'requestId': 'authorize_0001'}
            return {'orderId':'MOCK-1001','status':'AUTHORIZED','riskLevel':'YELLOW'}
        return {'orderId':'MOCK-1001','status':'AUTHORIZED','riskLevel':'YELLOW', 'amount':'200.00'}
    monkeypatch.setattr(bank,'_request',fake_request)
    r=run(bank.authorize_transfer('MOCK-1001', TOKEN, True, None, 'authorize_0001'))
    assert r['status']=='AUTHORIZED' and r['result']=='AUTHORIZED'


def test_java_authorize_contract_unchanged(monkeypatch):
    monkeypatch.setattr(bank, 'BANK_MODE', 'java')
    async def fake_request(method, url, bearer, data=None):
        if method=='POST':
            assert data == {'confirmed': True, 'otp': '123456'}
            return {'orderId':99, 'status':'AUTHORIZED','riskLevel':'RED','result':'AUTHORIZED'}
        return {'orderId':99,'status':'AUTHORIZED','riskLevel':'RED','amount':'1100.00'}
    monkeypatch.setattr(bank,'_request',fake_request)
    r=run(bank.authorize_transfer('99',TOKEN,True,'123456','authorize_0001'))
    assert r['status']=='AUTHORIZED'


def test_false_confirmation_never_hits_bank(monkeypatch):
    async def never(*a,**k): raise AssertionError('should not call bank')
    monkeypatch.setattr(bank,'_request',never)
    with pytest.raises(bank.BankError):
        run(bank.authorize_transfer('MOCK-1001', TOKEN, False, None, 'authorize_0001'))


def test_mock_cancel_has_request_id(monkeypatch):
    monkeypatch.setattr(bank,'BANK_MODE','mock')
    async def fake_request(method, url, bearer, data=None):
        if method=='GET':
            return {'orderId':'MOCK-1001','status':'PENDING_APPROVAL','riskLevel':'YELLOW','amount':'200.00'}
        assert data == {'requestId':'cancel_0001'}
        return {'orderId':'MOCK-1001','status':'CANCELLED','riskLevel':'YELLOW','amount':'200.00'}
    monkeypatch.setattr(bank,'_request',fake_request)
    assert run(bank.cancel_transfer('MOCK-1001',TOKEN,'cancel_0001'))['status']=='CANCELLED'


@pytest.fixture(autouse=True)
def reset():
    mock.reset_demo()


def test_mock_red_otp_request():
    client=TestClient(mock.app)
    prepared=client.post('/api/transfers/prepare',headers=H,json={
        'payeeId':1,'amount':'1200.00','requestId':'prepare_0001'
    })
    assert prepared.status_code == 200 and prepared.json()['riskLevel']=='RED'
    oid=prepared.json()['orderId']
    r=client.post(f'/api/transfers/{oid}/otp/request',headers=H)
    assert r.status_code==200
    assert r.json()['expiresInSeconds']==120
    assert 'otp' not in r.json()
    auth=client.post(f'/api/transfers/{oid}/authorize',headers=H,json={
        'confirmation':True,'otpCode':'246810','requestId':'authorize_0001'
    })
    assert auth.status_code==200 and auth.json()['status']=='AUTHORIZED'


def test_mock_yellow_does_not_need_otp():
    client=TestClient(mock.app)
    prepared=client.post('/api/transfers/prepare',headers=H,json={
        'payeeId':1,'amount':'200.00','requestId':'prepare_0001'
    })
    oid=prepared.json()['orderId']
    assert client.post(f'/api/transfers/{oid}/otp/request',headers=H).status_code==409
