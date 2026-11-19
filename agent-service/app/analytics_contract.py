"""D4: validate the two Java analytics contracts without model or database I/O."""
from datetime import datetime
from decimal import Decimal, InvalidOperation
import re


class AnalyticsContractError(ValueError):
    pass


def valid_year(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9]{4}', value) is not None and int(value) >= 1000


def valid_month(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9]{4}-(0[1-9]|1[0-2])', value) is not None and int(value[:4]) >= 1000


def explicit_annual_year(message):
    """An annual expression, not just the year part of a monthly expression."""
    if not isinstance(message, str):
        return None
    values = set(re.findall(r'(?<![0-9])([0-9]{4})\s*年(?!\s*[0-9]{1,2}\s*月)', message))
    return next(iter(values)) if len(values) == 1 else None


def _require(ok, field):
    if not ok:
        raise AnalyticsContractError(f'银行分析响应字段不合法：{field}')


def _amount(value, field, *, nonnegative=True):
    _require(type(value) in (int, float, Decimal), field)
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise AnalyticsContractError(f'银行分析金额不合法：{field}') from exc
    _require(result.is_finite() and (not nonnegative or result >= 0), field)
    return result


def _count(value, field, minimum=0):
    _require(type(value) is int and value >= minimum, field)
    return value


def _date(value, field):
    _require(isinstance(value, str), field)
    try:
        _require('T' in value, field)
        dt = datetime.fromisoformat(value)
    except (ValueError, TypeError) as exc:
        raise AnalyticsContractError(f'银行分析时间不合法：{field}') from exc
    _require(dt.tzinfo is None, field)
    return dt


def _base(data, requested, field):
    _require(isinstance(data, dict), 'object')
    _require(data.get(field) == requested, field)
    _require(data.get('currency') == 'CNY', 'currency')
    _require(data.get('source') == 'mysql', 'source')
    start = _date(data.get('periodStart'), 'periodStart')
    end = _date(data.get('periodEndExclusive'), 'periodEndExclusive')
    _require(start <= end, 'period')
    return start, end


def validate_annual_report(data, year):
    _require(valid_year(year), 'year')
    start, end = _base(data, year, 'year')
    y = int(year)
    _require(start == datetime(y, 1, 1), 'periodStart')
    mode = data.get('periodType')
    _require(mode in ('YEAR_TO_DATE', 'FULL_YEAR'), 'periodType')
    if mode == 'FULL_YEAR':
        _require(y < 9999 and end == datetime(y+1, 1, 1), 'periodEndExclusive')
        n = 12
    else:
        _require(end.year == y, 'periodEndExclusive')
        n = end.month
    for name in ('totalIncome', 'totalExpense', 'netCashFlow'):
        _amount(data.get(name), name, nonnegative=name != 'netCashFlow')
    categories = data.get('categories')
    _require(isinstance(categories, list), 'categories')
    names = set()
    for cat in categories:
        _require(isinstance(cat, dict), 'category')
        name = cat.get('name')
        _require(isinstance(name, str) and bool(name.strip()) and name not in names, 'category.name')
        names.add(name)
        _amount(cat.get('amount'), 'category.amount')
        _count(cat.get('count'), 'category.count', 1)
    rows = data.get('monthlyBreakdown')
    _require(isinstance(rows, list) and len(rows) == n, 'monthlyBreakdown')
    for i, row in enumerate(rows, 1):
        _require(isinstance(row, dict) and row.get('month') == f'{year}-{i:02d}', 'monthlyBreakdown.month')
        _amount(row.get('totalIncome'), 'monthlyBreakdown.totalIncome')
        _amount(row.get('totalExpense'), 'monthlyBreakdown.totalExpense')
    return data


def validate_anomaly_report(data, month):
    _require(valid_month(month), 'month')
    start, end = _base(data, month, 'month')
    y, m = map(int, month.split('-'))
    _require(start == datetime(y, m, 1), 'periodStart')
    next_month = datetime(y + (m == 12), m % 12 + 1, 1) if not (y == 9999 and m == 12) else datetime.max
    _require(end <= next_month, 'periodEndExclusive')
    scanned = _count(data.get('scannedCount'), 'scannedCount')
    count = _count(data.get('anomalyCount'), 'anomalyCount')
    _require(scanned <= 10000 and count <= 2*scanned, 'scan limits')
    _require(_amount(data.get('largeOutflowThreshold'), 'largeOutflowThreshold') == Decimal('1000.00'), 'largeOutflowThreshold')
    _require(_count(data.get('duplicateWindowMinutes'), 'duplicateWindowMinutes') == 10, 'duplicateWindowMinutes')
    rows = data.get('items')
    _require(isinstance(rows, list) and len(rows) == count, 'items')
    seen = set()
    for row in rows:
        _require(isinstance(row, dict), 'item')
        tx = _count(row.get('transactionId'), 'transactionId', 1)
        rule = row.get('ruleCode')
        _require(rule in ('LARGE_OUTFLOW', 'POSSIBLE_DUPLICATE'), 'ruleCode')
        _require((tx, rule) not in seen, 'duplicate event')
        seen.add((tx, rule))
        amount = _amount(row.get('amount'), 'amount')
        _require(isinstance(row.get('category'), str), 'category')
        merchant = row.get('merchantName')
        _require(merchant is None or isinstance(merchant, str), 'merchantName')
        occurred = _date(row.get('occurredAt'), 'occurredAt')
        _require(start <= occurred < end, 'occurredAt')
        _require(isinstance(row.get('reason'), str) and bool(row['reason'].strip()), 'reason')
        related = row.get('relatedTransactionId')
        if rule == 'LARGE_OUTFLOW':
            _require(amount >= Decimal('1000.00') and related is None, 'LARGE_OUTFLOW')
        else:
            _require(bool(merchant and merchant.strip()), 'merchantName')
            _require(_count(related, 'relatedTransactionId', 1) != tx, 'relatedTransactionId')
    _require(len({tx for tx, _ in seen}) <= scanned, 'scannedCount')
    return data
