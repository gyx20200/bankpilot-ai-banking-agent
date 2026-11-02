#!/usr/bin/env python3
"""Non-destructive Java/MySQL smoke checks: registers plans but does NOT cancel subscriptions.

Requires DAY6 demo authentication and the original Day6 cancellation migration.
Run only against a local synthetic test database.
"""
import argparse
import json
import os
import sys
import uuid
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


def call(base, method, path, *, body=None, token=None):
    data = None if body is None else json.dumps(body).encode('utf-8')
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = Request(base.rstrip('/') + path, method=method, data=data, headers=headers)
    try:
        with urlopen(req, timeout=8) as res:
            raw = res.read().decode('utf-8')
            return res.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        return exc.code, {}


def check(test, label):
    if not test:
        raise AssertionError(label)
    print('[PASS]', label)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--bank', default='http://127.0.0.1:8080')
    args = p.parse_args()
    password = os.getenv('DEMO_LOGIN_PASSWORD')
    if not password:
        raise RuntimeError('Missing DEMO_LOGIN_PASSWORD')
    base = args.bank
    login_code, login = call(base, 'POST', '/api/auth/demo-login', body={'username': 'demo', 'password': password})
    check(login_code == 200 and bool(login.get('token')), 'Java login')
    token = login['token']

    unauth, _ = call(base, 'GET', '/api/agent/capabilities')
    check(unauth == 401, 'Catalog requires authentication')
    rc, cap = call(base, 'GET', '/api/agent/capabilities', token=token)
    check(rc == 200 and len(cap.get('capabilities', [])) == 3, 'Three allowed backend capabilities')
    check(not any('execute' in item.get('operation','') or 'authorize' in item.get('operation','')
                  for item in cap['capabilities']), 'No approval/execute model tools')

    rc, balance = call(base, 'GET', '/api/demo/balance', token=token)
    check(rc == 200 and 'balance' in balance, 'Get original balance')
    rc, subs = call(base, 'GET', '/api/demo/subscriptions', token=token)
    check(rc == 200 and isinstance(subs, list), 'Subscription query')

    for month in ['2026-08', '2026-09', '2026-10']:
        rc, report = call(base, 'GET', f'/api/demo/analytics/monthly?month={month}', token=token)
        check(rc == 200 and report.get('month') == month and report.get('source') == 'mysql',
              f'Dynamic month {month} uses Java/MySQL')
    rc, _ = call(base, 'GET', '/api/demo/analytics/monthly?month=2026-13', token=token)
    check(rc == 400, 'Invalid month rejected by Java')

    A = lambda month: {'type':'monthly_analytics','month':month}
    B = {'type':'list_subscriptions'}
    C = {'type':'cancel_subscription','merchantName':'视频会员'}
    cases = [[A('2026-08')],[B],[C],[A('2026-09'),B],
             [A('2026-10'),C],[B,C],[A('2026-10'),B,C]]
    test_prefix = 'wf_d6_' + uuid.uuid4().hex[:16]
    for i, tasks in enumerate(cases, 1):
        wf = f'{test_prefix}_{i}'
        payload = {'workflowId':wf,'tasks':tasks}
        rc, plan = call(base, 'POST', '/api/agent/workflow-runs', body=payload, token=token)
        check(rc == 201 and plan.get('workflowId') == wf and len(plan.get('tasks',[])) == len(tasks),
              f'Combination {i}/7 registered')
        rc, replay = call(base, 'POST', '/api/agent/workflow-runs', body=payload, token=token)
        check(rc == 201 and replay.get('tasks') == plan.get('tasks'), f'Combination {i}/7 idempotent')
        rc, recovered = call(base, 'GET', '/api/agent/workflow-runs/'+wf, token=token)
        check(rc == 200 and recovered.get('tasks') == plan.get('tasks'), f'Combination {i}/7 reloadable')
        if any(x['type'] == 'cancel_subscription' for x in tasks):
            cancel = next(x for x in plan['tasks'] if x['type'] == 'cancel_subscription')
            check('human_approval' in cancel['dependsOn'], 'Approval dependency enforced in plan')
            check(plan['businessPhase'] == 'CANCELLATION_NOT_PREPARED', 'Registry alone does not cancel')
        else:
            check(plan['businessPhase'] == 'READ_ONLY_PLAN', 'Read-only tasks do not cancel')
        if i == 1:
            rc, _ = call(base, 'POST', '/api/agent/workflow-runs',
                         body={'workflowId':wf,'tasks':[A('2026-10')]}, token=token)
            check(rc == 409, 'Same workflow ID with changed plan rejected')

    rc, _ = call(base, 'POST', '/api/agent/workflow-runs',
                 body={'workflowId':test_prefix+'_bad','tasks':[{'type':'execute_transfer'}]}, token=token)
    check(rc == 400, 'Unknown model-proposed task rejected')
    rc, after = call(base, 'GET', '/api/demo/balance', token=token)
    check(rc == 200 and str(after['balance']) == str(balance['balance']), 'No balance mutation')
    rc, actual_subs = call(base, 'GET', '/api/demo/subscriptions', token=token)
    check(rc == 200 and subs == actual_subs, 'No subscription cancellation')
    print('\nALL PASSED: A/B/C plan registry, month validation and business safety.')
    print('Plans were persisted in MySQL. Run the separate cancellation smoke test only on disposable data.')


if __name__ == '__main__':
    try:
        main()
    except (AssertionError, RuntimeError, URLError, ValueError, KeyError) as exc:
        print('[FAIL]', str(exc), file=sys.stderr)
        raise SystemExit(1)
