"""Safe transfer preparation for Day 6, without bank authorization/execution."""

from decimal import Decimal
from typing import Any

from app import banking_client as bank
from app.transfer_parser import normalize_amount


def match_registered_payee(payees: Any, name: str, amount: str) -> tuple[str, dict]:
    """Require a unique, exact saved-payee match. Never infer an account ID."""
    if not isinstance(payees, list) or not isinstance(name, str):
        return 'PAYEE_INVALID', {}
    matches = [p for p in payees if isinstance(p, dict)
               and str(p.get('payeeName', '')).strip() == name.strip()]
    if not matches:
        return 'PAYEE_NOT_FOUND', {}
    if len(matches) != 1:
        return 'PAYEE_AMBIGUOUS', {}
    payee = matches[0]
    if type(payee.get('id')) is not int or payee['id'] <= 0:
        return 'PAYEE_INVALID', {}
    try:
        safe_amount = normalize_amount(amount)
    except (TypeError, ValueError):
        return 'AMOUNT_INVALID', {}
    return 'PAYEE_FOUND', {
        'id': payee['id'],
        'payeeName': payee['payeeName'],
        'accountMasked': str(payee.get('payeeAccountMasked', '')),
        'amount': safe_amount,
    }


async def prepare_verified_transfer(candidate: dict, request_id: str, bearer: str) -> dict:
    """Only create a pending order; enforce that response matches selected payee."""
    remark = candidate.get('remark', '')
    if remark:
        order = await bank.prepare_transfer(
            candidate['id'], candidate['amount'], request_id, bearer, remark=remark)
    else:
        order = await bank.prepare_transfer(
            candidate['id'], candidate['amount'], request_id, bearer)
    try:
        correct = (
                str(order['payeeName']).strip() == candidate['payeeName']
                and Decimal(str(order['amount'])) == Decimal(candidate['amount'])
                and str(order['accountMasked']) == candidate['accountMasked']
                and (not remark or order.get('remark') == remark)
                and order['status'] == 'PENDING_APPROVAL'
                and order['riskLevel'] in ('YELLOW', 'RED')
                and bool(order['orderId'])
        )
    except (KeyError, TypeError, ValueError, ArithmeticError):
        correct = False
    if not correct:
        raise bank.BankError('银行转账建单响应与收款人或金额不一致，请查询订单状态。', 409)
    return order
