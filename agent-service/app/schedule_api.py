"""Read/cancel bank-owned schedules. Execution stays exclusively in Java/MySQL."""
from uuid import uuid4
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from app import banking_client as bank

router = APIRouter(prefix='/api/agent/schedules', tags=['Scheduled transfers'])


class Action(BaseModel):
    requestId: str = Field(pattern=r'^[A-Za-z0-9_-]{8,64}$')


def _error(exc: bank.BankError):
    raise HTTPException(exc.status, str(exc)) from exc


@router.get('')
async def my_schedules(authorization: str | None = Header(default=None)):
    try:
        await bank.current_user(authorization)
        return await bank.scheduled_list(authorization)
    except bank.BankError as exc:
        _error(exc)


@router.get('/{schedule_id}')
async def schedule_detail(schedule_id: str, authorization: str | None = Header(default=None)):
    try:
        await bank.current_user(authorization)
        return await bank.scheduled_get(schedule_id, authorization)
    except bank.BankError as exc:
        _error(exc)


@router.post('/{schedule_id}/cancel')
async def cancel_schedule(schedule_id: str, body: Action,
                          authorization: str | None = Header(default=None)):
    try:
        await bank.current_user(authorization)
        return await bank.scheduled_cancel(schedule_id, body.requestId, authorization)
    except bank.BankError as exc:
        _error(exc)
