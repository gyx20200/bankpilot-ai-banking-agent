"""DAY 7 LOCAL MOCK BANK ONLY. Never deploy or connect to real funds.

Start explicitly: BANKPILOT_STAGE1_MOCK=1 uvicorn mock_day7_backend:app --host 127.0.0.1 --port 18080
Every account/token/order lives in RAM. Restart erases all data. No Java/MySQL calls.
"""
import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from threading import Thread, Event
from decimal import Decimal, InvalidOperation
from threading import RLock
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

if os.getenv('BANKPILOT_STAGE1_MOCK') != '1':
    raise RuntimeError('这是不安全的本地模拟银行，必须显式设置 BANKPILOT_STAGE1_MOCK=1 才能启动。')

app = FastAPI(title='BankPilot Day7 LOCAL MOCK — NEVER DEPLOY', version='stage1-test-only')
_lock = RLock()
_users: dict[int, dict] = {}
_username_to_id: dict[str, int] = {}
_phone_to_id: dict[str, int] = {}
_tokens: dict[str, dict] = {}
_accounts: dict[int, Decimal] = {}
_transactions: dict[int, list[dict]] = {}
_subscriptions: dict[int, dict] = {}
_orders: dict[str, dict] = {}
_transfer_request_keys: dict[tuple[int, str], str] = {}
_cancellations: dict[str, dict] = {}
_cancel_request_keys: dict[tuple[int, str], str] = {}
_aa_collections: dict[str, dict] = {}
_aa_items: dict[str, dict] = {}
_aa_request_keys: dict[tuple[int, str], str] = {}
_schedules: dict[str, dict] = {}
_schedule_keys: dict[tuple[int, str], str] = {}
_scheduler_stop = Event()
_DEMO_OTP = '246810'  # deliberately insecure; ONLY local RAM simulation
_AUTH_SECONDS = 1800


def _now():
    return datetime.now(timezone.utc)


def _money(value: Decimal) -> str:
    return f'{value:.2f}'


def _masked_account(uid: int) -> str:
    return f'****{(6600 + uid):04d}'


def _password_hash(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 160_000)


def _principal(authorization: str | None) -> dict:
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(401, '请先登录模拟银行。')
    token = authorization[7:].strip()
    with _lock:
        record = _tokens.get(token)
        if not record or record['expires'] <= _now():
            raise HTTPException(401, '登录状态已过期或撤销。')
        return _users[record['user_id']]


def _subscription(sub_id: int, uid: int) -> dict:
    sub = _subscriptions.get(sub_id)
    if not sub or sub['userId'] != uid:
        raise HTTPException(404, '订阅协议不存在。')
    return sub


def _order(order_id: str, uid: int) -> dict:
    order = _orders.get(order_id)
    if not order or order['fromUserId'] != uid:
        raise HTTPException(404, '订单不存在。')
    return order


def _cancellation(order_id: str, uid: int) -> dict:
    order = _cancellations.get(order_id)
    if not order or order['userId'] != uid:
        raise HTTPException(404, '取消申请不存在。')
    return order


def _transfer_view(order: dict) -> dict:
    result = {key: order[key] for key in (
        'orderId', 'payeeName', 'accountMasked', 'amount', 'riskLevel', 'status', 'remark')}
    if order.get('transferId'):
        result['transferId'] = order['transferId']
        result['balanceAfter'] = order['balanceAfter']
    return result


def _cancel_view(order: dict) -> dict:
    sub = _subscriptions[order['subscriptionId']]
    return {'orderId': order['orderId'], 'subscriptionId': sub['id'],
            'merchantName': sub['merchantName'], 'status': order['status'],
            'subscriptionStatus': sub['status']}


def _parse_amount(value: str) -> Decimal:
    try:
        num = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise HTTPException(422, '金额格式无效。')
    if not num.is_finite() or not (Decimal('0') < num <= Decimal('1000000')) or num.as_tuple().exponent < -2:
        raise HTTPException(422, '金额不合法。')
    return num.quantize(Decimal('0.01'))


def _risk(uid: int) -> str:
    today = _now().astimezone(timezone(timedelta(hours=8))).date().isoformat()
    total = sum((Decimal(item['amount']) for item in _orders.values()
                 if item['fromUserId'] == uid and item['createdDate'] == today
                 and item['status'] in ('PENDING_APPROVAL', 'AUTHORIZED', 'EXECUTING', 'SUCCESS', 'UNKNOWN')),
                Decimal('0'))
    return 'RED' if total > 1000 else 'YELLOW'


class RegisterBody(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r'^[A-Za-z0-9_]+$')
    password: str = Field(min_length=8, max_length=128)
    fullName: str = Field(min_length=1, max_length=50)
    phone: str = Field(pattern=r'^1[3-9][0-9]{9}$')


class LoginBody(BaseModel):
    username: str
    password: str


class TransferPrepare(BaseModel):
    payeeId: int = Field(gt=0)
    amount: str
    requestId: str = Field(min_length=8, max_length=64)
    remark: str = Field(default='', max_length=80)


class TransferApprove(BaseModel):
    confirmation: bool
    otpCode: str | None = None
    requestId: str = Field(min_length=8, max_length=64)


