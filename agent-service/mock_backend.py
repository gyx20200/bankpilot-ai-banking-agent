"""Local-only FAKE BANK for frontend/agent integration tests.

FIXED PUBLIC TEST TOKEN + OTP; NEVER DEPLOY. Does NOT authenticate real humans.
Balances and orders live only in process RAM and reset upon restart.
"""
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from threading import Lock
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel, Field

app = FastAPI(title="FAKE BANK — Day4 DEMO ONLY")
DEMO_TOKEN = "Bearer mock-day4-token"
DEMO_OTP = "246810"  # Only for demo; real backend must issue and verify expiring OTP.
_lock = Lock()
_payees = [
    {"id": 1, "payeeName": "李四", "payeeAccountMasked": "****5291"},
    {"id": 2, "payeeName": "王五", "payeeAccountMasked": "****8806"},
]


def reset_demo():
    """Tests may call this between scenarios; avoid in HTTP API."""
    global _balances, _orders_by_key, _orders_by_id, _history
    with _lock:
        _balances = {1: Decimal("12580.50"), 2: Decimal("5000.00"), 3: Decimal("3000.00")}
        _orders_by_key = {}
        _orders_by_id = {}
        _history = [
            {"id": 1, "direction": "IN", "amount": "8000.00", "category": "工资", "merchantName": "公司", "occurredAt": "2026-10-03 09:00:00"},
            {"id": 2, "direction": "OUT", "amount": "35.00", "category": "餐饮", "merchantName": "美团外卖", "occurredAt": "2026-10-05 12:00:00"},
            {"id": 3, "direction": "OUT", "amount": "69.00", "category": "购物", "merchantName": "京东", "occurredAt": "2026-10-06 19:00:00"},
            {"id": 4, "direction": "OUT", "amount": "25.00", "category": "订阅", "merchantName": "视频会员", "occurredAt": "2026-10-08 08:00:00"},
        ]


reset_demo()


def _auth(value: str | None):
    if value != DEMO_TOKEN:
        raise HTTPException(401, "Mock 登录凭证无效")


def _get_order(oid: str):
    obj = _orders_by_id.get(str(oid))
    if obj is None: raise HTTPException(404, "订单不存在")
    return obj


def _public(obj):
    return {key: obj[key] for key in (
        "orderId", "payeeName", "accountMasked", "amount", "riskLevel", "status"
    )} | ({"transferId": obj["transferId"], "balanceAfter": obj["balanceAfter"]} if obj.get("transferId") else {})


def _amount(raw):
    try:
        number = Decimal(raw)
    except (InvalidOperation, TypeError):
        raise HTTPException(422, "非法金额")
    if not number.is_finite() or number <= 0 or number > Decimal("1000000") or number.as_tuple().exponent < -2:
        raise HTTPException(422, "金额不合法")
    return number.quantize(Decimal("0.01"))


def _at_risk(obj):
    total = sum((Decimal(x["amount"]) for x in _orders_by_id.values()
                 if x["status"] not in ("CANCELLED", "FAILED", "LOCKED")
                 and x["createdDate"] == obj["createdDate"]), Decimal("0"))
    return "RED" if total > 1000 else "YELLOW"


class Prepare(BaseModel):
    payeeId: int = Field(gt=0)
    amount: str
    requestId: str = Field(min_length=8, max_length=64)
    remark: str = ""


class Approval(BaseModel):
    confirmation: bool
    otpCode: str | None = None
    requestId: str = Field(min_length=8, max_length=64)


class Action(BaseModel):
    requestId: str = Field(min_length=8, max_length=64)


@app.get("/api/demo/balance")
def balance():
    with _lock:
        value = str(_balances[1])
    return {"userName": "张小明", "accountNoMasked": "****6688", "balance": value, "currency": "CNY"}


@app.get("/api/demo/transactions")
def transactions():
    with _lock: return list(_history)


@app.get("/api/demo/payees")
def payees(): return _payees


@app.get("/api/demo/subscriptions")
def subscriptions():
    return [
        {"id": 1, "merchantName": "视频会员", "amount": "25.00", "billingCycle": "MONTHLY", "status": "ACTIVE", "nextPayDate": "2026-11-08"},
        {"id": 2, "merchantName": "音乐会员", "amount": "15.00", "billingCycle": "MONTHLY", "status": "ACTIVE", "nextPayDate": "2026-11-12"},
    ]


