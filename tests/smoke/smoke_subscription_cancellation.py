#!/usr/bin/env python3
"""Day 6 local-dev integration checks against real Spring Boot/MySQL.

WARNING: defaults to executing a cancellation of one DEMO subscription.
Use a disposable demo database and an active subscription id. No real funds move.
"""
import argparse
import json
import os
import sys
import uuid
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


def call(base, method, path, data=None, token=None):
    body = json.dumps(data).encode('utf-8') if data is not None else None
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = Request(base.rstrip('/') + path, data=body, headers=headers, method=method)
    try:
        with urlopen(req, timeout=8) as res:
            raw = res.read()
            return res.status, json.loads(raw.decode('utf-8')) if raw else {}
    except HTTPError as error:
        try:
            result = json.loads(error.read().decode('utf-8'))
        except (ValueError, UnicodeDecodeError):
            result = {'error': 'HTTP error'}
        return error.code, result


def require(condition, label):
    if not condition:
        raise AssertionError(label)
    print('[PASS]', label)


def main():
    p = argparse.ArgumentParser(description='Day6 BankPilot local demo smoke tests')
    p.add_argument('--bank', default='http://127.0.0.1:8080')
    p.add_argument('--subscription-id', type=int, default=1)
    p.add_argument('--agent', default=None, help='optional Python agent base URL, e.g. http://127.0.0.1:8000')
    args = p.parse_args()

    password = os.getenv('DEMO_LOGIN_PASSWORD')
    if not password:
        raise SystemExit('Set DEMO_LOGIN_PASSWORD in PowerShell first; do not save it in source code.')
    c, _ = call(args.bank, 'GET', '/api/subscription-cancellations/1')
    require(c == 401, 'Unauthorized request rejected')
    c, session = call(args.bank, 'POST', '/api/auth/demo-login', {'username': 'demo', 'password': password})
    require(c == 200 and bool(session.get('token')), 'Demo login provides temporary bearer token')
    token = session['token']

    c, subs = call(args.bank, 'GET', '/api/demo/subscriptions', token=token)
    require(c == 200 and isinstance(subs, list), 'Subscriptions retrieved from Java API')
    selected = next((s for s in subs if s.get('id') == args.subscription_id), None)
    require(selected is not None and selected['status'] == 'ACTIVE', 'Selected demo subscription is ACTIVE')
    c, balance_before = call(args.bank, 'GET', '/api/demo/balance', token=token)
    require(c == 200, 'Initial bank balance queried')
    c, report = call(args.bank, 'GET', '/api/demo/analytics/monthly?month=2026-10', token=token)
    require(c == 200 and report.get('month') == '2026-10' and 'netCashFlow' in report,
            'Day5 monthly analytics still works')
    c, transactions_before = call(args.bank, 'GET', '/api/demo/transactions', token=token)
    require(c == 200 and isinstance(transactions_before, list), 'Day2 transaction query still works')

    uid = uuid.uuid4().hex
    workflow_id = 'day6-run-' + uid[:16]
    body = {'subscriptionId': args.subscription_id, 'requestId': 'day6-' + uid, 'workflowId': workflow_id}
    c, draft = call(args.bank, 'POST', '/api/subscription-cancellations/prepare', body, token)
    require(c == 201 and draft.get('status') == 'PENDING_APPROVAL' and draft.get('riskLevel') == 'YELLOW',
            'Create YELLOW pending cancellation order only')
    order_id = draft['orderId']
    c, duplicated = call(args.bank, 'POST', '/api/subscription-cancellations/prepare', body, token)
    require(c == 201 and duplicated.get('orderId') == order_id, 'Duplicate requestId returns original order')
    c, not_authorized = call(args.bank, 'POST', f'/api/subscription-cancellations/{order_id}/execute', token=token)
    require(c == 409, 'Execution before confirmation is blocked')
    c, still_active = call(args.bank, 'GET', '/api/demo/subscriptions', token=token)
    require(c == 200 and next(s for s in still_active if s['id']==args.subscription_id)['status'] == 'ACTIVE',
            'Bank subscription still active after draft')

    c, approved = call(args.bank, 'POST', f'/api/subscription-cancellations/{order_id}/authorize',
                       {'confirmed': True}, token)
    require(c == 200 and approved.get('status') == 'AUTHORIZED', 'Explicit confirmation authorizes order')
    c, performed = call(args.bank, 'POST', f'/api/subscription-cancellations/{order_id}/execute', token=token)
    require(c == 200 and performed.get('status') == 'SUCCESS', 'Authorized cancellation executes')
    c, repeated = call(args.bank, 'POST', f'/api/subscription-cancellations/{order_id}/execute', token=token)
    require(c == 200 and repeated.get('status') == 'SUCCESS', 'Repeat execution is idempotent')
    c, status = call(args.bank, 'GET', f'/api/subscription-cancellations/{order_id}', token=token)
    require(c == 200 and status.get('status') == 'SUCCESS', 'Authoritative order state is SUCCESS')
    c, subs_after = call(args.bank, 'GET', '/api/demo/subscriptions', token=token)
    require(c == 200 and next(s for s in subs_after if s['id']==args.subscription_id)['status'] == 'CANCELLED',
            'Only targeted bank-side subscription was cancelled')
    c, balance_after = call(args.bank, 'GET', '/api/demo/balance', token=token)
    require(c == 200 and str(balance_after['balance']) == str(balance_before['balance']),
            'Cancellation never changes bank account balance')
    c, transactions_after = call(args.bank, 'GET', '/api/demo/transactions', token=token)
    require(c == 200 and transactions_after == transactions_before, 'Cancellation creates no transfer transactions')

    if args.agent:
        # Only checks already finished Day5 month analytics; it does NOT claim to test Day6 LangGraph.
        c, agent_result = call(args.agent, 'POST', '/api/agent/chat',
                {'message': '帮我分析2026年10月的收支情况', 'requestId': 'day6-' + uuid.uuid4().hex}, token)
        require(c == 200 and agent_result.get('intent') == 'monthly_analytics',
                'Agent Day5 monthly_analytics regression')
        print('[INFO] Verify DeepSeek tool_calls and Day6 LangGraph interruption manually in the UI.')

    print('\nALL PASSED — Local Java+MySQL Day6 cancellation workflow.')
    print('Order:', order_id, '/ Workflow:', workflow_id)
    print('IMPORTANT: demo subscription',args.subscription_id,'is now CANCELLED. Use a fresh test DB for another run.')


if __name__ == '__main__':
    try:
        main()
    except (AssertionError, URLError, ValueError, KeyError) as e:
        print('[FAIL]',str(e), file=sys.stderr)
        raise SystemExit(1)