class RequestId(BaseModel):
    requestId: str = Field(min_length=8, max_length=128)


class CancellationPrepare(RequestId):
    subscriptionId: int = Field(gt=0)


class CancellationApprove(RequestId):
    confirmed: bool


@app.get('/health')
def health():
    return {'status': 'ok', 'mode': 'LOCAL_MOCK_ONLY', 'persistent': False}


@app.post('/api/auth/register', status_code=201)
def register(body: RegisterBody):
    with _lock:
        username = body.username.strip().lower()
        if not body.fullName.strip():
            raise HTTPException(422, '姓名不能为空。')
        if username in _username_to_id or body.phone in _phone_to_id:
            raise HTTPException(409, '用户名或手机号已经注册。')
        uid = len(_users) + 1
        salt = secrets.token_bytes(16)
        user = {'userId': uid, 'username': username,
                'displayName': body.fullName.strip(), 'phone': body.phone,
                'salt': salt, 'digest': _password_hash(body.password, salt)}
        _users[uid] = user
        _username_to_id[username] = uid
        _phone_to_id[body.phone] = uid
        _accounts[uid] = Decimal('10000.00')
        _transactions[uid] = []
        for merchant, amount in (('视频会员', '25.00'), ('音乐会员', '15.00')):
            sid = len(_subscriptions) + 1
            _subscriptions[sid] = {
                'id': sid, 'userId': uid, 'merchantName': merchant, 'amount': amount,
                'billingCycle': 'MONTHLY', 'status': 'ACTIVE',
                'nextPayDate': (_now() + timedelta(days=30)).date().isoformat(),
            }
    return {'userId': uid, 'status': 'REGISTERED'}


@app.post('/api/auth/login')
def login(body: LoginBody):
    with _lock:
        uid = _username_to_id.get(body.username.strip().lower())
        user = _users.get(uid)
        # Do not reveal whether the username exists.
        if not user or not hmac.compare_digest(_password_hash(body.password, user['salt']), user['digest']):
            raise HTTPException(401, '用户名或密码错误。')
        token = secrets.token_urlsafe(32)
        _tokens[token] = {'user_id': uid, 'expires': _now() + timedelta(seconds=_AUTH_SECONDS)}
        return {'token': token, 'tokenType': 'Bearer',
                'expiresInSeconds': _AUTH_SECONDS, 'displayName': user['displayName']}


@app.get('/api/auth/me')
def me(authorization: str | None = Header(default=None)):
    user = _principal(authorization)
    return {'userId': user['userId'], 'username': user['username'],
            'displayName': user['displayName'],
            'phoneMasked': user['phone'][:3] + '****' + user['phone'][-4:]}


@app.post('/api/auth/logout')
def logout(authorization: str | None = Header(default=None)):
    user = _principal(authorization)
    with _lock:
        _tokens.pop(authorization[7:].strip(), None)
    return {'status': 'logged_out'}


@app.get('/api/demo/balance')
def balance(authorization: str | None = Header(default=None)):
    user = _principal(authorization)
    with _lock:
        return {'userName': user['displayName'], 'accountNoMasked': _masked_account(user['userId']),
                'balance': _money(_accounts[user['userId']]), 'currency': 'CNY'}


@app.get('/api/demo/transactions')
def transactions(authorization: str | None = Header(default=None)):
    user = _principal(authorization)
    with _lock:
        return [dict(x) for x in _transactions[user['userId']]]


@app.get('/api/demo/payees')
def payees(authorization: str | None = Header(default=None)):
    user = _principal(authorization)
    with _lock:
        return [{'id': target['userId'], 'payeeName': target['displayName'],
                 'payeeAccountMasked': _masked_account(target['userId'])}
                for target in _users.values() if target['userId'] != user['userId']]


@app.get('/api/demo/subscriptions')
def subscriptions(authorization: str | None = Header(default=None)):
    user = _principal(authorization)
    with _lock:
        return [{key: val for key, val in sub.items() if key != 'userId'}
                for sub in _subscriptions.values() if sub['userId'] == user['userId']]


@app.get('/api/demo/analytics/monthly')
def monthly(month: str, authorization: str | None = Header(default=None)):
    user = _principal(authorization)
    if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', month):
        raise HTTPException(400, '月份格式必须为 YYYY-MM。')
    with _lock:
        records = [x for x in _transactions[user['userId']] if x['occurredAt'][:7] == month]
    income = sum((Decimal(x['amount']) for x in records if x['direction'] == 'IN'), Decimal('0'))
    expense = sum((Decimal(x['amount']) for x in records if x['direction'] == 'OUT'), Decimal('0'))
    categories: dict[str, tuple[Decimal, int]] = {}
    for item in records:
        if item['direction'] == 'OUT':
            key = item['category']
            amount, count = categories.get(key, (Decimal('0'), 0))
            categories[key] = (amount + Decimal(item['amount']), count + 1)
    return {'month': month, 'currency': 'CNY', 'totalIncome': _money(income),
            'totalExpense': _money(expense), 'netCashFlow': _money(income - expense),
            'categories': [{'name': k, 'amount': _money(v), 'count': n}
                           for k, (v, n) in sorted(categories.items())], 'source': 'mock'}


