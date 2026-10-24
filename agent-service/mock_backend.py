"""Optional local mock for teammate independent UI work; NOT MySQL/Java.

Run this ONLY when the real Java backend is unavailable. Never present mock data
as real account data. No mutation endpoints are provided.
"""

from fastapi import FastAPI

app = FastAPI(title="FAKE BANK — LOCAL MOCK ONLY")

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
    return [{"id": 1, "payeeName": "李四", "payeeAccountMasked": "****5291"}]

@app.get("/api/demo/subscriptions")
def subscriptions():
    return [
        {"id": 1, "merchantName": "视频会员", "amount": "25.00", "billingCycle": "MONTHLY", "status": "ACTIVE", "nextPayDate": "2026-11-08"},
        {"id": 2, "merchantName": "音乐会员", "amount": "15.00", "billingCycle": "MONTHLY", "status": "ACTIVE", "nextPayDate": "2026-11-12"},
    ]
