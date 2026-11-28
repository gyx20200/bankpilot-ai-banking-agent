"""Authenticated D14 virtual demo-card center. No payment/card-number issuance."""
from __future__ import annotations
import asyncio
from datetime import datetime,timedelta,timezone
from uuid import uuid4
from fastapi import APIRouter, Header, HTTPException
from langgraph.types import Command
from pydantic import BaseModel, Field, StrictBool
from app import banking_client as bank
from app.graph.task_planner import plan_tasks, PlannerError
from . import client
from .workflow import graph

router=APIRouter(prefix='/api/agent/cards',tags=['D14 Virtual Demo Cards'])
_sessions: dict[str,dict]={}
_locks: dict[str,asyncio.Lock]={}

class StartBody(BaseModel):
    message: str=Field(min_length=1,max_length=300)
    requestId: str=Field(pattern=r'^[A-Za-z0-9_-]{8,64}$')
class DecideBody(BaseModel):
    threadId: str=Field(min_length=8,max_length=128)
    approved: StrictBool
class RestrictBody(BaseModel):
    singleTransactionLimit: str=Field(pattern=r'^\d{1,6}(?:\.\d{1,2})?$')
    disableOnline: StrictBool
    requestId: str=Field(pattern=r'^[A-Za-z0-9_-]{8,64}$')

async def owner(token):
    try: value=await bank.current_user(token)
    except bank.BankError as exc: raise HTTPException(exc.status,str(exc)) from exc
    uid=value.get('userId')
    if type(uid) is not int or uid<=0: raise HTTPException(502,'Java 身份校验失败。')
    return uid

def view(thread,state):
    paused=bool(state.get('__interrupt__'))
    return {'threadId':thread,'status':'WAITING_CARD_APPROVAL' if paused else state.get('status','UNKNOWN'),
            'application':state.get('application'), 'result':state.get('result'),
            'details':state.get('details','')}

@router.get('')
async def cards(authorization: str|None=Header(default=None)):
    await owner(authorization)
    try:return await client.cards(authorization)
    except bank.BankError as exc:raise HTTPException(exc.status,str(exc)) from exc

@router.get('/applications')
async def applications(authorization: str|None=Header(default=None)):
    await owner(authorization)
    try:return await client.applications(authorization)
    except bank.BankError as exc:raise HTTPException(exc.status,str(exc)) from exc

@router.get('/applications/{aid}')
async def application(aid:int,authorization: str|None=Header(default=None)):
    await owner(authorization)
    try:return await client.application(authorization,aid)
    except bank.BankError as exc:raise HTTPException(exc.status,str(exc)) from exc

@router.post('/applications/{aid}/cancel')
async def cancel_pending_application(aid:int,authorization: str|None=Header(default=None)):
    # Safe reconciliation for a PENDING_APPROVAL application after Python restart:
    # user can explicitly CANCEL the original Java application, never approve it here.
    await owner(authorization)
    try:
        original=await client.application(authorization,aid)
        if original['status']!='PENDING_APPROVAL':
            raise HTTPException(409,'原申请不在待审批状态；请刷新。')
        result=await client.confirm(authorization,aid,False)
        if result['status']!='CANCELLED':
            raise HTTPException(409,'Java 没有确认取消；请查询原单。')
        return result
    except bank.BankError as exc:raise HTTPException(exc.status,str(exc)) from exc

@router.post('/start')
async def start(body:StartBody,authorization: str|None=Header(default=None)):
    uid=await owner(authorization)
    try:
        plan=await plan_tasks(body.message)
        if plan.status!='ready': return {'status':'NEEDS_CLARIFICATION','details':plan.clarification or '请明确要查询还是申请虚拟模拟卡。'}
        if len(plan.tasks)!=1 or plan.tasks[0].type not in ('card_list','card_apply'):
            return {'status':'NEEDS_CLARIFICATION','details':'卡片中心每次仅处理一种卡片请求。'}
        # Do not let an over-eager model convert lock/loss/credit requests into card issuance.
        if plan.tasks[0].type == 'card_apply':
            if (any(word in body.message for word in ('挂失','锁卡','解锁','冻结','提升额度','提高额度','借贷','信用卡'))
                or not ('卡' in body.message and '虚拟' in body.message
                        and any(word in body.message for word in ('申请','办理','开一张')))):
                return {'status':'NEEDS_CLARIFICATION','details':'只支持明确申请一张虚拟模拟借记卡；挂失、额度调整等留待 D15。'}
        thread=uuid4().hex
        state=await graph.ainvoke({'task':{'type':plan.tasks[0].type},'requestId':body.requestId},
                 config={'configurable':{'thread_id':thread}},context={'authorization':authorization})
        result=view(thread,state)
        if result['status']=='WAITING_CARD_APPROVAL':
            app=state['application']
            _sessions[thread]={'owner':uid,'applicationId':app['applicationId'],
                'cardType':app['cardType'],'expires':datetime.now(timezone.utc)+timedelta(minutes=30)}
            _locks[thread]=asyncio.Lock()
        return result
    except PlannerError as exc:return {'status':'NEEDS_CLARIFICATION','details':str(exc)}
    except bank.BankError as exc:raise HTTPException(exc.status,str(exc)) from exc
    except Exception as exc:raise HTTPException(503,'卡片申请结果不确定；请查询 Java 原申请，不能直接重新建单。') from exc

@router.post('/resume')
async def resume(body:DecideBody,authorization: str|None=Header(default=None)):
    uid=await owner(authorization)
    s=_sessions.get(body.threadId)
    if s is None:raise HTTPException(409,'审批线程不存在或已重启，请查询 Java 原申请。')
    if s['owner']!=uid:raise HTTPException(403,'无法审批其他用户的申请。')
    if s['expires']<datetime.now(timezone.utc):raise HTTPException(409,'审批超时，请查询 Java 原申请。')
    async with _locks[body.threadId]:
        try:
            original=await client.application(authorization,s['applicationId'])
            if original['cardType']!=s['cardType'] or original['applicationId']!=s['applicationId']:
                raise HTTPException(409,'原申请与审批对象不一致。')
            if original['status']!='PENDING_APPROVAL':
                return {'threadId':body.threadId,'status':original['status'],'application':original,
                        'details':'Java 申请已有结果；没有重复签发。'}
            state=await graph.ainvoke(Command(resume=body.approved),
                        config={'configurable':{'thread_id':body.threadId}},
                        context={'authorization':authorization})
            result=view(body.threadId,state)
            if result['status'] not in ('WAITING_CARD_APPROVAL','UNKNOWN'):
                _sessions.pop(body.threadId,None);_locks.pop(body.threadId,None)
            return result
        except bank.BankError as exc:raise HTTPException(exc.status,str(exc)) from exc
        except HTTPException:raise
        except Exception as exc:raise HTTPException(503,'审批结果不确定，请查原申请。') from exc

@router.post('/{cid}/restrictions')
async def restrict(cid:int,body:RestrictBody,authorization: str|None=Header(default=None)):
    await owner(authorization)
    try:return await client.restrict(authorization,cid,body.singleTransactionLimit,
                                     body.disableOnline,body.requestId)
    except bank.BankError as exc:raise HTTPException(exc.status,str(exc)) from exc