class ConfirmRecipientBody(BaseModel):
    recipientId: int = Field(gt=0)


@app.get('/api/transfers/recipients/search')
def search_recipients(name: str | None = None, phone: str | None = None,
                      authorization: str | None = Header(default=None)):
    """Mock only: directory includes every registered user EXCEPT current payer."""
    user = _principal(authorization)
    if not name and not phone:
        raise HTTPException(422, '姓名和手机号不能同时为空。')
    if name is not None and (not name.strip() or len(name) > 50):
        raise HTTPException(422, '姓名无效。')
    if phone is not None and not re.fullmatch(r'1[3-9]\d{9}', phone):
        raise HTTPException(422, '手机号无效。')
    with _lock:
        found = [u for u in _users.values()
                 if u['userId'] != user['userId']
                 and (not name or u['displayName'] == name.strip())
                 and (not phone or u['phone'] == phone)]
        if len(found) > 30:
            raise HTTPException(409, '同名用户过多，请改用唯一手机号定位。')
        return [{'recipientId': u['userId'], 'payeeName': u['displayName'],
                 'accountMasked': _masked_account(u['userId'])} for u in found]


@app.post('/api/transfers/recipients/confirm')
def confirm_recipient(body: ConfirmRecipientBody,
                      authorization: str | None = Header(default=None)):
    """Recheck the selected bank user; simulate current payer's payee binding."""
    user = _principal(authorization)
    with _lock:
        target = _users.get(body.recipientId)
        if not target or target['userId'] == user['userId']:
            raise HTTPException(404, '不能确认该收款账户。')
        return {'id': target['userId'], 'payeeName': target['displayName'],
                'payeeAccountMasked': _masked_account(target['userId'])}


@app.post('/api/transfers/prepare')
def prepare(body: TransferPrepare, authorization: str | None = Header(default=None)):
    user = _principal(authorization)
    amount = _parse_amount(body.amount)
    uid = user['userId']
    with _lock:
        target = _users.get(body.payeeId)
        if not target or target['userId'] == uid:
            raise HTTPException(404, '收款人不存在。')
        prior_id = _transfer_request_keys.get((uid, body.requestId))
        if prior_id:
            prior = _orders[prior_id]
            if (prior['toUserId'] != body.payeeId or prior['amount'] != _money(amount)
                    or prior['remark'] != body.remark):
                raise HTTPException(409, '转账幂等键对应不同参数。')
            return _transfer_view(prior)
        oid = 'MOCK-TF-' + uuid4().hex[:18]
        order = {'orderId': oid, 'fromUserId': uid, 'toUserId': body.payeeId,
                 'payeeName': target['displayName'], 'accountMasked': _masked_account(body.payeeId),
                 'amount': _money(amount), 'remark': body.remark, 'riskLevel': 'YELLOW',
                 'status': 'PENDING_APPROVAL', 'strongVerified': False, 'otpTries': 0,
                 'otpIssuedUntil': None,
                 'createdDate': _now().astimezone(timezone(timedelta(hours=8))).date().isoformat()}
        _orders[oid] = order
        _transfer_request_keys[(uid, body.requestId)] = oid
        order['riskLevel'] = _risk(uid)
        return _transfer_view(order)


@app.get('/api/transfers/{order_id}')
def get_transfer(order_id: str, authorization: str | None = Header(default=None)):
    uid = _principal(authorization)['userId']
    with _lock:
        return _transfer_view(_order(order_id, uid))


@app.post('/api/transfers/{order_id}/otp/request')
def request_otp(order_id: str, authorization: str | None = Header(default=None)):
    uid = _principal(authorization)['userId']
    with _lock:
        order = _order(order_id, uid)
        if _risk(uid) == 'RED':
            order['riskLevel'] = 'RED'
        if order['status'] != 'PENDING_APPROVAL' or order['riskLevel'] != 'RED':
            raise HTTPException(409, '只有等待审批的 RED 订单可以申请 OTP。')
        order['otpIssuedUntil'] = _now() + timedelta(seconds=120)
        return {'orderId': order_id, 'expiresInSeconds': 120, 'status': 'MOCK_ONLY'}


@app.post('/api/transfers/{order_id}/authorize')
def authorize(order_id: str, body: TransferApprove, authorization: str | None = Header(default=None)):
    uid = _principal(authorization)['userId']
    with _lock:
        order = _order(order_id, uid)
        if order['status'] == 'AUTHORIZED':
            return _transfer_view(order)
        if order['status'] != 'PENDING_APPROVAL' or not body.confirmation:
            raise HTTPException(409, '订单不在待确认状态。')
        if _risk(uid) == 'RED':
            order['riskLevel'] = 'RED'
        if order['riskLevel'] == 'RED':
            if (not order['otpIssuedUntil'] or order['otpIssuedUntil'] < _now()
                    or body.otpCode != _DEMO_OTP):
                order['otpTries'] += 1
                if order['otpTries'] >= 5:
                    order['status'] = 'LOCKED'
                raise HTTPException(403, '模拟 OTP 错误、未申请或已过期。')
            order['strongVerified'] = True
        order['status'] = 'AUTHORIZED'
        order['authorizedUntil'] = _now() + timedelta(minutes=5)
        return _transfer_view(order)



