"""Stage4: authorization, idempotency, missed windows and bank ownership."""
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

os.environ['BANKPILOT_STAGE1_MOCK'] = '1'
from fastapi.testclient import TestClient
import mock_day7_backend as mock
from app.graph.schedule_time import validate_schedule_time, CN
from app.graph.task_planner import validate_plan

client = TestClient(mock.app)


def person(name, phone):
    uname = 'u' + uuid4().hex[:14]
    res = client.post('/api/auth/register', json={
        'username': uname, 'password': 'safePassword88', 'fullName': name, 'phone': phone,
    })
    assert res.status_code == 201, res.text
    token = client.post('/api/auth/login', json={'username': uname, 'password': 'safePassword88'}).json()['token']
    return {'Authorization': 'Bearer ' + token}, res.json()['userId']


def setup():
    n = int(uuid4().int % 10**9)
    return person('日程甲'+str(n), '13' + f'{n:09d}'), person('日程乙'+str(n), '15' + f'{n:09d}')


def schedule(payer, target, amount='200.00', time_offset=timedelta(minutes=5)):
    due = (datetime.now(CN) + time_offset).replace(second=0, microsecond=0)
    data = {'payeeId': target, 'amount': amount, 'remark': '生活费',
            'executeAt': due.isoformat(timespec='minutes'), 'requestId': uuid4().hex}
    r = client.post('/api/scheduled-transfers/prepare', json=data, headers=payer)
    assert r.status_code == 200, r.text
    return r.json(), data, due


def bal(h):
    return Decimal(client.get('/api/demo/balance', headers=h).json()['balance'])


def auth(h, sid):
    r = client.post(f'/api/scheduled-transfers/{sid}/otp/request', headers=h)
    assert r.status_code == 200, r.text
    return client.post(f'/api/scheduled-transfers/{sid}/authorize', headers=h,
                       json={'requestId': uuid4().hex, 'confirmed': True, 'otpCode': '246810'})


def test_schedule_otp_required_and_no_immediate_debit():
    (payer, uid), (receiver, rid) = setup()
    draft, data, due = schedule(payer, rid, amount='10.00')
    sid = draft['scheduleId']
    assert draft['status'] == 'PENDING_AUTH'
    assert bal(payer) == bal(receiver) == 10000
    unauth = client.post(f'/api/scheduled-transfers/{sid}/authorize', headers=payer,
                         json={'requestId': uuid4().hex, 'confirmed': True, 'otpCode': '246810'})
    assert unauth.status_code == 403
    assert client.post(f'/api/scheduled-transfers/{sid}/otp/request', headers=receiver).status_code == 404
    signed = auth(payer, sid)
    assert signed.status_code == 200 and signed.json()['status'] == 'SCHEDULED'
    assert bal(payer) == bal(receiver) == 10000
    assert client.get('/api/scheduled-transfers/mine', headers=receiver).json() == []
    assert client.get(f'/api/scheduled-transfers/{sid}', headers=receiver).status_code == 404
    mock._process_due(due.astimezone(timezone.utc))
    result = client.get(f'/api/scheduled-transfers/{sid}', headers=payer).json()
    assert result['status'] == 'SUCCESS' and result['orderId']
    assert bal(payer) == 9990 and bal(receiver) == 10010
    assert len([x for x in client.get('/api/demo/transactions', headers=payer).json()
                if x.get('remark') == '生活费']) == 1
    mock._process_due(due.astimezone(timezone.utc) + timedelta(seconds=2))
    assert bal(payer) == 9990 and bal(receiver) == 10010


def test_schedule_idempotency_cancel_missed_failed_no_retry():
    (payer, uid), (receiver, rid) = setup()
    first, data, due = schedule(payer, rid)
    r = client.post('/api/scheduled-transfers/prepare', headers=payer, json=data)
    assert r.json()['scheduleId'] == first['scheduleId']
    changed = dict(data, amount='999.00')
    assert client.post('/api/scheduled-transfers/prepare', headers=payer, json=changed).status_code == 409
    assert auth(payer, first['scheduleId']).status_code == 200
    assert client.post(f"/api/scheduled-transfers/{first['scheduleId']}/cancel", headers=payer,
                       json={'requestId': uuid4().hex}).json()['status'] == 'CANCELLED'
    mock._process_due(due.astimezone(timezone.utc))
    assert bal(payer) == 10000
    second, _, due2 = schedule(payer, rid)
    assert auth(payer, second['scheduleId']).status_code == 200
    mock._process_due(due2.astimezone(timezone.utc) + timedelta(seconds=61))
    assert client.get(f"/api/scheduled-transfers/{second['scheduleId']}", headers=payer).json()['status'] == 'MISSED'
    mock._process_due(due2.astimezone(timezone.utc) + timedelta(seconds=62))
    assert bal(payer) == 10000
    third, _, due3 = schedule(payer, rid, amount='100000.00')
    assert auth(payer, third['scheduleId']).status_code == 200
    mock._process_due(due3.astimezone(timezone.utc))
    failed = client.get(f"/api/scheduled-transfers/{third['scheduleId']}", headers=payer).json()
    assert failed['status'] == 'FAILED'
    mock._accounts[uid] += Decimal('100000')
    mock._process_due(due3.astimezone(timezone.utc) + timedelta(seconds=3))
    assert client.get(f"/api/scheduled-transfers/{third['scheduleId']}", headers=payer).json()['status'] == 'FAILED'


