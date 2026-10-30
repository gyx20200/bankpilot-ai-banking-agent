"""Use local installed LangGraph to run end-to-end checkpoint approval tests."""
import asyncio
from datetime import date
from uuid import uuid4

import pytest
from langgraph.types import Command
from app import banking_client as bank
from app.graph import dynamic_read_workflow as reads
from app.graph import dynamic_cancellation_workflow as flow
from app.graph.task_planner import validate_plan

TOKEN='Bearer mock-day4-token'

def run(c): return asyncio.run(c)

@pytest.fixture
def scenario(monkeypatch):
    events=[]
    order={'orderId':'MOCK-1001','payeeName':'李四','accountMasked':'****5291',
           'amount':'200.00','riskLevel':'YELLOW','status':'PENDING_APPROVAL'}
    async def plan(msg):
        return validate_plan({'tasks':[
            {'type':'transfer_prepare','payee_name':'李四','amount':'200'}
        ]},date(2026,10,28),msg)
    async def payees(bearer):
        return [{'id':1,'payeeName':'李四','payeeAccountMasked':'****5291'}]
    async def search(bearer, *, name=None, phone=None):
        return [{'recipientId': 1, 'payeeName': '李四', 'accountMasked': '****5291'}]
    async def confirm(recipient_id,bearer):
        return {'id':1,'payeeName':'李四','payeeAccountMasked':'****5291'}
    async def prepare(id,amount,rid,bearer):
        events.append(('prepare',rid))
        return dict(order)
    async def get(oid,bearer): return dict(order)
    async def authorize(oid,bearer,confirmed,otp,rid):
        assert confirmed is True
        events.append(('authorize',rid,otp))
        order['status']='AUTHORIZED'
        return dict(order)
    async def execute(oid,bearer,rid):
        assert order['status']=='AUTHORIZED'
        events.append(('execute',rid))
        order['status']='SUCCESS'
        return dict(order)
    async def cancel(oid,bearer,rid):
        events.append(('cancel',rid))
        order['status']='CANCELLED'
        return dict(order)
    monkeypatch.setattr(flow,'plan_tasks',plan)
    monkeypatch.setitem(reads.READ_EXECUTORS,'payees',payees)
    monkeypatch.setattr(bank,'search_registered_recipients',search)
    monkeypatch.setattr(bank,'confirm_registered_recipient',confirm)
    monkeypatch.setattr(bank,'prepare_transfer',prepare)
    monkeypatch.setattr(bank,'get_order',get)
    monkeypatch.setattr(bank,'authorize_transfer',authorize)
    monkeypatch.setattr(bank,'execute_transfer',execute)
    monkeypatch.setattr(bank,'cancel_transfer',cancel)
    return events, order


def start():
    cfg={'configurable':{'thread_id':str(uuid4())}}
    res=run(flow.dynamic_graph.ainvoke({'message':'给李四转200元'},cfg,
        context={'authorization':TOKEN}))
    assert res.get('__interrupt__')
    return cfg


def test_yellow_approval_then_verified_success(scenario):
    events,order=scenario
    cfg=start()
    snap=flow.dynamic_graph.get_state(cfg)
    assert snap.next==('wait_for_transfer_approval',)
    assert 'transferAuthorizeRequestId' in snap.values
    assert events[0][0]=='prepare'
    result=run(flow.dynamic_graph.ainvoke(Command(resume=True),cfg,
        context={'authorization':TOKEN,'transferOtpCode':None}))
    assert result['status']=='COMPLETED'
    assert result['transferOrder']['status']=='SUCCESS'
    assert [x[0] for x in events]==['prepare','authorize','execute']


def test_decline_cancels_without_debit(scenario):
    events,order=scenario
    cfg=start()
    result=run(flow.dynamic_graph.ainvoke(Command(resume=False),cfg,
        context={'authorization':TOKEN}))
    assert result['status']=='REJECTED'
    assert order['status']=='CANCELLED'
    assert [x[0] for x in events]==['prepare','cancel']


def test_red_requires_otp_and_never_checkpoints_it(scenario):
    events,order=scenario
    order['riskLevel']='RED'
    cfg=start()
    with pytest.raises(bank.BankError):
        run(flow.dynamic_graph.ainvoke(Command(resume=True),cfg,
            context={'authorization':TOKEN}))
    snap=flow.dynamic_graph.get_state(cfg)
    assert 'transfer_authorize' in snap.next
    assert '666666' not in repr(snap.values)
    order['status']='PENDING_APPROVAL'
    result=run(flow.dynamic_graph.ainvoke(None,cfg,
        context={'authorization':TOKEN,'transferOtpCode':'666666'}))
    assert result['status']=='COMPLETED'
    assert events[-2][2]=='666666'
    assert '666666' not in repr(flow.dynamic_graph.get_state(cfg).values)
