"""FAKE BANK for local Day 3 development only. No balances ever change.

Mock token is PUBLIC and NOT suitable for production authentication. Do not expose
this mock server to the Internet. Run only on 127.0.0.1:8080.
"""
from decimal import Decimal
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="FAKE BANK — LOCAL MOCK — NO MONEY MOVES")
MOCK_TOKEN = "Bearer mock-day3-token"
ORDERS: dict[str, dict] = {}


class MockPrepare(BaseModel):
    payeeId: int = Field(gt=0)
    amount: str
    requestId: str
    remark: str = ""


@app.get("/api/demo/balance")
def balance():
    return {"userName": "张小明", "accountNoMasked": "****6688", "balance": "12580.50", "currency": "CNY", "source": "mock"}


@app.get("/api/demo/transactions")
def transactions():
    return [
        {"id": 1, "direction": "IN", "amount": "8000.00", "category": "工资", "merchantName": "公司", "description": "十月工资", "occurredAt": "2026-10-03 09:00:00"},
        {"id": 2, "direction": "OUT", "amount": "35.00", "category": "餐饮", "merchantName": "美团外卖", "description": "午餐", "occurredAt": "2026-10-05 12:00:00"},
        {"id": 3, "direction": "OUT", "amount": "69.00", "category": "购物", "merchantName": "京东", "description": "生活用品", "occurredAt": "2026-10-06 19:00:00"},
        {"id": 4, "direction": "OUT", "amount": "25.00", "category": "订阅", "merchantName": "视频会员", "description": "会员自动扣费", "occurredAt": "2026-10-08 08:00:00"},
    ]


@app.get("/api/demo/payees")
def payees():
    return [{"id": 1, "payeeName": "李四", "payeeAccountMasked": "****5291"}, {"id": 2, "payeeName": "王五", "payeeAccountMasked": "****8806"}]


@app.get("/api/demo/subscriptions")
def subscriptions():
    return [
        {"id": 1, "merchantName": "视频会员", "amount": "25.00", "billingCycle": "MONTHLY", "status": "ACTIVE", "nextPayDate": "2026-11-08"},
        {"id": 2, "merchantName": "音乐会员", "amount": "15.00", "billingCycle": "MONTHLY", "status": "ACTIVE", "nextPayDate": "2026-11-12"},
    ]


@app.post("/api/transfers/prepare")
def prepare(request: MockPrepare, authorization: str | None = Header(default=None)):
    if authorization != MOCK_TOKEN:
        raise HTTPException(status_code=401, detail="本地模拟令牌错误")
    payee = next((p for p in payees() if p["id"] == request.payeeId), None)
    if not payee:
        raise HTTPException(status_code=404, detail="收款人不存在")
    try:
        amount = Decimal(request.amount)
    except Exception:
        raise HTTPException(status_code=400, detail="金额格式错误")
    if amount <= 0 or amount > Decimal("1000000.00") or amount.as_tuple().exponent < -2:
        raise HTTPException(status_code=400, detail="金额越界")
    if request.requestId in ORDERS:
        existing = ORDERS[request.requestId]
        if existing["amount"] != str(amount.quantize(Decimal('0.01'))) or existing["payeeId"] != request.payeeId:
            raise HTTPException(status_code=409, detail="幂等键与不同订单参数冲突")
        return {k: v for k, v in existing.items() if k != "payeeId"}
    order = {
        "orderId": f"MOCK-{len(ORDERS) + 1001}",
        "payeeName": payee["payeeName"],
        "accountMasked": payee["payeeAccountMasked"],
        "amount": str(amount.quantize(Decimal('0.01'))),
        "riskLevel": "YELLOW" if amount <= 1000 else "RED",  # illustrative, NOT cumulative or bank policy
        "status": "PENDING_APPROVAL",
        "payeeId": request.payeeId,
    }
    ORDERS[request.requestId] = order
    return {k: v for k, v in order.items() if k != "payeeId"}
