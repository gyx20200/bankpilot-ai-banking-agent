"""Isolated D14 LangGraph; approval is never supplied by the model."""
from __future__ import annotations
from typing import Any, TypedDict
from langgraph.graph import START, END, StateGraph
from langgraph.types import interrupt
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.runtime import Runtime
from app import banking_client as bank
from . import client

class Context(TypedDict):
    authorization: str

class State(TypedDict, total=False):
    task: dict[str,Any]
    requestId: str
    application: dict[str,Any]
    result: Any
    approved: bool
    status: str
    details: str

def route(state:State):
    return 'read' if state['task']['type']=='card_list' else 'prepare'

async def read(state:State,runtime:Runtime[Context]):
    return {'result':await client.cards(runtime.context['authorization']),
            'status':'COMPLETED','details':'卡片别名与限制来自 Java/MySQL 模拟数据库。'}

async def prepare(state:State,runtime:Runtime[Context]):
    return {'application':await client.prepare(runtime.context['authorization'],state['requestId']),
            'status':'PENDING_APPROVAL'}

def pause(state:State):
    app=state['application']
    selected=interrupt({'kind':'D14_VIRTUAL_CARD','applicationId':app['applicationId'],
                        'cardType':app['cardType'],
                        'notice':'仅创建模拟卡片别名；不会产生真实银行卡、卡号或资金操作。'})
    if type(selected) is not bool:
        return {'status':'INVALID_DECISION','details':'需要本人明确确认或拒绝。'}
    return {'approved':selected,'status':'APPROVED' if selected else 'DECLINED'}

def after_pause(state:State):
    return 'settle' if state.get('status') in ('APPROVED','DECLINED') else END

async def settle(state:State,runtime:Runtime[Context]):
    app=state['application'];uid=app['applicationId'];token=runtime.context['authorization']
    try:
        result=await client.confirm(token,uid,state['approved'])
    except bank.BankError:
        result=await client.application(token,uid)
        if result['status']!=('ISSUED' if state['approved'] else 'CANCELLED'):
            raise
    return {'application':result,'status':'VERIFY_PENDING'}

async def verify(state:State,runtime:Runtime[Context]):
    current=await client.application(runtime.context['authorization'],state['application']['applicationId'])
    expected='ISSUED' if state['approved'] else 'CANCELLED'
    if current['status']!=expected or current['cardType']!='VIRTUAL_DEBIT':
        return {'application':current,'status':'NOT_CONFIRMED','details':'请查询 Java 原申请。'}
    return {'application':current,'status':'COMPLETED' if state['approved'] else 'REJECTED',
            'details':'Java 已确认模拟卡片签发。' if state['approved'] else '用户拒绝，未签发卡片。'}

builder=StateGraph(State,context_schema=Context)
for name,fn in [('read',read),('prepare',prepare),('pause',pause),('settle',settle),('verify',verify)]:
    builder.add_node(name,fn)
builder.add_conditional_edges(START,route,['read','prepare'])
builder.add_edge('read',END)
builder.add_edge('prepare','pause')
builder.add_conditional_edges('pause',after_pause,['settle',END])
builder.add_edge('settle','verify')
builder.add_edge('verify',END)
# D14 memory-only MVP. After restart query Java applications; never replay a write.
graph=builder.compile(checkpointer=InMemorySaver())
