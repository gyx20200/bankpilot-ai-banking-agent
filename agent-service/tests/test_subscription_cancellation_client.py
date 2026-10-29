import asyncio
import pytest
from app import banking_client as bank

AUTH = 'Bearer fake-test-user'


def run(coro):
    return asyncio.run(coro)


def test_prepare_calls_only_prepare(monkeypatch):
    calls = []
    async def fake_request(method, url, bearer=None, data=None):
        calls.append((method, url, bearer, data))
        return {'orderId': 'SC-1001', 'subscriptionId': 7, 'status': 'PENDING_APPROVAL'}
    monkeypatch.setattr(bank, '_request', fake_request)
    order = run(bank.prepare_subscription_cancellation(7, AUTH, 'prepare-0001'))
    assert order['status'] == 'PENDING_APPROVAL'
    assert calls == [('POST', f'{bank.CANCELLATION_URL}/prepare', AUTH,
                      {'subscriptionId': 7, 'requestId': 'prepare-0001'})]


def test_prepare_cannot_claim_success(monkeypatch):
    async def fake_request(*args, **kwargs):
        return {'orderId': 'SC-1001', 'subscriptionId': 7, 'status': 'SUCCESS'}
    monkeypatch.setattr(bank, '_request', fake_request)
    with pytest.raises(bank.BankError):
        run(bank.prepare_subscription_cancellation(7, AUTH, 'prepare-0001'))


def test_authorize_requires_explicit_true(monkeypatch):
    async def cannot_request(*args, **kwargs):
        raise AssertionError('must not call backend')
    monkeypatch.setattr(bank, '_request', cannot_request)
    with pytest.raises(bank.BankError):
        run(bank.authorize_subscription_cancellation('SC-1001', AUTH, 'authorize-0001', False))


def test_authorize_sends_confirmed(monkeypatch):
    calls = []
    async def fake_request(method, url, bearer=None, data=None):
        calls.append((method, url, bearer, data))
        return {'orderId': 'SC-1001', 'status': 'AUTHORIZED'}
    monkeypatch.setattr(bank, '_request', fake_request)
    assert run(bank.authorize_subscription_cancellation('SC-1001', AUTH, 'authorize-0001', True))['status'] == 'AUTHORIZED'
    assert calls[0][1].endswith('/SC-1001/authorize')
    assert calls[0][3] == {'confirmed': True, 'requestId': 'authorize-0001'}


def test_authorize_rejects_mismatched_order(monkeypatch):
    async def fake_request(*args, **kwargs):
        return {'orderId': 'SC-9999', 'status': 'AUTHORIZED'}
    monkeypatch.setattr(bank, '_request', fake_request)
    with pytest.raises(bank.BankError):
        run(bank.authorize_subscription_cancellation('SC-1001', AUTH, 'authorize-0001', True))


def test_execute_only_accepts_confirmed_cancelled(monkeypatch):
    async def fake_request(*args, **kwargs):
        return {'orderId': 'SC-1001', 'status': 'SUCCESS', 'subscriptionStatus': 'ACTIVE'}
    monkeypatch.setattr(bank, '_request', fake_request)
    with pytest.raises(bank.BankError):
        run(bank.execute_subscription_cancellation('SC-1001', AUTH, 'execute-0001'))


def test_execute_success(monkeypatch):
    async def fake_request(*args, **kwargs):
        return {'orderId': 'SC-1001', 'status': 'SUCCESS', 'subscriptionStatus': 'CANCELLED'}
    monkeypatch.setattr(bank, '_request', fake_request)
    assert run(bank.execute_subscription_cancellation('SC-1001', AUTH, 'execute-0001'))['status'] == 'SUCCESS'


def test_get_order(monkeypatch):
    async def fake_request(method, url, bearer=None, data=None):
        assert method == 'GET' and url.endswith('/SC-1001') and bearer == AUTH
        return {'orderId': 'SC-1001', 'status': 'PENDING_APPROVAL'}
    monkeypatch.setattr(bank, '_request', fake_request)
    assert run(bank.get_subscription_cancellation('SC-1001', AUTH))['status'] == 'PENDING_APPROVAL'


@pytest.mark.parametrize('bad_id', [0, -1, True, '2', None])
def test_reject_invalid_subscription_id(bad_id, monkeypatch):
    async def cannot_request(*args, **kwargs):
        raise AssertionError('must not call backend')
    monkeypatch.setattr(bank, '_request', cannot_request)
    with pytest.raises(bank.BankError):
        run(bank.prepare_subscription_cancellation(bad_id, AUTH, 'prepare-0001'))


def test_reject_invalid_request_id():
    with pytest.raises(bank.BankError):
        run(bank.prepare_subscription_cancellation(1, AUTH, 'bad'))


def test_no_login():
    with pytest.raises(bank.BankError) as exc:
        run(bank.prepare_subscription_cancellation(1, None, 'prepare-0001'))
    assert exc.value.status == 401
