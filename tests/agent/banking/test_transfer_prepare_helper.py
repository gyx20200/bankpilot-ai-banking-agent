import asyncio
import pytest
from app import banking_client as bank
from app.graph.transfer_prepare import match_registered_payee, prepare_verified_transfer

PAYEES = [
    {'id': 1, 'payeeName': '李四', 'payeeAccountMasked': '****5291'},
    {'id': 2, 'payeeName': '王五', 'payeeAccountMasked': '****8806'},
]


def test_unique_payee_match():
    status, candidate = match_registered_payee(PAYEES, '李四', '200')
    assert status == 'PAYEE_FOUND'
    assert candidate == {'id': 1, 'payeeName': '李四',
                         'accountMasked': '****5291', 'amount': '200.00'}


@pytest.mark.parametrize('name,rows,amount,expected', [
    ('张三', PAYEES, '200', 'PAYEE_NOT_FOUND'),
    ('李四', PAYEES + [PAYEES[0]], '200', 'PAYEE_AMBIGUOUS'),
    ('李四', [{'id': True, 'payeeName': '李四'}], '200', 'PAYEE_INVALID'),
    ('李四', PAYEES, '0', 'AMOUNT_INVALID'),
    ('李四', PAYEES, '1000000.01', 'AMOUNT_INVALID'),
    ('李四', PAYEES, 'abc', 'AMOUNT_INVALID'),
])
def test_fails_closed(name, rows, amount, expected):
    assert match_registered_payee(rows, name, amount)[0] == expected


def test_prepare_checks_response_fields(monkeypatch):
    _, target = match_registered_payee(PAYEES, '李四', '200')
    calls = []

    async def fake_prepare(payee_id, amount, request_id, bearer):
        calls.append((payee_id, amount, request_id, bearer))
        return {'orderId': 'MOCK-1001', 'payeeName': '李四', 'accountMasked': '****5291',
                'amount': '200.00', 'riskLevel': 'YELLOW', 'status': 'PENDING_APPROVAL'}

    monkeypatch.setattr(bank, 'prepare_transfer', fake_prepare)
    value = asyncio.run(prepare_verified_transfer(target, 'abcd1234', 'Bearer demo'))
    assert value['status'] == 'PENDING_APPROVAL'
    assert calls == [(1, '200.00', 'abcd1234', 'Bearer demo')]


def test_prepare_does_not_accept_mismatched_amount(monkeypatch):
    _, target = match_registered_payee(PAYEES, '李四', '200')

    async def bad_prepare(*args):
        return {'orderId': 'MOCK-1001', 'payeeName': '李四', 'accountMasked': '****5291',
                'amount': '900.00', 'riskLevel': 'YELLOW', 'status': 'PENDING_APPROVAL'}

    monkeypatch.setattr(bank, 'prepare_transfer', bad_prepare)
    with pytest.raises(bank.BankError):
        asyncio.run(prepare_verified_transfer(target, 'abcd1234', 'Bearer demo'))