def _commit_mock_transfer(order: dict) -> None:
    """Single mock ledger operation shared by ordinary, AA and due schedules.
    Caller holds the RLock; Java uses one MySQL transaction instead.
    """
    uid, target_uid = order['fromUserId'], order['toUserId']
    amount = Decimal(order['amount'])
    _accounts[uid] -= amount
    _accounts[target_uid] += amount
    timestamp = _now().isoformat()
    for account_id, direction, peer in ((uid, 'OUT', target_uid), (target_uid, 'IN', uid)):
        _transactions[account_id].append({
            'id': len(_transactions[account_id]) + 1,
            'direction': direction, 'amount': order['amount'], 'category': '转账',
            'merchantName': _users[peer]['displayName'], 'remark': order['remark'], 'occurredAt': timestamp,
        })
    order['status'] = 'SUCCESS'
    if order.get('aaItemId'):
        item = _aa_items[order['aaItemId']]
        item['status'] = 'PAID'
        item['transferOrderId'] = order['orderId']
    order['transferId'] = 'MOCK-TXN-' + uuid4().hex[:14]
    order['balanceAfter'] = _money(_accounts[uid])


@app.post('/api/transfers/{order_id}/execute')
def execute(order_id: str, body: RequestId, authorization: str | None = Header(default=None)):
    uid = _principal(authorization)['userId']
    with _lock:
        order = _order(order_id, uid)
        if order['status'] == 'SUCCESS':
            return _transfer_view(order)
        if order['status'] != 'AUTHORIZED' or order.get('authorizedUntil', _now()) <= _now():
            raise HTTPException(409, '订单未授权或已过期。')
        if _risk(uid) == 'RED' and not order['strongVerified']:
            order['riskLevel'] = 'RED'
            order['status'] = 'PENDING_APPROVAL'
            raise HTTPException(409, '风险升级，需要 OTP。')
        amount = Decimal(order['amount'])
        if _accounts[uid] < amount:
            order['status'] = 'FAILED'
            raise HTTPException(409, '余额不足。')
        _commit_mock_transfer(order)
        return _transfer_view(order)


@app.post('/api/transfers/{order_id}/cancel')
def cancel_transfer(order_id: str, body: RequestId, authorization: str | None = Header(default=None)):
    uid = _principal(authorization)['userId']
    with _lock:
        order = _order(order_id, uid)
        if order['status'] == 'CANCELLED':
            return _transfer_view(order)
        if order['status'] not in ('PENDING_APPROVAL', 'AUTHORIZED', 'LOCKED'):
            raise HTTPException(409, '订单不可取消。')
        order['status'] = 'CANCELLED'
        if order.get('aaItemId'):
            _aa_items[order['aaItemId']]['status'] = 'FAILED'
        return _transfer_view(order)


@app.post('/api/subscription-cancellations/prepare')
def cancel_prepare(body: CancellationPrepare, authorization: str | None = Header(default=None)):
    uid = _principal(authorization)['userId']
    with _lock:
        sub = _subscription(body.subscriptionId, uid)
        prior_id = _cancel_request_keys.get((uid, body.requestId))
        if prior_id:
            prior = _cancellations[prior_id]
            if prior['subscriptionId'] != sub['id']:
                raise HTTPException(409, '取消幂等键冲突。')
            return _cancel_view(prior)
        if sub['status'] != 'ACTIVE':
            raise HTTPException(409, '协议已经取消。')
        if any(o['subscriptionId'] == sub['id'] and o['status'] in ('PENDING_APPROVAL', 'AUTHORIZED')
               for o in _cancellations.values()):
            raise HTTPException(409, '已有待处理的取消申请。')
        oid = 'MOCK-SC-' + uuid4().hex[:18]
        order = {'orderId': oid, 'userId': uid, 'subscriptionId': sub['id'],
                 'status': 'PENDING_APPROVAL'}
        _cancellations[oid] = order
        _cancel_request_keys[(uid, body.requestId)] = oid
        return _cancel_view(order)


@app.get('/api/subscription-cancellations/{order_id}')
def cancel_status(order_id: str, authorization: str | None = Header(default=None)):
    uid = _principal(authorization)['userId']
    with _lock:
        return _cancel_view(_cancellation(order_id, uid))


@app.post('/api/subscription-cancellations/{order_id}/authorize')
def cancel_authorize(order_id: str, body: CancellationApprove, authorization: str | None = Header(default=None)):
    uid = _principal(authorization)['userId']
    with _lock:
        order = _cancellation(order_id, uid)
        if order['status'] != 'PENDING_APPROVAL' or not body.confirmed:
            raise HTTPException(409, '取消申请无法授权。')
        order['status'] = 'AUTHORIZED'
        return _cancel_view(order)


