"""Day6 read/approval endpoints. Never accepts user IDs or auth from the model."""
import hashlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from langgraph.types import Command
from app import banking_client as bank
from app.graph.workflow import graph

router = APIRouter(prefix='/api/agent/workflows', tags=['Cross-Scenario'])
_owners = {}  # demo-only; use authenticated persistent task store after contest


class StartBody(BaseModel):
    message: str = Field(min_length=6, max_length=300)


class ResumeBody(BaseModel):
    threadId: str
    approved: bool


def _identity(token: str | None):
    if not token or not token.startswith('Bearer '):
        raise HTTPException(401, '请先登录银行演示账户。')
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def _view(thread_id: str, result: dict):
    paused = bool(result.get('__interrupt__'))
    return {
        'threadId': thread_id,
        'status': 'WAITING_APPROVAL' if paused else result.get('result', 'UNKNOWN'),
        'report': result.get('report'),
        'subscriptions': [
            {'id': s['id'], 'merchantName': s['merchantName'], 'amount': str(s['amount']),
             'status': s['status']}
            for s in result.get('subscriptions', [])
        ],
        'candidate': result.get('candidate'),
        'details': result.get('details', ''),
        'steps': ['查询交易', '查询订阅', '统计与匹配'] + (['等待确认'] if paused else []),
    }


@router.post('/start')
async def start(body: StartBody, authorization: str | None = Header(default=None)):
    owner = _identity(authorization)
    # Only launch fixed supported scenario; no arbitrary LLM-created DAG.
    if not any(w in body.message for w in ('账单', '消费', '支出')) or not any(w in body.message for w in ('订阅', '代扣', '会员')):
        raise HTTPException(422, '此工作流需要同时包含账单分析和订阅查询需求。')
    thread_id = str(uuid4())
    config = {'configurable': {'thread_id': thread_id}}
    try:
        result = await graph.ainvoke({'request': body.message}, config,
                                     context={'authorization': authorization})
    except bank.BankError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    # Save ownership only after authenticated reads succeed.
    if result.get('__interrupt__'):
        _owners[thread_id] = (owner, datetime.now(timezone.utc) + timedelta(minutes=15))
    return _view(thread_id, result)


@router.post('/resume')
async def resume(body: ResumeBody, authorization: str | None = Header(default=None)):
    owner = _identity(authorization)
    record = _owners.get(body.threadId)
    if not record or record[0] != owner or datetime.now(timezone.utc) > record[1]:
        raise HTTPException(403, '任务不存在、已经过期或登录身份不匹配。')
    # Make a live bank authorization check before resuming checkpointed state.
    try:
        await bank.subscriptions(authorization)
        result = await graph.ainvoke(Command(resume=body.approved),
                         {'configurable': {'thread_id': body.threadId}},
                         context={'authorization': authorization})
    except bank.BankError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    _owners.pop(body.threadId, None)  # one-shot approval
    return _view(body.threadId, result)
