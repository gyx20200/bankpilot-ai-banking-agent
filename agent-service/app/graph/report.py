"""Deterministic report from simulated transactions. Do not ask an LLM to sum money."""
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo


def build_report(rows: list[dict]) -> dict:
    today = datetime.now(ZoneInfo('Asia/Shanghai')).date()
    start = today - timedelta(days=29)
    totals: dict[str, Decimal] = {}
    count = 0
    for item in rows:
        if item.get('direction') != 'OUT':
            continue
        when = str(item.get('occurredAt', item.get('occurred_at', '')))
        try:
            day = datetime.fromisoformat(when.replace('Z', '+00:00')).date()
            amount = Decimal(str(item.get('amount')))
        except (ValueError, TypeError, InvalidOperation):
            continue
        if not (start <= day <= today) or amount <= 0 or not amount.is_finite():
            continue
        category = str(item.get('category') or '其他')
        totals[category] = totals.get(category, Decimal('0')) + amount
        count += 1
    total = sum(totals.values(), Decimal('0'))
    return {
        'period': f'{start.isoformat()} ~ {today.isoformat()}',
        'totalExpense': f'{total:.2f}',
        'transactionCount': count,
        'categories': [
            {'name': k, 'amount': f'{v:.2f}'}
            for k, v in sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
        ],
    }


def find_candidate(text: str, subscriptions: list[dict]) -> dict | None:
    if not any(word in text for word in ('取消', '停掉', '停止代扣', '关闭代扣')):
        return None
    active = [s for s in subscriptions if s.get('status') == 'ACTIVE'
              and s.get('merchantName') and str(s['merchantName']) in text]
    if len(active) != 1:
        return None  # Ambiguous or missing; do not guess which authorization to cancel.
    candidate = active[0]
    return {'id': candidate['id'], 'merchantName': candidate['merchantName'],
            'amount': str(candidate['amount']), 'billingCycle': candidate['billingCycle']}
