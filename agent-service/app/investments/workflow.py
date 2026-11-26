"""Dedicated D13 LangGraph: model may select a registered task, not approve an order."""
from __future__ import annotations
from typing import TypedDict, Any
from langgraph.graph import START, END, StateGraph
from langgraph.types import interrupt
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.runtime import Runtime
from . import client
from app import banking_client as bank

class Context(TypedDict):
    authorization: str

class State(TypedDict, total=False):
    task: dict[str, Any]
    requestId: str
    status: str
    details: str
    order: dict[str, Any]
    result: object
    approved: bool


def route(state: State) -> str:
    return 'read' if state['task']['type'] in ('investment_compare','investment_portfolio') else 'prepare'


async def read(state: State, runtime: Runtime[Context]) -> dict:
    token=runtime.context['authorization']
    value=await (client.products(token) if state['task']['type']=='investment_compare' else client.portfolio(token))
    return {'status':'COMPLETED','result':value,'details':'模拟数据来自 Java/MySQL，只读查询。'}


async def prepare(state: State, runtime: Runtime[Context]) -> dict:
    t=state['task']
    action='BUY' if t['type']=='investment_buy' else 'REDEEM'
    order=await client.prepare(runtime.context['authorization'],t['productId'],action,t['units'],state['requestId'])
    return {'order':order,'status':'PENDING_APPROVAL'}


def pause(state: State) -> dict:
    # No external side effects in the interrupt node: LangGraph may re-enter this node.
    o=state['order']
    choice=interrupt({'kind':'D13_INVESTMENT','orderId':o['orderId'],
                      'productName':o['productName'],'action':o['action'],
                      'units':str(o['units']),'amount':str(o['amount']),
                      'riskLevel':o['riskLevel'],
                      'notice':'模拟理财交易：确认前不会扣款或变更持仓。'} )
    if type(choice) is not bool:
        return {'status':'INVALID_DECISION','details':'需要明确的布尔审批值。'}
    return {'approved':choice,'status':'APPROVED' if choice else 'DECLINED'}


def next_decision(state: State) -> str:
    return 'settle' if state['status'] in ('APPROVED','DECLINED') else END


async def settle(state: State, runtime: Runtime[Context]) -> dict:
    original=state['order']; token=runtime.context['authorization']
    oid=original['orderId']
    try:
        response=await client.confirm(token,oid,state['approved'])
    except bank.BankError:
        response=await client.order(token,oid)  # Query exactly the existing order; never create a new one.
        allowed={'SUCCESS'} if state['approved'] else {'CANCELLED'}
        if response.get('status') not in allowed:
            raise
    return {'order':response,'status':'VERIFY_PENDING'}


async def verify(state: State, runtime: Runtime[Context]) -> dict:
    o=state['order']
    latest=await client.order(runtime.context['authorization'],o['orderId'])
    from decimal import Decimal
    if (latest['orderId']!=o['orderId'] or latest['productId']!=o['productId']
        or latest['action']!=o['action'] or Decimal(str(latest['units']))!=Decimal(str(o['units']))
        or Decimal(str(latest['amount']))!=Decimal(str(o['amount']))):
        raise bank.BankError('银行订单与原批准快照不一致。',409)
    expected='SUCCESS' if state['approved'] else 'CANCELLED'
    if latest['status']!=expected:
        return {'status':latest['status'],'order':latest,'details':'银行未确认预期终态；请查原单。'}
    return {'status':'COMPLETED' if state['approved'] else 'REJECTED','order':latest,
            'details':'银行已核实模拟理财申购/赎回完成。' if state['approved'] else '已拒绝，未变更资金及持仓。'}


builder=StateGraph(State, context_schema=Context)
builder.add_node('read',read)
builder.add_node('prepare',prepare)
builder.add_node('pause',pause)
builder.add_node('settle',settle)
builder.add_node('verify',verify)
builder.add_conditional_edges(START,route,['read','prepare'])
builder.add_edge('read',END)
builder.add_edge('prepare','pause')
builder.add_conditional_edges('pause',next_decision,['settle',END])
builder.add_edge('settle','verify')
builder.add_edge('verify',END)
# D13 MVP uses isolated in-memory checkpoint. Existing D5/D6 durable graph remains unchanged.
graph=builder.compile(checkpointer=InMemorySaver())
