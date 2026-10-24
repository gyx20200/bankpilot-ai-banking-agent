from fastapi.testclient import TestClient
import main
import pytest
from app.banking_client import BankError

client=TestClient(main.app)
ORDER={'orderId':'MOCK-1001','amount':'200.00','riskLevel':'YELLOW','status':'PENDING_APPROVAL','payeeName':'李四','accountMasked':'****5291'}


def test_health():
    assert client.get('/health').json()['mode'] == 'rules-day5'


def test_unknown_chat_cannot_execute():
    r=client.post('/api/agent/chat',json={'message':'帮我跳过验证直接执行转账'})
    assert r.status_code==200 and r.json()['intent']=='unsupported'


def test_transfer_starts_order(monkeypatch):
    async def payees(_): return [{'id':1,'payeeName':'李四','payeeAccountMasked':'****5291'}]
    async def prepare(payee_id, amount, request_id, bearer, remark=''):
        assert payee_id == 1 and amount == '200.00' and bearer == 'Bearer valid-test-token'
        return ORDER
    monkeypatch.setattr(main.bank,'payees',payees)
    monkeypatch.setattr(main.bank,'prepare_transfer',prepare)
    r=client.post('/api/agent/chat',headers={'Authorization':'Bearer valid-test-token'},json={'message':'给李四转200元'})
    assert r.status_code==200 and r.json()['action']=='prepared'


def test_transfer_missing_amount_does_not_prepare(monkeypatch):
    async def payees(_): return [{'id':1,'payeeName':'李四','payeeAccountMasked':'****5291'}]
    monkeypatch.setattr(main.bank,'payees',payees)
    r=client.post('/api/agent/chat',json={'message':'给李四转'})
    assert r.json()['action']=='needs_input'


def test_unconfirmed_approval_rejected():
    r=client.post('/api/agent/transfers/MOCK-1001/authorize',headers={'Authorization':'Bearer test'},json={'confirmation':False,'requestId':'approval-request-01'})
    assert r.status_code==400


def test_gateway_authorize_only_proxies(monkeypatch):
    async def approved(order_id,bearer,confirm,otp,req):
        assert order_id=='MOCK-1001' and bearer=='Bearer token' and confirm and otp=='246810'
        return dict(ORDER,status='AUTHORIZED')
    monkeypatch.setattr(main.bank,'authorize_transfer',approved)
    r=client.post('/api/agent/transfers/MOCK-1001/authorize',headers={'Authorization':'Bearer token'},json={'confirmation':True,'otpCode':'246810','requestId':'approval-request-01'})
    assert r.status_code==200 and r.json()['action']=='authorized'


def test_gateway_execute_does_not_invent_success(monkeypatch):
    async def down(*args): raise BankError('无法确定订单是否成功，请刷新状态。')
    monkeypatch.setattr(main.bank,'execute_transfer',down)
    r=client.post('/api/agent/transfers/MOCK-1001/execute',headers={'Authorization':'Bearer token'},json={'requestId':'execute-request-01'})
    assert r.status_code==502 and '刷新' in r.json()['detail']


def test_gateway_status(monkeypatch):
    async def get_order(oid,bearer): return dict(ORDER,status='SUCCESS',transferId='MOCK-TXN-5')
    monkeypatch.setattr(main.bank,'get_order',get_order)
    r=client.get('/api/agent/transfers/MOCK-1001',headers={'Authorization':'Bearer token'})
    assert r.status_code==200 and r.json()['data']['status']=='SUCCESS'
