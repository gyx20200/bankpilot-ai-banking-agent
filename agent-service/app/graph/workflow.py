"""Day6 finite-state, read-first LangGraph with explicit subscription cancellation approval.

No LLM-suggested SQL or arbitrary tools. Bank cancellation remains optional until
Java provides a real authenticated endpoint. Checkpoints are IN MEMORY only.
"""
from typing import TypedDict, Any
from uuid import uuid4
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.runtime import Runtime
from langgraph.types import interrupt

from app import banking_client as bank
from app.graph.report import build_report, find_candidate


class Context(TypedDict):
    authorization: str  # runtime-only; never part of checkpointed State


class State(TypedDict, total=False):
    request: str
    transactions: list[dict]
    subscriptions: list[dict]
    report: dict
    candidate: dict | None
    cancelKey: str
    approved: bool
    result: str
    details: str


async def fetch_transactions(state: State, runtime: Runtime[Context]):
    return {'transactions': await bank.transactions(runtime.context['authorization'])}


async def fetch_subscriptions(state: State, runtime: Runtime[Context]):
    return {'subscriptions': await bank.subscriptions(runtime.context['authorization'])}


async def analyze(state: State):
    return {
        'report': build_report(state['transactions']),
        'candidate': find_candidate(state['request'], state['subscriptions']),
        'cancelKey': str(uuid4()),
        'result': 'ANALYZED',
    }


def next_after_analysis(state: State):
    return 'approval' if state.get('candidate') else END


def human_approval(state: State):
    choice = interrupt({
        'kind': 'SUBSCRIPTION_CANCELLATION',
        'target': state['candidate'],
        'notice': '是否申请取消该模拟银行代扣授权？本操作需要银行后端再次验证。',
    })
    return {'approved': choice is True,
            'result': 'APPROVED_PENDING_BANK' if choice is True else 'DECLINED'}


def next_after_approval(state: State):
    return 'cancel' if state.get('approved') is True else END


async def cancel(state: State, runtime: Runtime[Context]):
    target = state['candidate']
    # Re-fetch the current user's authorizations; never trust stale graph state.
    current = await bank.subscriptions(runtime.context['authorization'])
    if not any(s.get('id') == target['id'] and s.get('status') == 'ACTIVE' for s in current):
        return {'result': 'NOT_EXECUTED', 'details': '该代扣状态已变化，请重新查询。'}
    try:
        response = await bank.cancel_subscription(target['id'],
                runtime.context['authorization'], state['cancelKey'])
    except bank.BankError:
        return {'result': 'NOT_CONFIRMED', 'details': '银行取消接口尚不可用或拒绝操作，未确认取消成功。'}
    if response.get('status') == 'CANCELLED' and str(response.get('id')) == str(target['id']):
        return {'result': 'CANCELLED', 'details': '银行后端确认模拟代扣授权已取消。'}
    return {'result': 'NOT_CONFIRMED', 'details': '银行没有返回已取消状态，请查询协议。'}


builder = StateGraph(State, context_schema=Context)
builder.add_node('transactions', fetch_transactions)
builder.add_node('subscriptions', fetch_subscriptions)
builder.add_node('analysis', analyze)
builder.add_node('approval', human_approval)
builder.add_node('cancel', cancel)
builder.add_edge(START, 'transactions')
builder.add_edge(START, 'subscriptions')
builder.add_edge('transactions', 'analysis')
builder.add_edge('subscriptions', 'analysis')
builder.add_conditional_edges('analysis', next_after_analysis)
builder.add_conditional_edges('approval', next_after_approval)
builder.add_edge('cancel', END)
graph = builder.compile(checkpointer=InMemorySaver())
