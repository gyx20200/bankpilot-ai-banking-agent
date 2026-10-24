from typing import Literal
from app.transfer_parser import parse_transfer
Intent = Literal["balance", "transactions", "payees", "subscriptions", "transfer", "unsupported"]


def parse_intent(message: str) -> Intent:
    text = "".join(message.lower().split())
    if not text: return "unsupported"
    if parse_transfer(message): return "transfer"
    if any(w in text for w in ("跳过验证", "免验证", "不用确认", "忽略权限", "不要转")):
        return "unsupported"
    if any(w in text for w in ("代扣", "订阅", "自动扣", "续费", "会员")): return "subscriptions"
    if any(w in text for w in ("收款人", "联系人", "转账对象")): return "payees"
    if any(w in text for w in ("账单", "流水", "交易", "消费", "支出", "明细")): return "transactions"
    if any(w in text for w in ("余额", "还有多少钱", "剩多少钱")): return "balance"
    return "unsupported"
