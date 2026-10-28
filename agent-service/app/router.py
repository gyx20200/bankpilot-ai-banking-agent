import re
from typing import Literal
from app.transfer_parser import parse_transfer
Intent = Literal["balance", "transactions", "payees", "subscriptions", "monthly_analytics", "transfer", "unsupported"]


def extract_month(message: str) -> str | None:
    """Only explicit year-month values; do not invent a month from ambiguous text."""
    chinese = re.search(r"(?<!\d)(\d{4})\s*年\s*(\d{1,2})\s*月", message)
    iso = re.search(r"(?<!\d)(\d{4})-(\d{2})(?![-\d])", message)
    match = chinese or iso
    if match is None:
        return None
    year, month = int(match.group(1)), int(match.group(2))
    if not (1 <= year <= 9999 and 1 <= month <= 12):
        return None
    return f"{year:04d}-{month:02d}"


def parse_intent(message: str) -> Intent:
    text = "".join(message.lower().split())
    if not text: return "unsupported"
    # A monthly *analysis* is different from asking for recent transaction records.
    if (any(word in text for word in ("分析", "统计", "汇总", "收支", "净现金流", "月报", "财务报告"))
            and ("月" in text or re.search(r"\d{4}-\d{2}", text))):
        return "monthly_analytics"
    if parse_transfer(message): return "transfer"
    if any(w in text for w in ("跳过验证", "免验证", "不用确认", "忽略权限", "不要转")):
        return "unsupported"
    if any(w in text for w in ("代扣", "订阅", "自动扣", "续费", "会员")): return "subscriptions"
    if any(w in text for w in ("收款人", "联系人", "转账对象")): return "payees"
    if any(w in text for w in ("账单", "流水", "交易", "消费", "支出", "明细")): return "transactions"
    if any(w in text for w in ("余额", "还有多少钱", "剩多少钱")): return "balance"
    return "unsupported"
