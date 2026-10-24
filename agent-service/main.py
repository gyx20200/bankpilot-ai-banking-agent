"""BankPilot Day 5 FastAPI gateway. No AI model gets payment execution tools.

Only explicit browser POST operations can call authorize/execute/cancel routes.
The Java bank backend MUST re-check authentication and all business permissions.
"""
from decimal import Decimal
from uuid import uuid4
from typing import Any
import logging
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from app.router import Intent, parse_intent
from app.transfer_parser import TransferIntent
from app import llm_router
from app.transfer_parser import parse_transfer, normalize_amount
from app import banking_client as bank

app = FastAPI(title="BankPilot Agent Day 5", version="0.5.0")
logger = logging.getLogger("bankpilot.gateway")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=300)
    requestId: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{8,64}$")


class PrepareRequest(BaseModel):
    payeeId: int = Field(gt=0)
    amount: str = Field(min_length=1, max_length=20)
    requestId: str = Field(pattern=r"^[A-Za-z0-9_-]{8,64}$")
    remark: str = Field(default="", max_length=80)


class ApprovalRequest(BaseModel):
    confirmation: bool
    otpCode: str | None = Field(default=None, max_length=20)
    requestId: str = Field(pattern=r"^[A-Za-z0-9_-]{8,64}$")


class ActionRequest(BaseModel):
    requestId: str = Field(pattern=r"^[A-Za-z0-9_-]{8,64}$")


class Response(BaseModel):
    reply: str
    intent: Intent
    action: str | None = None
    data: Any = None
    source: str = "none"
    requestId: str
    routing: str = "rules"


def bank_source(): return "mock-api" if bank.BANK_MODE == "mock" else "bank-api"


def _fail(e: bank.BankError):
    logger.warning("bank_call_rejected status=%s", e.status)
    raise HTTPException(status_code=e.status, detail=str(e)) from e


def _response(action, payload, reply, request_id):
    return Response(reply=reply, intent="transfer", action=action, data=payload,
                    source=bank_source(), requestId=request_id)


@app.get("/health")
@app.get("/api/agent/health")
async def health():
    return {"status": "ok", "mode": "llm-day5" if llm_router.enabled() else "rules-day5",
            "bankMode": bank.BANK_MODE, "modelConfigured": llm_router.configured() if llm_router.enabled() else False,
            "modelName": llm_router.model_name()}


@app.post("/api/agent/chat", response_model=Response)
async def chat(req: ChatRequest, authorization: str | None = Header(default=None)):
    request_id = req.requestId or uuid4().hex
    # A model may classify intent and extract candidate parameters, but has no
    # authorization or execute tool. Refuse explicit bypass requests up front.
    forbidden = ("跳过验证", "免验证", "不用确认", "忽略权限", "不需要确认", "绕过风控", "直接扣款", "不要转", "别转", "万元", "亿元")
    if any(word in req.message for word in forbidden):
        return Response(reply="无法跳过银行权限控制；操作未执行。", intent="unsupported", requestId=request_id)
    routing = "llm" if llm_router.enabled() else "rules"
    parsed = None
    if llm_router.enabled():
        try:
            decision = await llm_router.choose_tool(req.message)
        except llm_router.LLMRouterError as ex:
            raise HTTPException(status_code=502, detail=str(ex)) from ex
        selected = {"get_balance":"balance", "get_transactions":"transactions", "get_payees":"payees",
                    "get_subscriptions":"subscriptions", "prepare_transfer":"transfer"}
        intent = selected.get(decision.name, "unsupported") if decision else "unsupported"
        if intent == "transfer":
            parsed = TransferIntent(payee_name=decision.arguments["payee_name"], amount=decision.arguments["amount"])
    else:
        intent = parse_intent(req.message)
        if intent == "transfer":
            parsed = parse_transfer(req.message)
    logger.info("chat_intent=%s routing=%s request_id=%s", intent, routing, request_id)
    if intent == "unsupported":
        return Response(reply="目前支持查询余额、流水、收款人、代扣和单笔转账建单；复杂表达或未经授权的操作无法执行。",
                        intent=intent, requestId=request_id, routing=routing)
    try:
        if intent == "balance":
            data = await bank.balance(authorization)
            return Response(reply=f"模拟账户当前余额 ¥{Decimal(str(data['balance'])):,.2f}。", intent=intent, data=data,
                            source=bank_source(), requestId=request_id, routing=routing)
        if intent == "transactions":
            data = await bank.transactions(authorization)
            return Response(reply=f"已查询 {len(data)} 条交易记录。", intent=intent, data=data, source=bank_source(), requestId=request_id, routing=routing)
        if intent == "payees":
            data = await bank.payees(authorization)
            return Response(reply=f"已查询 {len(data)} 位常用收款人。", intent=intent, data=data, source=bank_source(), requestId=request_id, routing=routing)
        if intent == "subscriptions":
            data = await bank.subscriptions(authorization)
            return Response(reply=f"已查询 {len(data)} 条代扣协议。", intent=intent, data=data, source=bank_source(), requestId=request_id)

        if parsed is None:
            return Response(reply="无法确定收款人或金额。", intent="transfer", requestId=request_id, routing=routing)
        saved_payees = await bank.payees(authorization)
        matches = [p for p in saved_payees if p.get("payeeName") == parsed.payee_name]
        try:
            amount = normalize_amount(parsed.amount) if parsed.amount is not None else None
        except ValueError:
            amount = None
        if len(matches) != 1 or amount is None or not authorization:
            resp = _response("needs_input", {
                "payees": saved_payees, "payeeName": parsed.payee_name, "amount": amount or "", "requestId": request_id,
            }, "请确认收款人、填写有效金额，并提供银行登录凭证。仅提交转账建单请求。", request_id)
            resp.routing = routing
            return resp
        result = await bank.prepare_transfer(int(matches[0]["id"]), amount, request_id, authorization)
        resp = _response("prepared", result, "待确认转账订单已创建；尚未发生扣款。", request_id)
        resp.routing = routing
        return resp
    except (ValueError, TypeError):
        raise HTTPException(status_code=502, detail="银行查询返回数据格式有误。")
    except bank.BankError as ex:
        _fail(ex)


