"""D14 isolated workflow regression. Synchronous pytest wrappers need no asyncio plugin."""
import asyncio
from types import SimpleNamespace
from uuid import uuid4
import pytest
from fastapi import HTTPException
from app.cards import api

class Task:
    def __init__(self, name):self.type=name

@pytest.fixture
def fake(monkeypatch):
    calls={'prepare':[],'confirm':[]}
    apps={}
    async def user(token):
        if token=='Bearer user1':return {'userId':1}
        if token=='Bearer user2':return {'userId':2}
        raise HTTPException(status_code=401,detail='invalid demo token')
    async def plan(message):
        if '未知操作' in message:return SimpleNamespace(status='ready',tasks=[Task('investment_buy')])
        return SimpleNamespace(status='ready',tasks=[Task('card_list' if '查询' in message else 'card_apply')])
    async def prepare(token,rid):
        calls['prepare'].append(rid)
        aid=len(calls['prepare'])+2000
        apps[aid]={'applicationId':aid,'status':'PENDING_APPROVAL',
                   'cardType':'VIRTUAL_DEBIT','cardId':None}
        return dict(apps[aid])
    async def application(token,aid):
        if aid not in apps:raise HTTPException(status_code=404)
        return dict(apps[aid])
    async def confirm(token,aid,approved):
        calls['confirm'].append((aid,approved))
        apps[aid]['status']='ISSUED' if approved else 'CANCELLED'
        apps[aid]['cardId']=10 if approved else None
        return dict(apps[aid])
    async def cards(token):return [{'cardId':10,'cardAlias':'BP-VC-DEMO', 'status':'ACTIVE'}]
    monkeypatch.setattr(api.bank,'current_user',user)
    monkeypatch.setattr(api,'plan_tasks',plan)
    monkeypatch.setattr(api.client,'prepare',prepare)
    monkeypatch.setattr(api.client,'confirm',confirm)
    monkeypatch.setattr(api.client,'application',application)
    monkeypatch.setattr(api.client,'cards',cards)
    yield calls,apps
    api._sessions.clear();api._locks.clear()

def run(coro):return asyncio.run(coro)

def test_query_cards_is_read_only(fake):
    calls,_=fake
    data=run(api.start(api.StartBody(message='查询我的模拟卡',requestId=uuid4().hex),authorization='Bearer user1'))
    assert data['status']=='COMPLETED'
    assert calls['prepare']==[] and calls['confirm']==[]

def test_approval_required_before_issuing(fake):
    calls,_=fake
    item=run(api.start(api.StartBody(message='申请虚拟模拟银行卡',requestId=uuid4().hex),authorization='Bearer user1'))
    assert item['status']=='WAITING_CARD_APPROVAL' and len(calls['prepare'])==1
    assert calls['confirm']==[]
    done=run(api.resume(api.DecideBody(threadId=item['threadId'],approved=True),authorization='Bearer user1'))
    assert done['status']=='COMPLETED' and done['application']['status']=='ISSUED'
    assert calls['confirm']==[(item['application']['applicationId'],True)]

def test_rejection_does_not_issue(fake):
    calls,_=fake
    item=run(api.start(api.StartBody(message='申请一张虚拟模拟银行卡',requestId=uuid4().hex),authorization='Bearer user1'))
    done=run(api.resume(api.DecideBody(threadId=item['threadId'],approved=False),authorization='Bearer user1'))
    assert done['status']=='REJECTED' and done['application']['status']=='CANCELLED'
    assert calls['confirm'][0][1] is False

def test_foreign_user_cannot_resume(fake):
    calls,_=fake
    item=run(api.start(api.StartBody(message='申请一张虚拟模拟银行卡',requestId=uuid4().hex),authorization='Bearer user1'))
    with pytest.raises(HTTPException) as raised:
        run(api.resume(api.DecideBody(threadId=item['threadId'],approved=True),authorization='Bearer user2'))
    assert raised.value.status_code==403 and calls['confirm']==[]

def test_unrelated_request_is_not_executed(fake):
    calls,_=fake
    item=run(api.start(api.StartBody(message='未知操作',requestId=uuid4().hex),authorization='Bearer user1'))
    assert item['status']=='NEEDS_CLARIFICATION' and calls['prepare']==[]


def test_cancel_original_pending_after_restart(fake):
    calls,_=fake
    item=run(api.start(api.StartBody(message='申请虚拟模拟银行卡',requestId=uuid4().hex),authorization='Bearer user1'))
    # Simulate a lost Python approval session (process restart).
    api._sessions.clear();api._locks.clear()
    cancelled=run(api.cancel_pending_application(item['application']['applicationId'],authorization='Bearer user1'))
    assert cancelled['status']=='CANCELLED' and calls['confirm'][0][1] is False