@app.post('/api/subscription-cancellations/{order_id}/execute')
def cancel_execute(order_id: str, body: RequestId, authorization: str | None = Header(default=None)):
    uid = _principal(authorization)['userId']
    with _lock:
        order = _cancellation(order_id, uid)
        if order['status'] == 'SUCCESS':
            return _cancel_view(order)
        if order['status'] != 'AUTHORIZED':
            raise HTTPException(409, '取消申请尚未授权。')
        _subscription(order['subscriptionId'], uid)['status'] = 'CANCELLED'
        order['status'] = 'SUCCESS'
        return _cancel_view(order)


@app.post('/api/subscription-cancellations/{order_id}/reject')
def cancel_reject(order_id: str, body: RequestId, authorization: str | None = Header(default=None)):
    uid = _principal(authorization)['userId']
    with _lock:
        order = _cancellation(order_id, uid)
        if order['status'] == 'REJECTED':
            return _cancel_view(order)
        if order['status'] != 'PENDING_APPROVAL':
            raise HTTPException(409, '当前不能拒绝取消。')
        order['status'] = 'REJECTED'
        return _cancel_view(order)


# === Day 7 stage 4 local-only scheduled transfer simulation. ===
class ScheduledPrepare(RequestId):
    payeeId: int = Field(gt=0)
    amount: str
    executeAt: str
    remark: str = Field(default='', max_length=80)


class ScheduledAuthorize(RequestId):
    confirmed: bool
    otpCode: str | None = None


def _schedule(sid: str, uid: int) -> dict:
    item = _schedules.get(sid)
    if not item or item['ownerId'] != uid:
        raise HTTPException(404, '预约不存在或不属于当前用户。')
    return item


def _schedule_view(item: dict) -> dict:
    return {k: v for k, v in item.items()
            if k not in ('ownerId', 'payeeId', 'otpIssuedUntil', 'otpTries', 'authorization')}


def _datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() != timedelta(hours=8):
            raise ValueError('timezone')
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        raise HTTPException(422, '预约执行时间必须是有效的 +08:00 ISO 时间。')


@app.post('/api/scheduled-transfers/prepare')
def schedule_prepare(body: ScheduledPrepare, authorization: str | None = Header(default=None)):
    uid = _principal(authorization)['userId']
    amount = _parse_amount(body.amount)
    target_at = _datetime(body.executeAt)
    if target_at <= _now():
        raise HTTPException(422, '只能预约明确的未来时间。')
    with _lock:
        target = _users.get(body.payeeId)
        if not target or target['userId'] == uid:
            raise HTTPException(404, '收款人不存在或不可转给本人。')
        previous = _schedule_keys.get((uid, body.requestId))
        if previous:
            old = _schedules[previous]
            if (old['payeeId'] != body.payeeId or old['amount'] != _money(amount)
                    or old['executeAt'] != body.executeAt or old['remark'] != body.remark):
                raise HTTPException(409, '预约幂等键被重复用于不同业务。')
            return _schedule_view(old)
        sid = 'MOCK-ST-' + uuid4().hex[:18]
        item = {'scheduleId': sid, 'ownerId': uid, 'payeeId': body.payeeId,
                'payeeName': target['displayName'], 'accountMasked': _masked_account(body.payeeId),
                'amount': _money(amount), 'remark': body.remark, 'executeAt': body.executeAt,
                'status': 'PENDING_AUTH', 'otpIssuedUntil': None, 'otpTries': 0,
                'orderId': None, 'failureReason': None, 'authorization': None}
        _schedules[sid] = item
        _schedule_keys[(uid, body.requestId)] = sid
        return _schedule_view(item)


@app.get('/api/scheduled-transfers/mine')
def schedules_mine(authorization: str | None = Header(default=None)):
    uid = _principal(authorization)['userId']
    with _lock:
        return [_schedule_view(s) for s in _schedules.values() if s['ownerId'] == uid]


@app.get('/api/scheduled-transfers/{schedule_id}')
def schedule_get(schedule_id: str, authorization: str | None = Header(default=None)):
    uid = _principal(authorization)['userId']
    with _lock:
        return _schedule_view(_schedule(schedule_id, uid))


@app.post('/api/scheduled-transfers/{schedule_id}/otp/request')
def schedule_request_otp(schedule_id: str, authorization: str | None = Header(default=None)):
    uid = _principal(authorization)['userId']
    with _lock:
        item = _schedule(schedule_id, uid)
        if item['status'] != 'PENDING_AUTH':
            raise HTTPException(409, '预约不是待OTP状态。')
        item['otpIssuedUntil'] = _now() + timedelta(seconds=120)
        return {'scheduleId': schedule_id, 'status': 'OTP_REQUESTED', 'expiresInSeconds': 120}


@app.post('/api/scheduled-transfers/{schedule_id}/authorize')
def schedule_authorize(schedule_id: str, body: ScheduledAuthorize,
                       authorization: str | None = Header(default=None)):
    uid = _principal(authorization)['userId']
    with _lock:
        item = _schedule(schedule_id, uid)
        if item['status'] == 'SCHEDULED' and item['authorization'] == body.requestId:
            return _schedule_view(item)
        if item['status'] != 'PENDING_AUTH' or body.confirmed is not True:
            raise HTTPException(409, '预约不允许继续授权。')
        if _datetime(item['executeAt']) <= _now():
            item['status'] = 'MISSED'
            item['failureReason'] = '预约时间已过，未完成授权，不能补执行'
            raise HTTPException(409, '预约执行时间已过，不能授权。')
        if (item['otpIssuedUntil'] is None or _now() > item['otpIssuedUntil']
                or body.otpCode != _DEMO_OTP):
            item['otpTries'] += 1
            if item['otpTries'] >= 5:
                item['status'] = 'FAILED'
                item['failureReason'] = '模拟OTP尝试次数耗尽'
            raise HTTPException(403, '预约 OTP 错误、未申请或已过期。')
        item['authorization'] = body.requestId  # bind immutable schedule contents by id
        item['status'] = 'SCHEDULED'
        return _schedule_view(item)


