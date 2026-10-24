"""BankPilot Day 3: read tools plus safe transfer ORDER PREPARATION only.

No execute/approve endpoints. No LLM yet; does not claim payments are done.
"""
from typing import Any
from uuid import uuid4
from decimal import Decimal, InvalidOperation
import logging

from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel, Field

from app.router import Intent, parse_intent
from app.transfer_parser import parse_transfer, normalize_amount
from app.banking_client import (
    BankingServiceError, BANK_API_MODE,
    get_balance, get_transactions, get_payees, get_subscriptions, prepare_transfer,
)

app = FastAPI(title="BankPilot Agent Gateway - Day 3", version="0.3.0")
log = logging.getLogger("bankpilot.agent")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=300)
    requestId: str | None = Field(default=None, min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


class PrepareRequest(BaseModel):
    payeeId: int = Field(gt=0)
    amount: str = Field(min_length=1, max_length=20)
    requestId: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    remark: str = Field(default="", max_length=80)


class ChatResponse(BaseModel):
    reply: str
    intent: Intent
    action: str | None = None
    data: Any = None
    source: str = "none"
    requestId: str


def format_money(value: Any) -> str:
    try:
        return f"{Decimal(str(value)):,.2f}"
    except (InvalidOperation, ValueError):
        return "金额格式异常"


def source_name() -> str:
    return "mock-api" if BANK_API_MODE == "mock" else "bank-api"


def safe_error(exc: BankingServiceError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))


async def checked_payee(payee_id: int, authorization: str | None):
    """Convenience cross-check only; Java MUST enforce ownership again."""
    payees = await get_payees(authorization)
    match = [p for p in payees if isinstance(p, dict) and p.get("id") == payee_id]
    if not match:
        raise HTTPException(status_code=400, detail="请选择当前用户常用收款人中的有效账户。")
    return match[0]


@app.get("/health")
@app.get("/api/agent/health")
async def health():
    return {"status": "ok", "service": "agent-gateway", "mode": "rules-day3-prepare-only", "bankMode": BANK_API_MODE}


@app.post("/api/agent/transfers/prepare", response_model=ChatResponse)
async def prepare(request: PrepareRequest, authorization: str | None = Header(default=None)):
    request_id = request.requestId
    try:
        amount = normalize_amount(request.amount)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        await checked_payee(request.payeeId, authorization)
        order = await prepare_transfer(request.payeeId, amount, request_id, authorization, request.remark)
    except BankingServiceError as exc:
        raise safe_error(exc) from exc
    log.info("request_id=%s intent=transfer action=prepared", request_id)
    return ChatResponse(
        reply="已创建待确认转账订单。请核对收款人和金额；尚未扣款或转账。",
        intent="transfer", action="prepared", data=order, source=source_name(), requestId=request_id,
    )


@app.post("/api/agent/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, authorization: str | None = Header(default=None)):
    request_id = request.requestId or uuid4().hex
    intent = parse_intent(request.message)
    log.info("request_id=%s intent=%s", request_id, intent)  # No raw user text or full account data.

    if intent == "unsupported":
        return ChatResponse(
            reply="目前支持余额、交易、常用收款人、订阅查询，以及‘给李四转200元’创建待确认订单。不会跳过授权。",
            intent=intent, requestId=request_id,
        )

    try:
        if intent == "transfer":
            parsed = parse_transfer(request.message)
            assert parsed is not None
            payees = await get_payees(authorization)
            matches = [p for p in payees if isinstance(p, dict) and p.get("payeeName") == parsed.payee_name]
            try:
                amt = normalize_amount(parsed.amount) if parsed.amount is not None else None
                amount_error = None
            except ValueError as exc:
                amt, amount_error = None, str(exc)
            if len(matches) != 1 or amt is None:
                if not payees:
                    info = "当前没有可用的常用收款人，请先在银行系统中添加。"
                elif len(matches) > 1:
                    info = "收款人重名，请从列表中明确选择正确账户。"
                elif len(matches) == 0:
                    info = f"未找到名为“{parsed.payee_name}”的常用收款人，请明确选择。"
                else:
                    info = "请输入需要转账的金额。"
                if amount_error:
                    info = amount_error
                return ChatResponse(
                    reply=f"{info}本阶段仅能创建待确认订单，不会扣款。",
                    intent="transfer", action="needs_input",
                    data={"payees": payees, "payeeName": parsed.payee_name, "amount": amt or "", "requestId": request_id},
                    source=source_name(), requestId=request_id,
                )
            if not authorization:
                # UI form can re-submit after user obtains a demo login token.
                return ChatResponse(
                    reply="已找到收款人和金额。创建订单前，需要先提供银行后端签发的测试登录凭证。",
                    intent="transfer", action="needs_input",
                    data={"payees": payees, "payeeName": parsed.payee_name, "amount": amt, "requestId": request_id},
                    source=source_name(), requestId=request_id,
                )
            order = await prepare_transfer(matches[0]["id"], amt, request_id, authorization)
            return ChatResponse(
                reply="已创建待确认转账订单。尚未扣款，请查看下方订单预览。",
                intent="transfer", action="prepared", data=order, source=source_name(), requestId=request_id,
            )
        if intent == "balance":
            data = await get_balance(authorization)
            reply = f"{data.get('userName', '您好')}，您的模拟账户 {data.get('accountNoMasked', '****')} 当前余额为 ¥{format_money(data['balance'])}。"
        elif intent == "transactions":
            data = await get_transactions(authorization)
            reply = f"从银行接口查询到 {len(data)} 条交易流水（最多 100 条），详见下方列表。"
        elif intent == "payees":
            data = await get_payees(authorization)
            reply = f"当前共有 {len(data)} 位常用收款人，详见下方列表。"
        else:
            data = await get_subscriptions(authorization)
            reply = f"查询到 {len(data)} 条代扣协议，本阶段仅支持查询。"
    except BankingServiceError as exc:
        log.warning("request_id=%s backend_status=%s", request_id, exc.status_code)
        raise safe_error(exc) from exc
    return ChatResponse(reply=reply, intent=intent, data=data, source=source_name(), requestId=request_id)
