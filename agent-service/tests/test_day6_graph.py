"""Execute after `pip install -r requirements.txt` has installed LangGraph."""
import asyncio
from uuid import uuid4
from datetime import datetime
from zoneinfo import ZoneInfo
from langgraph.types import Command
from app import banking_client as bank
from app.graph.workflow import graph


def fake_data(monkeypatch):
    async def transactions(auth):
        assert auth == 'Bearer local-test-user'
        return [{'direction':'OUT','amount':'25.00','category':'订阅',
                 'occurredAt':str(datetime.now(ZoneInfo('Asia/Shanghai')).date())+' 12:00:00'}]
    async def subscriptions(auth):
        assert auth == 'Bearer local-test-user'
        return [{'id':1,'merchantName':'视频会员','amount':'25.00',
                 'billingCycle':'MONTHLY','status':'ACTIVE'}]
    monkeypatch.setattr(bank,'transactions',transactions)
    monkeypatch.setattr(bank,'subscriptions',subscriptions)


def test_readonly_cross_scenario(monkeypatch):
    fake_data(monkeypatch)
    async def run():
        config={'configurable':{'thread_id':str(uuid4())}}
        result=await graph.ainvoke({'request':'分析最近消费，查询我的订阅'},config,
             context={'authorization':'Bearer local-test-user'})
        assert result['report']['totalExpense']=='25.00'
        assert result['result']=='ANALYZED'
        assert not result.get('__interrupt__')
    asyncio.run(run())


def test_interrupt_and_refuse_without_write(monkeypatch):
    fake_data(monkeypatch)
    async def cannot_cancel(*args,**kwargs): raise AssertionError('no backend mutation on decline')
    monkeypatch.setattr(bank,'cancel_subscription',cannot_cancel)
    async def run():
        config={'configurable':{'thread_id':str(uuid4())}}
        paused=await graph.ainvoke({'request':'分析消费，查订阅并取消视频会员代扣'},config,
            context={'authorization':'Bearer local-test-user'})
        assert paused.get('__interrupt__')
        done=await graph.ainvoke(Command(resume=False),config,
            context={'authorization':'Bearer local-test-user'})
        assert done['result']=='DECLINED'
    asyncio.run(run())


def test_approve_does_not_fake_bank_success(monkeypatch):
    fake_data(monkeypatch)
    async def not_ready(*args,**kwargs): raise bank.BankError('No Java endpoint',404)
    monkeypatch.setattr(bank,'cancel_subscription',not_ready)
    async def run():
        config={'configurable':{'thread_id':str(uuid4())}}
        paused=await graph.ainvoke({'request':'分析消费，查订阅并取消视频会员代扣'},config,
            context={'authorization':'Bearer local-test-user'})
        assert paused.get('__interrupt__')
        done=await graph.ainvoke(Command(resume=True),config,
            context={'authorization':'Bearer local-test-user'})
        assert done['result']=='NOT_CONFIRMED'
    asyncio.run(run())