@app.post('/api/scheduled-transfers/{schedule_id}/cancel')
def schedule_cancel(schedule_id: str, body: RequestId,
                    authorization: str | None = Header(default=None)):
    uid = _principal(authorization)['userId']
    with _lock:
        item = _schedule(schedule_id, uid)
        if item['status'] == 'CANCELLED':
            return _schedule_view(item)
        if item['status'] not in ('PENDING_AUTH', 'SCHEDULED'):
            raise HTTPException(409, '当前预约已经执行、错过或失败，不允许取消。')
        item['status'] = 'CANCELLED'
        item['authorization'] = None
        return _schedule_view(item)


def _process_due(now: datetime | None = None):
    """Called by background worker; <=60 s start tolerance, otherwise MISSED.
    Never catch up old missed schedules, never retry failed transfers.
    """
    instant = (now or _now()).astimezone(timezone.utc)
    with _lock:
        for item in _schedules.values():
            if item['status'] != 'SCHEDULED':
                continue
            due = _datetime(item['executeAt'])
            if due > instant:
                continue
            if instant - due > timedelta(seconds=60):
                item['status'], item['failureReason'] = 'MISSED', '超过指定执行窗口，按业务规则不补执行'
                continue
            if not item['authorization']:
                item['status'], item['failureReason'] = 'FAILED', '缺少有效的预约强验证预授权'
                continue
            uid = item['ownerId']
            amount = Decimal(item['amount'])
            if _accounts[uid] < amount:
                item['status'], item['failureReason'] = 'FAILED', '执行时余额不足；不自动重试'
                continue
            # The actual order is born on EXECUTION day; its date participates
            # in the same _risk() calculation as ordinary and AA orders.
            oid = 'MOCK-TF-' + uuid4().hex[:18]
            order = {'orderId': oid, 'fromUserId': uid, 'toUserId': item['payeeId'],
                     'payeeName': item['payeeName'], 'accountMasked': item['accountMasked'],
                     'amount': item['amount'], 'remark': item['remark'], 'riskLevel': 'RED',
                     'status': 'AUTHORIZED', 'strongVerified': True, 'otpTries': 0,
                     'otpIssuedUntil': None, 'authorizedUntil': None,
                     'createdDate': instant.astimezone(timezone(timedelta(hours=8))).date().isoformat(),
                     'scheduleId': item['scheduleId']}
            _orders[oid] = order
            order['riskLevel'] = _risk(uid)  # execution-day total, including this order
            item['status'] = 'PROCESSING'
            _commit_mock_transfer(order)  # one lock, both balances + both ledgers
            item['orderId'] = oid
            item['status'] = 'SUCCESS'


def _schedule_background():
    while not _scheduler_stop.wait(1):
        try:
            _process_due()
        except Exception:
            # Unknown backend outcome: do not blindly repeat a side effect.
            with _lock:
                for value in _schedules.values():
                    if value['status'] == 'PROCESSING':
                        value['status'] = 'UNKNOWN'
                        value['failureReason'] = '执行结果待核实；不会自动重试'


@app.on_event('startup')
def start_schedule_worker():
    _scheduler_stop.clear()
    Thread(target=_schedule_background, daemon=True, name='bankpilot-mock-scheduler').start()


@app.on_event('shutdown')
def stop_schedule_worker():
    _scheduler_stop.set()


# === Day 7 stage 3 mock AA collection. Local RAM only. ===
class AAPrepare(BaseModel):
    participants: list[str] = Field(min_length=1, max_length=10)
    amount: str
    splitMode: str
    reason: str = Field(default='', max_length=80)
    requestId: str = Field(min_length=8, max_length=64)


class AAPaymentConfirm(RequestId):
    confirmed: bool
    otpCode: str | None = None


def _aa_collection(cid: str, uid: int) -> dict:
    record = _aa_collections.get(cid)
    if not record or record['initiatorId'] != uid:
        raise HTTPException(404, 'AA 收款单不存在或不属于当前用户。')
    return record


def _aa_item(iid: str, uid: int) -> dict:
    item = _aa_items.get(iid)
    if not item or item['payerId'] != uid:
        raise HTTPException(404, 'AA 付款请求不存在或不属于当前用户。')
    return item


def _aa_public_item(item: dict) -> dict:
    return {k: v for k, v in item.items() if k not in ('payerId',)} | {
        'payerId': item['payerId']}


