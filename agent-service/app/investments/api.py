"""Authenticated D13 investment workflow endpoints. Separate from existing D6 approvals."""
from __future__ import annotations
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4
from fastapi import APIRouter, Header, HTTPException
from langgraph.types import Command
from pydantic import BaseModel, Field, StrictBool
from app import banking_client as bank
from app.graph.task_planner import plan_tasks, PlannerError
from . import client
from .workflow import graph

router=APIRouter(prefix='/api/agent/investments',tags=['D13 Demo Investments'])
_sessions: dict[str,dict]={}
_locks: dict[str,asyncio.Lock]={}

class StartBody(BaseModel):
    message: str = Field(min_length=1,max_length=300)
    requestId: str = Field(pattern=r'^[A-Za-z0-9_-]{8,64}$')

class DecideBody(BaseModel):
    threadId: str = Field(min_length=8,max_length=128)
    approved: StrictBool

class SurveyBody(BaseModel):
    lossTolerance: int = Field(ge=1,le=3)
    horizon: int = Field(ge=1,le=3)
    experience: int = Field(ge=1,le=3)


def fail(exc: bank.BankError) -> HTTPException:
    return HTTPException(exc.status,str(exc))


async def owner(token: str | None) -> int:
    try: data=await bank.current_user(token)
    except bank.BankError as exc: raise fail(exc) from exc
    user_id=data.get('userId')
    if type(user_id) is not int or user_id<=0: raise HTTPException(502,'银行认证用户数据异常。')
    return user_id


def view(thread: str, state: dict) -> dict:
    paused=bool(state.get('__interrupt__'))
    return {'threadId':thread,
            'status':'WAITING_INVESTMENT_APPROVAL' if paused else state.get('status','UNKNOWN'),
            'order':state.get('order'), 'result':state.get('result'),
            'details':state.get('details',''), 'approvalType':'investment' if paused else None}


@router.get('/products')
async def products(authorization: str | None = Header(default=None)):
    await owner(authorization)
    try: return await client.products(authorization)
    except bank.BankError as exc: raise fail(exc) from exc


@router.get('/portfolio')
async def portfolio(authorization: str | None = Header(default=None)):
    await owner(authorization)
    try: return await client.portfolio(authorization)
    except bank.BankError as exc: raise fail(exc) from exc


@router.get('/profile')
async def profile(authorization: str | None = Header(default=None)):
    await owner(authorization)
    try: return await client.profile(authorization)
    except bank.BankError as exc: raise fail(exc) from exc


@router.post('/profile/assess')
async def assess(body: SurveyBody,authorization: str | None = Header(default=None)):
    await owner(authorization)
    try: return await client.assess(authorization,body.model_dump())
    except bank.BankError as exc: raise fail(exc) from exc


@router.get('/orders')
async def orders(authorization: str | None = Header(default=None)):
    await owner(authorization)
    try: return await client.orders(authorization)
    except bank.BankError as exc: raise fail(exc) from exc


@router.get('/orders/{order_id}')
async def order(order_id: int,authorization: str | None = Header(default=None)):
    await owner(authorization)
    try: return await client.order(authorization,order_id)
    except bank.BankError as exc: raise fail(exc) from exc


@router.post('/start')
async def start(body: StartBody, authorization: str | None = Header(default=None)):
    uid=await owner(authorization)
    try:
        plan=await plan_tasks(body.message)
        if plan.status!='ready':
            return {'status':'NEEDS_CLARIFICATION','details':plan.clarification or '请明确产品和份额。'}
        if len(plan.tasks)!=1 or plan.tasks[0].type not in (
            'investment_compare','investment_portfolio','investment_buy','investment_redeem'):
            return {'status':'NEEDS_CLARIFICATION','details':'理财中心一次只处理一项理财任务。其他银行业务请回到主聊天框。'}
        task=plan.tasks[0].model_dump(exclude_none=True)
        if task['type'] in ('investment_buy','investment_redeem'):
            products=await client.products(authorization)
            # Bind LLM-extracted *verbatim product name* to an exact Java product record.
            names=[p for p in products if p.get('name') == task.get('product_name')]
            if len(names)!=1:
                return {'status':'NEEDS_CLARIFICATION','details':'请使用产品列表中完整且唯一的产品名称。'}
            task['productId']=names[0]['productId']
            task['units']=str(task['units'])
            if Decimal(task['units'])<=0:
                return {'status':'NEEDS_CLARIFICATION','details':'请输入合法的申购或赎回份数。'}
        thread=uuid4().hex
        state=await graph.ainvoke({'task':task,'requestId':body.requestId},
                  config={'configurable':{'thread_id':thread}},
                  context={'authorization':authorization})
        result=view(thread,state)
        if result['status']=='WAITING_INVESTMENT_APPROVAL':
            _sessions[thread]={'owner':uid,'expires':datetime.now(timezone.utc)+timedelta(minutes=30),
                               'orderId':state['order']['orderId'], 'requestId':body.requestId,
                               'snapshot':{k:state['order'][k] for k in ('productId','action','units','amount','nav')}}
            _locks[thread]=asyncio.Lock()
        return result
    except PlannerError as exc:
        return {'status':'NEEDS_CLARIFICATION','details':str(exc)}
    except bank.BankError as exc: raise fail(exc) from exc
    except Exception as exc:
        raise HTTPException(503,'理财工作流结果尚未确认；请到订单记录核对原订单，禁止新建重复申请。') from exc


@router.post('/resume')
async def resume(body: DecideBody,authorization: str | None = Header(default=None)):
    uid=await owner(authorization)
    session=_sessions.get(body.threadId)
    if session is None: raise HTTPException(409,'会话不存在或已重启；请查 Java 理财订单，勿重新建单。')
    if session['owner']!=uid: raise HTTPException(403,'不可操作其他用户的理财审批。')
    if session['expires']<datetime.now(timezone.utc):
        raise HTTPException(409,'理财审批窗口已过期；请查原单。')
    lock=_locks[body.threadId]
    async with lock:
        try:
            previous=await client.order(authorization,session['orderId'])
            snapshot=session['snapshot']
            if (previous.get('productId')!=snapshot['productId']
                or previous.get('action')!=snapshot['action']
                or any(Decimal(str(previous.get(k)))!=Decimal(str(snapshot[k])) for k in ('units','amount','nav'))):
                raise HTTPException(409,'原银行订单与审批快照不符，禁止执行。')
            if previous['status']!='PENDING_APPROVAL':
                return {'threadId':body.threadId,'status':previous['status'],'order':previous,
                        'details':'银行订单已有结果，不会再次执行。'}
            result=await graph.ainvoke(Command(resume=body.approved),
                   config={'configurable':{'thread_id':body.threadId}},
                   context={'authorization':authorization})
            response=view(body.threadId,result)
            if response['status'] not in ('WAITING_INVESTMENT_APPROVAL','UNKNOWN'):
                _sessions.pop(body.threadId,None)
                _locks.pop(body.threadId,None)
            return response
        except bank.BankError as exc:
            raise fail(exc) from exc
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(503,'审批结果未确认；请按原订单ID查询 Java，勿重新执行。') from exc