def test_planner_schedule_uses_llm_iso_time_instead_of_parsing_user_phrase():
    now = datetime(2026, 10, 30, 20, 55, tzinfo=CN)
    raw = {'tasks': [{'type': 'schedule_transfer', 'payee_name': '李四',
                       'amount': '200', 'time_expression': '明天下午3点',
                       'execute_at': '2026-10-31T15:00:00+08:00'}],
           'unhandled_requests': []}
    plan = validate_plan(raw, message='明天下午3点给李四转200元', now=now)
    assert plan.status == 'ready' and plan.tasks[0].execute_at == '2026-10-31T15:00:00+08:00'
    assert validate_plan(raw, message='明天下午3点给李四转300元', now=now).status == 'needs_clarification'
    assert validate_plan(raw, message='明天下午3点给张三转200元', now=now).status == 'needs_clarification'
    assert validate_plan(raw, message='下周五下午3点给李四转200元', now=now).status == 'needs_clarification'


def test_bad_otp_does_not_pre_authorize_and_can_retry():
    (payer, uid), (receiver, rid) = setup()
    draft, _, due = schedule(payer, rid, amount='25.00')
    sid = draft['scheduleId']
    assert client.post(f'/api/scheduled-transfers/{sid}/otp/request', headers=payer).status_code == 200
    bad = client.post(f'/api/scheduled-transfers/{sid}/authorize', headers=payer,
                      json={'requestId': uuid4().hex, 'confirmed': True, 'otpCode': '000000'})
    assert bad.status_code == 403
    assert client.get(f'/api/scheduled-transfers/{sid}', headers=payer).json()['status'] == 'PENDING_AUTH'
    good = client.post(f'/api/scheduled-transfers/{sid}/authorize', headers=payer,
                       json={'requestId': uuid4().hex, 'confirmed': True, 'otpCode': '246810'})
    assert good.status_code == 200 and good.json()['status'] == 'SCHEDULED'
    assert bal(payer) == 10000 and bal(receiver) == 10000


def test_llm_normalized_schedule_time_and_format_validation():
    now = datetime(2026, 10, 30, 20, 55, tzinfo=CN)
    cases = {
        '2026-10-30T22:35:00+08:00': '2026-10-30T22:35:00+08:00',
        '2026-11-30T21:37+08:00': '2026-11-30T21:37:00+08:00',
        '2026-10-30T20:57:11+08:00': '2026-10-30T20:57:11+08:00',
    }
    for value, expected in cases.items():
        assert validate_schedule_time(value, now=now) == expected
    for invalid in (None, '', '今天下午3点', '2026-11-30',
                    '2026-11-30T21:37', '2026-11-30T21:37:00Z',
                    '2026-02-30T21:37:00+08:00', '2026-10-30T20:54+08:00',
                    '2026-11-30T21:37+09:00', '2026-11-30T25:37:00+08:00'):
        assert validate_schedule_time(invalid, now=now) is None, invalid


def test_planner_schedule_accepts_llm_conversion_for_varied_phrases():
    now = datetime(2026, 10, 30, 20, 55, tzinfo=CN)
    samples = [
        ('今天下午10.35', '2026-10-30T22:35:00+08:00'),
        ('2026年11月30日21.37', '2026-11-30T21:37:00+08:00'),
        ('2分钟后', '2026-10-30T20:57:00+08:00'),
        ('下周五下午6点', '2026-11-06T18:00:00+08:00'),
        ('后天早上八点半', '2026-11-01T08:30:00+08:00'),
    ]
    for phrase, converted in samples:
        raw = {'tasks': [{'type': 'schedule_transfer', 'payee_name': '李四',
                          'amount': '500', 'time_expression': phrase,
                          'execute_at': converted}], 'unhandled_requests': []}
        result = validate_plan(raw, message=phrase + '给李四转500元', now=now)
        assert result.status == 'ready', phrase
        assert result.tasks[0].execute_at == converted
        assert result.tasks[0].time_expression == phrase


def test_planner_schedule_rejects_missing_or_unsupported_time_without_guessing():
    now = datetime(2026, 10, 30, 20, 55, tzinfo=CN)
    base = {'type': 'schedule_transfer', 'payee_name': '李四', 'amount': '500',
            'time_expression': '明天', 'execute_at': '2026-10-31T15:00:00+08:00'}
    for change in ({}, {'time_expression': '下周五'},
                   {'execute_at': '2026-10-30T18:00:00+08:00'},
                   {'execute_at': '2026-11-30T21:37:00'},
                   {'time_expression': '明天下午3点'}):
        task = dict(base, **change)
        status = validate_plan({'tasks': [task], 'unhandled_requests': []},
                               message='明天给李四转500元', now=now).status
        assert status == 'needs_clarification', change
    no_datetime = dict(base)
    del no_datetime['execute_at']
    assert validate_plan({'tasks': [no_datetime], 'unhandled_requests': []},
                         message='明天给李四转500元', now=now).status == 'needs_clarification'


def test_planner_time_must_be_provided_by_model_and_grounded_in_original_message():
    now = datetime(2026, 10, 30, 20, 55, tzinfo=CN)
    raw = {'tasks': [{'type': 'schedule_transfer', 'payee_name': '李四',
                      'amount': '500', 'time_expression': '明天下午3点',
                      'execute_at': '2026-10-31T15:00:00+08:00'}],
           'unhandled_requests': []}
    assert validate_plan(raw, message='明天给李四转500元', now=now).status == 'needs_clarification'
    assert validate_plan(raw, message='明天下午3点给李四转500元', now=now).status == 'ready'
    invalid_time = dict(raw['tasks'][0], execute_at='2026-10-31T15:00:00')
    assert validate_plan({'tasks': [invalid_time], 'unhandled_requests': []},
                         message='明天下午3点给李四转500元', now=now).status == 'needs_clarification'