def _aa_view(collection: dict) -> dict:
    items = [_aa_public_item(_aa_items[iid]) for iid in collection['itemIds']]
    status = collection['status']
    if status == 'PUBLISHED' or status == 'PARTIAL':
        paid = sum(x['status'] == 'PAID' for x in items)
        if paid == len(items):
            status = 'COMPLETED'
        elif paid:
            status = 'PARTIAL'
        else:
            status = 'PUBLISHED'
    received = sum((Decimal(x['amount']) for x in items if x['status'] == 'PAID'), Decimal('0'))
    return {'collectionId': collection['collectionId'], 'initiatorId': collection['initiatorId'],
            'initiatorName': _users[collection['initiatorId']]['displayName'],
            'status': status, 'splitMode': collection['splitMode'],
            'reason': collection['reason'], 'totalAmount': collection['totalAmount'],
            'selfAmount': collection['selfAmount'], 'requestedAmount': collection['requestedAmount'],
            'receivedAmount': _money(received), 'items': items}


@app.post('/api/aa/prepare')
def aa_prepare(body: AAPrepare, authorization: str | None = Header(default=None)):
    uid = _principal(authorization)['userId']
    amount = _parse_amount(body.amount)
    if body.splitMode not in ('total_with_self', 'per_person'):
        raise HTTPException(422, 'AA 分摊方式错误。')
    if len(set(body.participants)) != len(body.participants) or any(
            not x.strip() or x != x.strip() for x in body.participants):
        raise HTTPException(422, 'AA 收款人重复或名称无效。')
    with _lock:
        targets = []
        for name in body.participants:
            found = [u for u in _users.values()
                     if u['userId'] != uid and (u['phone'] == name if re.fullmatch(r'1[3-9]\d{9}', name)
                                                   else u['displayName'] == name)]
            if len(found) != 1:
                raise HTTPException(409, 'AA 参与者未注册或存在同名用户；请用明确的唯一用户信息重新发起。')
            targets.append(found[0])
        if len({x['userId'] for x in targets}) != len(targets):
            raise HTTPException(409, 'AA 收款对象不可重复。')
        prior_id = _aa_request_keys.get((uid, body.requestId))
        if prior_id:
            prior = _aa_collections[prior_id]
            if (prior['participantNames'] != body.participants or prior['sourceAmount'] != _money(amount)
                    or prior['splitMode'] != body.splitMode or prior['reason'] != body.reason):
                raise HTTPException(409, 'AA 幂等键对应的金额或对象不同。')
            return _aa_view(prior)
        cents = int(amount * 100)
        if body.splitMode == 'total_with_self':
            share, remain = divmod(cents, len(targets) + 1)
            distributed = [share + (i < remain) for i in range(len(targets) + 1)]
            self_cents = distributed[-1]
            requested = distributed[:-1]
        else:
            self_cents = 0
            requested = [cents] * len(targets)
        if any(x <= 0 for x in requested):
            raise HTTPException(422, 'AA 金额太小，部分付款请求无法按分计算。')
        cid = 'MOCK-AA-' + uuid4().hex[:18]
        ids = []
        for target, part in zip(targets, requested):
            iid = 'MOCK-AI-' + uuid4().hex[:18]
            _aa_items[iid] = {'itemId': iid, 'collectionId': cid, 'payerId': target['userId'],
                              'payerName': target['displayName'], 'amount': _money(Decimal(part) / 100),
                              'status': 'PENDING', 'transferOrderId': None}
            ids.append(iid)
        collection = {'collectionId': cid, 'initiatorId': uid, 'itemIds': ids,
                      'participantNames': list(body.participants), 'sourceAmount': _money(amount),
                      'reason': body.reason, 'splitMode': body.splitMode, 'status': 'DRAFT',
                      'totalAmount': _money(amount if body.splitMode == 'total_with_self'
                                            else amount * len(targets)),
                      'selfAmount': _money(Decimal(self_cents) / 100),
                      'requestedAmount': _money(sum(Decimal(x) for x in requested) / 100)}
        _aa_collections[cid] = collection
        _aa_request_keys[(uid, body.requestId)] = cid
        return _aa_view(collection)


@app.get('/api/aa/outgoing')
def aa_outgoing(authorization: str | None = Header(default=None)):
    uid = _principal(authorization)['userId']
    with _lock:
        return [_aa_view(c) for c in _aa_collections.values()
                if c['initiatorId'] == uid and c['status'] not in ('DRAFT', 'CANCELLED')]


@app.get('/api/aa/inbox')
def aa_inbox(authorization: str | None = Header(default=None)):
    uid = _principal(authorization)['userId']
    with _lock:
        result = []
        for item in _aa_items.values():
            if item['payerId'] != uid:
                continue
            collection = _aa_collections[item['collectionId']]
            if collection['status'] in ('DRAFT', 'CANCELLED'):
                continue
            result.append(_aa_public_item(item) | {
                'initiatorName': _users[collection['initiatorId']]['displayName'],
                'reason': collection['reason']})
        return result


@app.get('/api/aa/{collection_id}')
def aa_get(collection_id: str, authorization: str | None = Header(default=None)):
    uid = _principal(authorization)['userId']
    with _lock:
        return _aa_view(_aa_collection(collection_id, uid))


