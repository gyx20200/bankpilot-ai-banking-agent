"""Day 7 AA inbox and payer actions. Bank Java is the sole ledger authority."""
from uuid import uuid4
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from app import banking_client as bank

router = APIRouter(prefix='/api/agent/aa', tags=['AA collection'])


class Action(BaseModel):
    requestId: str = Field(min_length=8, max_length=64, pattern=r'^[A-Za-z0-9_-]+$')


class PaymentConfirm(Action):
    confirmed: bool
    otpCode: str | None = Field(default=None, pattern=r'^\d{6}$')


def translate(exc: bank.BankError):
    raise HTTPException(exc.status, str(exc)) from exc


@router.get('/outgoing')
async def outgoing(authorization: str | None = Header(default=None)):
    try:
        await bank.current_user(authorization)
        return await bank.aa_outgoing(authorization)
    except bank.BankError as exc:
        translate(exc)


@router.get('/inbox')
async def inbox(authorization: str | None = Header(default=None)):
    try:
        await bank.current_user(authorization)
        return await bank.aa_inbox(authorization)
    except bank.BankError as exc:
        translate(exc)


@router.get('/collections/{collection_id}')
async def collection(collection_id: str, authorization: str | None = Header(default=None)):
    try:
        await bank.current_user(authorization)
        return await bank.aa_get(collection_id, authorization)
    except bank.BankError as exc:
        translate(exc)


@router.post('/items/{item_id}/payment/prepare')
async def prepare_payment(item_id: str, body: Action,
                          authorization: str | None = Header(default=None)):
    try:
        await bank.current_user(authorization)
        return await bank.aa_payment_prepare(item_id, body.requestId, authorization)
    except bank.BankError as exc:
        translate(exc)


@router.post('/items/{item_id}/otp/request')
async def request_otp(item_id: str, authorization: str | None = Header(default=None)):
    try:
        await bank.current_user(authorization)
        return await bank.aa_payment_otp(item_id, authorization)
    except bank.BankError as exc:
        translate(exc)


@router.post('/items/{item_id}/payment/confirm')
async def confirm_payment(item_id: str, body: PaymentConfirm,
                          authorization: str | None = Header(default=None)):
    if body.confirmed is not True:
        raise HTTPException(422, '付款人必须明确同意。')
    try:
        await bank.current_user(authorization)
        return await bank.aa_payment_confirm(item_id, body.requestId, body.otpCode, authorization)
    except bank.BankError as exc:
        translate(exc)


@router.post('/items/{item_id}/decline')
async def decline_payment(item_id: str, body: Action,
                          authorization: str | None = Header(default=None)):
    try:
        await bank.current_user(authorization)
        return await bank.aa_decline(item_id, body.requestId, authorization)
    except bank.BankError as exc:
        translate(exc)


@router.get('/items/{item_id}/payment')
async def payment_status(item_id: str, authorization: str | None = Header(default=None)):
    try:
        await bank.current_user(authorization)
        return await bank.aa_payment_get(item_id, authorization)
    except bank.BankError as exc:
        translate(exc)
