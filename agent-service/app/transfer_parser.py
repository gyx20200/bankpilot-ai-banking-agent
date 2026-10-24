"""Limited Day 3/4 transfer extraction; not an LLM or production NLU.

Handles only one explicit saved payee + arabic-number amount. Unclear expressions
must be completed by the user. NEVER executes funds.
"""
import re
from decimal import Decimal
from dataclasses import dataclass

DISALLOWED = ("不用确认", "免验证", "无需验证", "跳过验证", "忽略权限", "不要转", "别转", "取消转")
PATTERN = re.compile(
    r"(?:请|帮我|麻烦|麻烦帮我)?(?:给|向)(?P<name>[\u4e00-\u9fa5A-Za-z]{1,20})(?:转账?|打款|汇款)"
    r"(?P<amount>\d+(?:\.\d{1,2})?)?(?:元|块)?[。！!]?"
)
ALT = re.compile(
    r"(?:请|帮我|麻烦|麻烦帮我)?(?:转账?给|汇款给)(?P<name>[\u4e00-\u9fa5A-Za-z]{1,20})"
    r"(?P<amount>\d+(?:\.\d{1,2})?)?(?:元|块)?[。！!]?"
)
AMOUNT_RE = re.compile(r"(?:0|[1-9]\d{0,8})(?:\.\d{1,2})?\Z")


@dataclass(frozen=True)
class TransferIntent:
    payee_name: str
    amount: str | None


def parse_transfer(message: str) -> TransferIntent | None:
    text = "".join(message.strip().split())
    if any(p in text for p in DISALLOWED):
        return None
    if any(w in text for w in ("查询", "账单", "记录", "取消代扣", "同时")):
        return None
    for regex in (PATTERN, ALT):
        found = regex.fullmatch(text)
        if found:
            return TransferIntent(found.group("name"), found.group("amount"))
    return None


def normalize_amount(value: str) -> str:
    if not isinstance(value, str) or not AMOUNT_RE.fullmatch(value.strip()):
        raise ValueError("金额格式无效，请输入 200 或 200.50（最多两位小数）。")
    number = Decimal(value.strip())
    if number <= 0 or number > Decimal("1000000.00"):
        raise ValueError("模拟单笔转账金额需在 0.01 到 1,000,000.00 元之间。")
    return f"{number:.2f}"
