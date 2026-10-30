"""Stage 3 mock AA security, business and planner regression tests."""
import os
import sys
from uuid import uuid4
from decimal import Decimal

os.environ['BANKPILOT_STAGE1_MOCK'] = '1'
from fastapi.testclient import TestClient
import mock_day7_backend as mock
from app.graph.task_planner import validate_plan

client = TestClient(mock.app)


def key():
    return uuid4().hex


def person(name, phone):
    u = key()[:11]
    r = client.post('/api/auth/register', json={'username': u, 'password': 'safePassword88',
                                                    'fullName': name, 'phone': phone})
    assert r.status_code == 201, r.text
    l = client.post('/api/auth/login', json={'username': u, 'password': 'safePassword88'})
    assert l.status_code == 200, l.text
    return {'Authorization': 'Bearer ' + l.json()['token']}, r.json()['userId']


def create_three(total='300.00'):
    from random import randint
    # Unique names prevent other tests' participants matching by name.
    suffix = key()[:5]
    phones = ['18' + str(randint(10**8, 10**9-1)) for _ in range(3)]
    headers = [person(n, p) for n, p in zip(('发起'+suffix, '张三'+suffix, '李四'+suffix), phones)]
    sender, sid = headers[0]
    third = headers[1:]
    data = {'participants': ['张三'+suffix, '李四'+suffix], 'amount': total,
            'splitMode': 'total_with_self', 'reason': '聚餐', 'requestId': key()}
    r = client.post('/api/aa/prepare', json=data, headers=sender)
    assert r.status_code == 200, r.text
    return sender, sid, third, r.json(), data


def balance(headers):
    return Decimal(client.get('/api/demo/balance', headers=headers).json()['balance'])


def publish(sender, cid):
    r = client.post(f'/api/aa/{cid}/publish', headers=sender, json={'requestId': key()})
    assert r.status_code == 200, r.text
    return r.json()


def test_prepare_publish_and_pay_in_authorized_payer_identity():
    sender, sid, third, draft, data = create_three()
    zhang, zid = third[0]
    li, lid = third[1]
    assert draft['status'] == 'DRAFT'
    assert draft['requestedAmount'] == '200.00'
    assert draft['selfAmount'] == '100.00'
    assert balance(sender) == Decimal('10000.00')
    assert client.get('/api/aa/inbox', headers=zhang).json() == []
    assert client.get('/api/aa/inbox', headers=li).json() == []
    publish(sender, draft['collectionId'])
    za = client.get('/api/aa/inbox', headers=zhang).json()[0]
    la = client.get('/api/aa/inbox', headers=li).json()[0]
    assert za['payerId'] == zid and la['payerId'] == lid
    assert za['amount'] == '100.00'
    assert client.post(f"/api/aa/items/{za['itemId']}/payment/prepare",
                       headers=li, json={'requestId': key()}).status_code == 404
    order = client.post(f"/api/aa/items/{za['itemId']}/payment/prepare",
                        headers=zhang, json={'requestId': key()}).json()
    assert order['status'] == 'PENDING_APPROVAL' and order['riskLevel'] == 'YELLOW'
    pay = client.post(f"/api/aa/items/{za['itemId']}/payment/confirm", headers=zhang,
                      json={'requestId': key(), 'confirmed': True})
    assert pay.status_code == 200, pay.text
    assert pay.json()['status'] == 'PAID'
    assert balance(sender) == Decimal('10100.00')
    assert balance(zhang) == Decimal('9900.00')
    assert balance(li) == Decimal('10000.00')
    after = client.get(f"/api/aa/{draft['collectionId']}", headers=sender).json()
    assert after['receivedAmount'] == '100.00' and after['status'] == 'PARTIAL'
    assert client.get('/api/aa/outgoing', headers=zhang).json() == []
    assert client.get(f"/api/aa/{draft['collectionId']}", headers=li).status_code == 404
    again = client.post(f"/api/aa/items/{za['itemId']}/payment/confirm", headers=zhang,
                        json={'requestId': key(), 'confirmed': True})
    assert again.status_code == 200 and balance(sender) == Decimal('10100.00')
    decline = client.post(f"/api/aa/items/{la['itemId']}/decline", headers=li,
                          json={'requestId': key()})
    assert decline.status_code == 200 and decline.json()['status'] == 'DECLINED'
    assert balance(li) == Decimal('10000.00')


def test_cancel_draft_rejects_later_publish_and_keeps_inbox_empty():
    sender, sid, recipients, draft, data = create_three()
    cid = draft['collectionId']
    assert client.post(f'/api/aa/{cid}/cancel-draft', headers=sender,
                       json={'requestId': key()}).json()['status'] == 'CANCELLED'
    assert client.post(f'/api/aa/{cid}/publish', headers=sender,
                       json={'requestId': key()}).status_code == 409
    for bearer, _ in recipients:
        assert client.get('/api/aa/inbox', headers=bearer).json() == []