@app.post("/api/transfers/prepare")
def prepare(data: Prepare, authorization: str | None = Header(default=None)):
    _auth(authorization)
    amount = _amount(data.amount)
    payee = next((p for p in _payees if p["id"] == data.payeeId), None)
    if payee is None: raise HTTPException(404, "收款人不存在")
    with _lock:
        previous = _orders_by_key.get(data.requestId)
        if previous:
            if previous["payeeId"] != data.payeeId or Decimal(previous["amount"]) != amount or previous["remark"] != data.remark:
                raise HTTPException(409, "幂等键与不同参数冲突")
            return _public(previous)
        order = {
            "orderId": f"MOCK-{len(_orders_by_id) + 1001}",
            "payeeId": data.payeeId,
            "payeeName": payee["payeeName"],
            "accountMasked": payee["payeeAccountMasked"],
            "amount": str(amount),
            "riskLevel": "YELLOW", "status": "PENDING_APPROVAL",
            "remark": data.remark,
            "createdDate": date.today().isoformat(),
            "otpTries": 0, "strongVerified": False,
        }
        _orders_by_key[data.requestId] = order
        _orders_by_id[order["orderId"]] = order
        order["riskLevel"] = _at_risk(order)
        return _public(order)


@app.get("/api/transfers/{order_id}")
def order_status(order_id: str, authorization: str | None = Header(default=None)):
    _auth(authorization)
    with _lock: return _public(_get_order(order_id))


@app.post("/api/transfers/{order_id}/authorize")
def authorize(order_id: str, data: Approval, authorization: str | None = Header(default=None)):
    _auth(authorization)
    with _lock:
        order = _get_order(order_id)
        if order["status"] == "AUTHORIZED": return _public(order)
        if order["status"] != "PENDING_APPROVAL": raise HTTPException(409, "当前订单无法授权")
        if data.confirmation is not True: raise HTTPException(400, "缺少明确确认")
        # Never weaken previous risk, but allow upgrade as other orders arrive.
        if _at_risk(order) == "RED": order["riskLevel"] = "RED"
        if order["riskLevel"] == "RED":
            if data.otpCode != DEMO_OTP:
                order["otpTries"] += 1
                if order["otpTries"] >= 3: order["status"] = "LOCKED"
                raise HTTPException(403, "Mock OTP 验证失败")
            order["strongVerified"] = True
        order["status"] = "AUTHORIZED"
        return _public(order)


@app.post("/api/transfers/{order_id}/execute")
def execute(order_id: str, data: Action, authorization: str | None = Header(default=None)):
    _auth(authorization)
    with _lock:
        order = _get_order(order_id)
        if order["status"] == "SUCCESS": return _public(order)  # exact-once demo
        if order["status"] != "AUTHORIZED": raise HTTPException(409, "订单尚未授权")
        if _at_risk(order) == "RED" and not order["strongVerified"]:
            order["riskLevel"] = "RED"
            order["status"] = "PENDING_APPROVAL"
            raise HTTPException(409, "风险等级升级，需要重新强验证")
        amount = Decimal(order["amount"])
        if _balances[1] < amount:
            order["status"] = "FAILED"
            raise HTTPException(409, "账户余额不足")
        # In-process lock + Decimal demo only. Real banking MUST use a DB transaction.
        _balances[1] -= amount
        _balances[2 if order["payeeId"] == 1 else 3] += amount
        order["status"] = "SUCCESS"
        order["transferId"] = f"MOCK-TXN-{len(_history) + 1}"
        order["balanceAfter"] = str(_balances[1])
        _history.append({
            "id": len(_history) + 1, "direction": "OUT", "amount": order["amount"],
            "category": "转账", "merchantName": order["payeeName"],
            "occurredAt": datetime.now(timezone.utc).isoformat()
        })
        return _public(order)


@app.post("/api/transfers/{order_id}/cancel")
def cancel(order_id: str, data: Action, authorization: str | None = Header(default=None)):
    _auth(authorization)
    with _lock:
        order = _get_order(order_id)
        if order["status"] == "CANCELLED": return _public(order)
        if order["status"] not in ("PENDING_APPROVAL", "AUTHORIZED", "LOCKED"):
            raise HTTPException(409, "订单已执行或不可取消")
        order["status"] = "CANCELLED"
        return _public(order)
