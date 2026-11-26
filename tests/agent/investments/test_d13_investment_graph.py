"""D13 no-money mocked graph contract tests. Run with project's Python 3.11+ venv."""
import pytest
from types import SimpleNamespace
from uuid import uuid4
from fastapi import HTTPException
from app.investments import api


class Task:
    def __init__(self, t, name=None, qty=None):
        self.type=t; self.product_name=name; self.units=qty
    def model_dump(self, exclude_none=True):
        x={'type':self.type}
        if self.product_name is not None: x['product_name']=self.product_name
        if self.units is not None: x['units']=self.units
        return x


@pytest.fixture
def fake(monkeypatch):
    calls={'prepare':[],'confirm':[]}
    data={}

    async def current_user(token):
        if token == 'Bearer user1': return {'userId':1}
        if token == 'Bearer user2': return {'userId':2}
        raise RuntimeError('invalid test token')
    async def products(_):
        return [{'productId':101,'name':'稳健模拟理财','riskLevel':1,'nav':100.00,'active':True}]
    async def prepare(_,pid,action,qty,rid):
        calls['prepare'].append((pid,action,qty,rid))
        oid=len(calls['prepare'])+1000
        data[oid]={'orderId':oid,'productId':pid,'productName':'稳健模拟理财',
                   'action':action,'units':float(qty),'amount':100*float(qty),
                   'nav':100.00,'riskLevel':1,'status':'PENDING_APPROVAL'}
        return dict(data[oid])
    async def order(_,oid): return dict(data[oid])
    async def confirm(_,oid,approved):
        calls['confirm'].append((oid,approved))
        data[oid]['status']='SUCCESS' if approved else 'CANCELLED'
        return dict(data[oid])
    async def plan(msg):
        if '购买未知' in msg:
            return SimpleNamespace(status='ready', tasks=[Task('investment_buy','不存在', '1')])
        return SimpleNamespace(status='ready',tasks=[Task('investment_buy','稳健模拟理财','2')])

    monkeypatch.setattr(api.bank,'current_user',current_user)
    monkeypatch.setattr(api.client,'products',products)
    monkeypatch.setattr(api.client,'prepare',prepare)
    monkeypatch.setattr(api.client,'order',order)
    monkeypatch.setattr(api.client,'confirm',confirm)
    # workflow's client is the exact same imported module.
    monkeypatch.setattr(api,'plan_tasks',plan)
    yield calls, data
    api._sessions.clear(); api._locks.clear()


@pytest.mark.asyncio
async def test_prepare_then_confirm_once(fake):
    calls,data=fake
    item=await api.start(api.StartBody(message='申购稳健模拟理财2份',requestId=uuid4().hex),authorization='Bearer user1')
    assert item['status']=='WAITING_INVESTMENT_APPROVAL'
    assert len(calls['prepare'])==1 and calls['confirm']==[]
    result=await api.resume(api.DecideBody(threadId=item['threadId'],approved=True),authorization='Bearer user1')
    assert result['status']=='COMPLETED'
    assert len(calls['confirm'])==1
    assert result['order']['status']=='SUCCESS'


@pytest.mark.asyncio
async def test_denial_never_confirms_buy(fake):
    calls,data=fake
    item=await api.start(api.StartBody(message='申购稳健模拟理财2份',requestId=uuid4().hex),authorization='Bearer user1')
    result=await api.resume(api.DecideBody(threadId=item['threadId'],approved=False),authorization='Bearer user1')
    assert result['status']=='REJECTED'
    assert calls['confirm'][0][1] is False
    assert result['order']['status']=='CANCELLED'


@pytest.mark.asyncio
async def test_foreign_user_cannot_approve_thread(fake):
    calls,_=fake
    item=await api.start(api.StartBody(message='申购稳健模拟理财2份',requestId=uuid4().hex),authorization='Bearer user1')
    with pytest.raises(HTTPException) as ex:
        await api.resume(api.DecideBody(threadId=item['threadId'],approved=True),authorization='Bearer user2')
    assert ex.value.status_code==403
    assert calls['confirm']==[]


@pytest.mark.asyncio
async def test_unknown_product_never_prepares(fake):
    calls,_=fake
    item=await api.start(api.StartBody(message='购买未知产品1份',requestId=uuid4().hex),authorization='Bearer user1')
    assert item['status']=='NEEDS_CLARIFICATION'
    assert calls['prepare']==[]
