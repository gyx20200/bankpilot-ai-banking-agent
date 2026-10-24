"""Deliberately limited deterministic Day 3 transfer-intent parser.

Not an LLM. The backend MUST revalidate payee ownership, limits and permissions.
Never derives a payee account number from raw user text.
"""
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

# Avoid accidentally preparing orders based on negated/bypass instructions.
BLOCKED_PHRASES = ("不要转", "别转", "取消转", "不用确认", "无需确认", "跳过验证", "免验证", "忽略权限")
FORMATS = [
    re.compile(r"(?:请|帮我|麻烦|麻烦帮我)?(?:给|向)(?P<name>[\u4e00-\u9fa5A-Za-z0-9]{1,20})(?:转账?|打款|汇款)(?P<amount>[0-9]+(?:\.[0-9]{1,2})?)?(?:元|块)?[。！!]?"),
    re.compile(r"(?:请|帮我|麻烦|麻烦帮我)?(?:转账?给|汇款给)(?P<name>[\u4e00-\u9fa5]{1,20})(?P<amount>[0-9]+(?:\.[0-9]{1,2})?)?(?:元|块)?[。！!]?"),
]
AMOUNT_RE = re.compile(r"^(?:0|[1-9][0-9]{0,8})(?:\.[0-9]{1,2})?$")


@dataclass(frozen=True)
class TransferIntent:
    payee_name: str
    amount: str | None


def parse_transfer(message: str) -> TransferIntent | None:
    text = "".join(message.split())
    if any(p in text for p in BLOCKED_PHRASES):
        return None
    # Day 3 supports one operation per chat turn, not compound instructions.
    if any(p in text for p in ("查询", "账单", "交易记录", "消费记录", "取消代扣")):
        return None
    for regex in FORMATS:
        match = regex.fullmatch(text)
        if match:
            return TransferIntent(match.group('name'), match.group('amount'))
    return None


def normalize_amount(value: str) -> str:
    if not isinstance(value, str) or not AMOUNT_RE.fullmatch(value.strip()):
        raise ValueError("请输入正确金额，例如 200 或 200.50（最多两位小数）。")
    try:
        number = Decimal(value.strip())
    except InvalidOperation as exc:
        raise ValueError("金额格式错误。") from exc
    if number <= 0 or number > Decimal("1000000.00"):
        raise ValueError("演示版单笔金额必须在 0.01 至 1,000,000.00 元之间。")
    return f"{number:.2f}"
