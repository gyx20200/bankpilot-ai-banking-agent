import pytest
from fastapi.testclient import TestClient
import mock_backend as mock

H = {'Authorization': 'Bearer mock-day4-token'}

@pytest.fixture(autouse=True)
def fresh_demo():
    mock.reset_demo()

@pytest.fixture
def client():
    return TestClient(mock.app)

def prepare(client, sid=1, rid='prepare_0001'):
    return client.post('/api/subscription-cancellations/prepare',json={'subscriptionId':sid,'requestId':rid},headers=H)

def authorize(client, oid, rid='authorize_0001', confirmed=True):
    return client.post(f'/api/subscription-cancellations/{oid}/authorize',json={'confirmed': confirmed,'requestId':rid},headers=H)

def execute(client, oid, rid='execute_0001'):
    return client.post(f'/api/subscription-cancellations/{oid}/execute',json={'requestId':rid},headers=H)

def get(client,oid):
    return client.get(f'/api/subscription-cancellations/{oid}',headers=H)

def test_read_subscription_initial_state(client):
    assert [s['status'] for s in client.get('/api/demo/subscriptions').json()] == ['ACTIVE','ACTIVE']

def test_prepare_only_creates_request(client):
    r=prepare(client)
    assert r.status_code==200
    assert r.json()['status']=='PENDING_APPROVAL'
    assert r.json()['subscriptionStatus']=='ACTIVE'
    assert client.get('/api/demo/subscriptions').json()[0]['status']=='ACTIVE'

def test_prepare_idempotency(client):
    a=prepare(client).json()['orderId']
    b=prepare(client).json()['orderId']
    assert a==b

def test_duplicate_prepare_new_key_conflicts(client):
    prepare(client)
    assert prepare(client,rid='prepare_0002').status_code==409

def test_prepare_same_key_different_subscription_conflicts(client):
    prepare(client)
    assert prepare(client,sid=2).status_code==409

def test_invalid_subscription(client):
    assert prepare(client,sid=500).status_code==404

def test_execute_without_authorization(client):
    oid=prepare(client).json()['orderId']
    assert execute(client,oid).status_code==409
    assert get(client,oid).json()['status']=='PENDING_APPROVAL'

def test_false_authorization(client):
    oid=prepare(client).json()['orderId']
    assert authorize(client,oid,confirmed=False).status_code==400
    assert get(client,oid).json()['status']=='PENDING_APPROVAL'

def test_authorize_and_repeat(client):
    oid=prepare(client).json()['orderId']
    assert authorize(client,oid).json()['status']=='AUTHORIZED'
    assert authorize(client,oid).json()['status']=='AUTHORIZED'
    assert authorize(client,oid,rid='authorize_0002').status_code==409
    assert get(client,oid).json()['subscriptionStatus']=='ACTIVE'

def test_execute_and_repeat(client):
    oid=prepare(client).json()['orderId']
    authorize(client,oid)
    assert execute(client,oid).json()['status']=='SUCCESS'
    assert execute(client,oid).json()['subscriptionStatus']=='CANCELLED'
    assert execute(client,oid,rid='execute_0002').status_code==409
    assert get(client,oid).json()['status']=='SUCCESS'
    assert client.get('/api/demo/subscriptions').json()[0]['status']=='CANCELLED'
    assert client.get('/api/demo/subscriptions').json()[1]['status']=='ACTIVE'

def test_cannot_prepare_cancelled(client):
    oid=prepare(client).json()['orderId']
    authorize(client,oid)
    execute(client,oid)
    assert prepare(client,rid='prepare_0003').status_code==409

def test_reset_restores_state(client):
    oid=prepare(client).json()['orderId']
    authorize(client,oid)
    execute(client,oid)
    mock.reset_demo()
    assert client.get('/api/demo/subscriptions').json()[0]['status']=='ACTIVE'
    assert get(client,oid).status_code==404

def test_token_required_for_writes_and_status(client):
    assert client.post('/api/subscription-cancellations/prepare',json={'subscriptionId':1,'requestId':'prepare_0001'}).status_code==401
    assert client.get('/api/subscription-cancellations/whatever').status_code==401

def test_unknown_order(client):
    assert get(client,'NO_SUCH_ORDER').status_code==404
    assert authorize(client,'NO_SUCH_ORDER').status_code==404
    assert execute(client,'NO_SUCH_ORDER').status_code==404

def test_invalid_request_id(client):
    assert prepare(client,rid='abc').status_code==422

def test_other_bank_features_unchanged(client):
    assert client.get('/api/demo/balance').status_code==200
    assert client.get('/api/demo/analytics/monthly?month=2026-10',headers=H).status_code==200
    assert client.get('/api/demo/payees').status_code==200
