"""Stage 4D bank-reject API regression, isolated Mock only."""
import pytest
from fastapi.testclient import TestClient
import mock_backend as mock

H = {'Authorization': 'Bearer mock-day4-token'}


@pytest.fixture
def client():
    mock.reset_demo()
    return TestClient(mock.app)


def prepare(client, rid='prepare_reject_0001'):
    r = client.post('/api/subscription-cancellations/prepare',
                    json={'subscriptionId': 1, 'requestId': rid}, headers=H)
    assert r.status_code == 200, r.text
    return r.json()['orderId']


def reject(client, oid, rid='reject_0001'):
    return client.post(f'/api/subscription-cancellations/{oid}/reject',
                       json={'requestId': rid}, headers=H)


def test_reject_closes_pending_order(client):
    oid = prepare(client)
    result = reject(client, oid)
    assert result.status_code == 200
    assert result.json()['status'] == 'REJECTED'
    assert result.json()['subscriptionStatus'] == 'ACTIVE'
    status = client.get(f'/api/subscription-cancellations/{oid}', headers=H)
    assert status.json()['status'] == 'REJECTED'
    subs = client.get('/api/demo/subscriptions').json()
    assert subs[0]['status'] == 'ACTIVE'


def test_reject_is_idempotent(client):
    oid = prepare(client)
    assert reject(client, oid).status_code == 200
    assert reject(client, oid).status_code == 200
    assert reject(client, oid, 'reject_0002').status_code == 409


def test_reject_blocks_authorize_execute(client):
    oid = prepare(client)
    reject(client, oid)
    auth = client.post(f'/api/subscription-cancellations/{oid}/authorize',
                       json={'confirmed': True, 'requestId': 'authorize_0001'}, headers=H)
    exe = client.post(f'/api/subscription-cancellations/{oid}/execute',
                      json={'requestId': 'execute_0001'}, headers=H)
    assert auth.status_code == 409
    assert exe.status_code == 409


def test_reject_cannot_override_authorized(client):
    oid = prepare(client)
    auth = client.post(f'/api/subscription-cancellations/{oid}/authorize',
                       json={'confirmed': True, 'requestId': 'authorize_0001'}, headers=H)
    assert auth.status_code == 200
    assert reject(client, oid).status_code == 409


def test_reject_requires_token(client):
    oid = prepare(client)
    assert client.post(f'/api/subscription-cancellations/{oid}/reject',
                       json={'requestId': 'reject_0001'}).status_code == 401