@app.post('/api/aa/{collection_id}/publish')
def aa_publish(collection_id: str, body: RequestId,
               authorization: str | None = Header(default=None)):
    uid = _principal(authorization)['userId']
    with _lock:
        c = _aa_collection(collection_id, uid)
        if c['status'] not in ('DRAFT', 'PUBLISHED'):
            raise HTTPException(409, 'AA 申请不能发布。')
        c['status'] = 'PUBLISHED'
        return _aa_view(c)


@app.post('/api/aa/{collection_id}/cancel-draft')
def aa_cancel_draft(collection_id: str, body: RequestId,
                    authorization: str | None = Header(default=None)):
    uid = _principal(authorization)['userId']
    with _lock:
        c = _aa_collection(collection_id, uid)
        if c['status'] not in ('DRAFT', 'CANCELLED'):
            raise HTTPException(409, 'AA 收款请求已发布，不能按草稿拒绝。')
        c['status'] = 'CANCELLED'
        return _aa_view(c)


@app.post('/api/aa/items/{item_id}/payment/prepare')
def aa_payment_prepare(item_id: str, body: RequestId,
                       authorization: str | None = Header(default=None)):
    uid = _principal(authorization)['userId']
    with _lock:
        item = _aa_item(item_id, uid)
        col = _aa_collections[item['collectionId']]
        if col['status'] == 'DRAFT' or col['status'] == 'CANCELLED':
            raise HTTPException(409, 'AA 尚未正式发布。')
        if item['status'] == 'PAYING' and item.get('transferOrderId'):
            return _transfer_view(_order(item['transferOrderId'], uid))
        if item['status'] != 'PENDING':
            raise HTTPException(409, '该 AA 请求已经处理过。')
        order = prepare(TransferPrepare(payeeId=col['initiatorId'], amount=item['amount'],
                                         requestId=body.requestId, remark='AA:' + col['reason']), authorization)
        internal = _order(order['orderId'], uid)
        if internal.get('aaItemId') and internal['aaItemId'] != item_id:
            raise HTTPException(409, '转账订单已关联其他 AA 项目。')
        internal['aaItemId'] = item_id
        item['transferOrderId'] = order['orderId']
        item['status'] = 'PAYING'
        return order


@app.post('/api/aa/items/{item_id}/otp/request')
def aa_payment_otp(item_id: str, authorization: str | None = Header(default=None)):
    uid = _principal(authorization)['userId']
    with _lock:
        item = _aa_item(item_id, uid)
        if item['status'] != 'PAYING' or not item['transferOrderId']:
            raise HTTPException(409, 'AA 付款未处于等待审批状态。')
        return request_otp(item['transferOrderId'], authorization)


@app.post('/api/aa/items/{item_id}/payment/confirm')
def aa_payment_confirm(item_id: str, body: AAPaymentConfirm,
                       authorization: str | None = Header(default=None)):
    uid = _principal(authorization)['userId']
    with _lock:
        item = _aa_item(item_id, uid)
        if item['status'] == 'PAID':
            return _aa_public_item(item)
        if item['status'] != 'PAYING' or not item['transferOrderId'] or body.confirmed is not True:
            raise HTTPException(409, 'AA 付款尚未准备或用户未确认。')
        oid = item['transferOrderId']
        original = _order(oid, uid)
        if original['status'] == 'PENDING_APPROVAL':
            authorize(oid, TransferApprove(confirmation=True, otpCode=body.otpCode,
                                           requestId=body.requestId), authorization)
        try:
            order = execute(oid, RequestId(requestId=body.requestId), authorization)
        except HTTPException:
            if original['status'] == 'FAILED':
                item['status'] = 'FAILED'
            raise
        if order['status'] != 'SUCCESS' or item['status'] != 'PAID':
            raise HTTPException(409, '银行没有确认 AA 实际入账。')
        return _aa_public_item(item)


@app.post('/api/aa/items/{item_id}/decline')
def aa_decline(item_id: str, body: RequestId,
               authorization: str | None = Header(default=None)):
    uid = _principal(authorization)['userId']
    with _lock:
        item = _aa_item(item_id, uid)
        if item['status'] == 'DECLINED':
            return _aa_public_item(item)
        if item['status'] == 'PAYING' and item.get('transferOrderId'):
            original = _order(item['transferOrderId'], uid)
            if original['status'] not in ('PENDING_APPROVAL', 'AUTHORIZED', 'LOCKED'):
                raise HTTPException(409, '银行原付款订单已开始执行或完成，不允许拒绝。')
            cancel_transfer(original['orderId'], RequestId(requestId=body.requestId), authorization)
        elif item['status'] != 'PENDING':
            raise HTTPException(409, 'AA 请求已经处理，不允许拒绝。')
        item['status'] = 'DECLINED'
        return _aa_public_item(item)


@app.get('/api/aa/items/{item_id}/payment')
def aa_payment_status(item_id: str, authorization: str | None = Header(default=None)):
    uid = _principal(authorization)['userId']
    with _lock:
        item = _aa_item(item_id, uid)
        if not item.get('transferOrderId'):
            raise HTTPException(404, 'AA 项目尚未创建实际转账订单。')
        return _transfer_view(_order(item['transferOrderId'], uid))