def test_aa_uneven_split_and_idempotency():
    sender, _, recipients, draft, data = create_three('100.01')
    assert [x['amount'] for x in draft['items']] == ['33.34', '33.34']
    assert draft['selfAmount'] == '33.33' and draft['requestedAmount'] == '66.68'
    repeat = client.post('/api/aa/prepare', headers=sender, json=data)
    assert repeat.status_code == 200 and repeat.json()['collectionId'] == draft['collectionId']
    changed = client.post('/api/aa/prepare', headers=sender,
                          json={**data, 'amount': '110.00'})
    assert changed.status_code == 409


def test_red_otp_and_must_not_mark_paid_before_bank_confirm():
    sender, _, recipients, draft, _ = create_three('4500.00')
    payer, _ = recipients[0]
    publish(sender, draft['collectionId'])
    item = client.get('/api/aa/inbox', headers=payer).json()[0]
    order = client.post(f"/api/aa/items/{item['itemId']}/payment/prepare", headers=payer,
                        json={'requestId': key()}).json()
    assert order['riskLevel'] == 'RED'
    invalid = client.post(f"/api/aa/items/{item['itemId']}/payment/confirm", headers=payer,
                          json={'requestId': key(), 'confirmed': True})
    assert invalid.status_code == 403
    assert client.get(f"/api/aa/{draft['collectionId']}", headers=sender).json()['receivedAmount'] == '0.00'
    assert client.post(f"/api/aa/items/{item['itemId']}/otp/request", headers=payer).status_code == 200
    paid = client.post(f"/api/aa/items/{item['itemId']}/payment/confirm", headers=payer,
                       json={'requestId': key(), 'confirmed': True, 'otpCode': '246810'})
    assert paid.status_code == 200, paid.text
    assert client.get(f"/api/aa/{draft['collectionId']}", headers=sender).json()['receivedAmount'] == '1500.00'


def test_planner_requires_one_complete_utterance_and_prevents_writes_combining():
    raw = {'tasks': [{'type': 'create_aa_collection', 'aa_participants': ['张三','李四'],
                      'aa_mode': 'total_with_self', 'amount': '300.00', 'aa_reason':'聚餐'}],
           'unhandled_requests': []}
    plan = validate_plan(raw, message='我和张三、李四聚餐300元，三个人AA，帮我收款')
    assert plan.status == 'ready' and plan.execution_order == ['create_aa_collection']
    wrong = validate_plan(raw, message='我和张三、李四聚餐，帮我AA收款')
    assert wrong.status == 'needs_clarification'
    another = validate_plan(raw, message='我和张三、李四聚餐200元，三个人AA')
    assert another.status == 'needs_clarification'
    both = {'tasks': raw['tasks'] + [{'type': 'transfer_prepare', 'payee_name': '张三', 'amount': '100.00'}], 'unhandled_requests': []}
    assert validate_plan(both, message='我和张三、李四聚餐300元，三个人AA；给张三转100元').status == 'needs_clarification'


def test_resume_existing_payer_order_and_decline_before_debit():
    sender, _, recipients, draft, _ = create_three('600.00')
    payer, _ = recipients[0]
    publish(sender, draft['collectionId'])
    item = client.get('/api/aa/inbox', headers=payer).json()[0]
    oid = client.post(f"/api/aa/items/{item['itemId']}/payment/prepare", headers=payer,
                      json={'requestId': key()}).json()['orderId']
    restored = client.get(f"/api/aa/items/{item['itemId']}/payment", headers=payer)
    assert restored.status_code == 200 and restored.json()['orderId'] == oid
    assert client.get(f"/api/aa/items/{item['itemId']}/payment", headers=sender).status_code == 404
    declined = client.post(f"/api/aa/items/{item['itemId']}/decline", headers=payer,
                           json={'requestId': key()})
    assert declined.status_code == 200 and declined.json()['status'] == 'DECLINED'
    assert client.get(f"/api/transfers/{oid}", headers=payer).json()['status'] == 'CANCELLED'
    assert balance(sender) == Decimal('10000.00') and balance(payer) == Decimal('10000.00')
    assert client.post(f"/api/aa/items/{item['itemId']}/payment/confirm", headers=payer,
                       json={'requestId': key(), 'confirmed': True}).status_code == 409


def test_unregistered_and_duplicate_names_do_not_publish():
    sender, _, recipients, _, _ = create_three()
    r = client.post('/api/aa/prepare', headers=sender,
                    json={'participants': ['未注册测试用户'], 'amount': '100',
                          'splitMode': 'per_person', 'requestId': key()})
    assert r.status_code == 409
    r = client.post('/api/aa/prepare', headers=sender,
                    json={'participants': ['张三','张三'], 'amount': '100',
                          'splitMode': 'per_person', 'requestId': key()})
    assert r.status_code == 422


def test_per_person_aa_directly_requests_amount_without_self_share():
    sender, _, recipients, draft, _ = create_three()
    li, lid = recipients[1]
    phone = mock._users[lid]['phone']
    c = client.post('/api/aa/prepare', headers=sender, json={
        'participants': [phone], 'splitMode': 'per_person', 'amount': '88.88',
        'reason': '打车', 'requestId': key(),
    })
    assert c.status_code == 200, c.text
    view = c.json()
    assert view['requestedAmount'] == '88.88' and view['selfAmount'] == '0.00'
    assert view['items'][0]['payerId'] == lid
    assert client.get('/api/aa/outgoing', headers=sender).json() == []