@app.post("/api/agent/transfers/prepare", response_model=Response)
async def prepare(req: PrepareRequest, authorization: str | None = Header(default=None)):
    try:
        amount = normalize_amount(req.amount)
    except ValueError as ex:
        raise HTTPException(status_code=422, detail=str(ex)) from ex
    try:
        saved_payees = await bank.payees(authorization)
        if not any(p.get("id") == req.payeeId for p in saved_payees):
            raise HTTPException(status_code=400, detail="请选择本人常用收款人列表中的有效账户。")
        order = await bank.prepare_transfer(req.payeeId, amount, req.requestId, authorization, req.remark)
        return _response("prepared", order, "待确认转账订单已创建；尚未发生扣款。", req.requestId)
    except bank.BankError as ex: _fail(ex)


@app.get("/api/agent/transfers/{order_id}", response_model=Response)
async def status(order_id: str, authorization: str | None = Header(default=None)):
    try:
        order = await bank.get_order(order_id, authorization)
        return _response("status", order, "已从银行服务读取最新订单状态。", uuid4().hex)
    except bank.BankError as ex: _fail(ex)


@app.post("/api/agent/transfers/{order_id}/authorize", response_model=Response)
async def authorize(order_id: str, req: ApprovalRequest, authorization: str | None = Header(default=None)):
    if req.confirmation is not True:
        raise HTTPException(status_code=400, detail="必须由用户明确确认订单信息。")
    try:
        order = await bank.authorize_transfer(order_id, authorization, True, req.otpCode, req.requestId)
        if order["status"] != "AUTHORIZED":
            raise HTTPException(status_code=409, detail="授权尚未完成，请查询订单状态。")
        return _response("authorized", order, "银行后端确认授权通过。尚未执行转账。", req.requestId)
    except bank.BankError as ex: _fail(ex)


@app.post("/api/agent/transfers/{order_id}/execute", response_model=Response)
async def execute(order_id: str, req: ActionRequest, authorization: str | None = Header(default=None)):
    try:
        order = await bank.execute_transfer(order_id, authorization, req.requestId)
        return _response("executed", order,
                         "银行系统确认模拟转账成功。" if order["status"] == "SUCCESS" else "请查看银行订单状态。", req.requestId)
    except bank.BankError as ex: _fail(ex)


@app.post("/api/agent/transfers/{order_id}/cancel", response_model=Response)
async def cancel(order_id: str, req: ActionRequest, authorization: str | None = Header(default=None)):
    try:
        order = await bank.cancel_transfer(order_id, authorization, req.requestId)
        return _response("cancelled", order, "订单取消结果已从银行后端返回。", req.requestId)
    except bank.BankError as ex: _fail(ex)
