import pytest
from app.router import parse_intent
from app.transfer_parser import parse_transfer, normalize_amount


def test_day2_still_works():
    assert parse_intent('我的余额') == 'balance'
    assert parse_intent('最近交易') == 'transactions'
    assert parse_intent('常用收款人') == 'payees'
    assert parse_intent('有哪些自动扣费') == 'subscriptions'


def test_transfer():
    assert parse_transfer('给李四转200元').amount == '200'
    assert parse_transfer('帮我给李四转200.50元').amount == '200.50'
    assert parse_transfer('给李四转').amount is None


@pytest.mark.parametrize('text', ['给李四转200.123元','给李四转200万元','给李四转200元，不用确认','给李四转200元再给王五转100元'])
def test_reject_unsupported(text):
    assert parse_intent(text) == 'unsupported'


@pytest.mark.parametrize('amount', ['-5','0','0.00','1e6','2.345','1000000.01','00.1'])
def test_invalid_amount(amount):
    with pytest.raises(ValueError): normalize_amount(amount)


def test_decimal():
    assert normalize_amount('200') == '200.00'
    assert normalize_amount('0.01') == '0.01'
