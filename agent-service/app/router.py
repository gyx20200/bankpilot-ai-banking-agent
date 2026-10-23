"""Day 2 local intent router. Replace with LLM structured intent router on Day 5.

This is intentionally a read-only router: no user text can trigger a write.
"""

from typing import Literal

Intent = Literal["balance", "transactions", "payees", "subscriptions", "unsupported"]


def parse_intent(message: str) -> Intent:
    text = "".join(message.lower().split())
    if not text:
        return "unsupported"

    # Match more specific terms first. One intent per request in Day 2.
    if any(w in text for w in ("代扣", "订阅", "自动扣", "续费", "会员")):
        return "subscriptions"
    if any(w in text for w in ("收款人", "联系人", "转账对象", "常用朋友")):
        return "payees"
    if any(w in text for w in ("账单", "流水", "交易", "消费", "支出", "明细", "花了")):
        return "transactions"
    if any(w in text for w in ("余额", "还有多少钱", "有多少钱", "剩多少钱")):
        return "balance"
    return "unsupported"
