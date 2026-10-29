"""Day 6 transfer approval nodes: explicit consent, bank-enforced OTP, verified status.

Never persist OTP in LangGraph State. It is supplied only in runtime context.
"""
from decimal import Decimal
from uuid import uuid4

from langgraph.types import interrupt

from app import banking_client as bank


def _checked_order(state: dict, order: dict, expected: str | None = None) -> dict:
    """Validate immutable recipient and amount against the approved bank order."""
    candidate = state['transferCandidate']
    previous = state['transferOrder']
    try:
        ok = (
            isinstance(order, dict)
            and str(order['orderId']) == str(previous['orderId'])
            and str(order['payeeName']).strip() == candidate['payeeName']
            and str(order['accountMasked']) == candidate['accountMasked']
            and Decimal(str(order['amount'])) == Decimal(candidate['amount'])
            and order['riskLevel'] in ('YELLOW', 'RED')
            and (expected is None or order['status'] == expected)
        )
    except (KeyError, ValueError, TypeError, ArithmeticError):
        ok = False
    if not ok:
        raise bank.BankError('银行转账订单与已批准的收款人、金额或状态不一致，禁止继续。', 409)
    return order


def assign_transfer_approval_ids(state: dict) -> dict:
    return {
        'transferAuthorizeRequestId': uuid4().hex,
        'transferExecuteRequestId': uuid4().hex,
        'transferCancelRequestId': uuid4().hex,
    }


def wait_transfer_approval(state: dict) -> dict:
    # This node has NO bank side effect. It is re-entered on Command(resume=...).
    choice = interrupt({
        'kind': 'TRANSFER_APPROVAL',
        'orderId': state['transferOrder']['orderId'],
        'payee': state['transferCandidate']['payeeName'],
        'accountMasked': state['transferCandidate']['accountMasked'],
        'amount': state['transferCandidate']['amount'],
        'riskLevel': state['transferOrder']['riskLevel'],
        'notice': '请核对收款人、账户尾号和金额。RED 风险还需银行 OTP。',
    })
    if type(choice) is not bool:
        return {'status': 'INVALID_TRANSFER_DECISION',
                'details': '审批必须是明确的 true 或 false；未执行转账。'}
    return {'transferDecision': choice,
            'status': 'TRANSFER_APPROVED' if choice else 'TRANSFER_DECLINED'}


def after_transfer_decision(state: dict):
    if state['status'] == 'TRANSFER_APPROVED':
        return 'transfer_authorize'
    if state['status'] == 'TRANSFER_DECLINED':
        return 'transfer_cancel'
    return '__end__'


async def transfer_authorize_node(state: dict, runtime) -> dict:
    bearer = runtime.context['authorization']
    oid = str(state['transferOrder']['orderId'])
    current = _checked_order(state, await bank.get_order(oid, bearer))
    if current['status'] == 'SUCCESS':
        return {'transferOrder': current, 'status': 'TRANSFER_EXECUTED_PENDING_VERIFICATION'}
    if current['status'] == 'AUTHORIZED':
        return {'transferOrder': current, 'status': 'TRANSFER_AUTHORIZED'}
    if current['status'] != 'PENDING_APPROVAL':
        raise bank.BankError('转账订单已不处于待审批状态，不允许授权。', 409)
    otp = runtime.context.get('transferOtpCode')
    if current['riskLevel'] == 'RED' and not otp:
        raise bank.BankError('当前为 RED 风险，请先申请 OTP 并提供验证码。', 422)
    try:
        authorized = await bank.authorize_transfer(
            oid, bearer, True, otp, state['transferAuthorizeRequestId'])
    except bank.BankError:
        latest = _checked_order(state, await bank.get_order(oid, bearer))
        if latest['status'] not in ('AUTHORIZED', 'SUCCESS'):
            raise
        authorized = latest
    authorized = _checked_order(state, authorized)
    if authorized['status'] == 'SUCCESS':
        return {'transferOrder': authorized, 'status': 'TRANSFER_EXECUTED_PENDING_VERIFICATION'}
    if authorized['status'] != 'AUTHORIZED':
        raise bank.BankError('转账未授权；如风险已升级到 RED，请先申请 OTP 再重试。', 409)
    return {'transferOrder': authorized, 'status': 'TRANSFER_AUTHORIZED'}


def after_transfer_authorize(state: dict):
    return ('transfer_verify_success'
            if state['status'] == 'TRANSFER_EXECUTED_PENDING_VERIFICATION'
            else 'transfer_execute')


async def transfer_execute_node(state: dict, runtime) -> dict:
    bearer = runtime.context['authorization']
    oid = str(state['transferOrder']['orderId'])
    current = _checked_order(state, await bank.get_order(oid, bearer))
    if current['status'] == 'SUCCESS':
        return {'transferOrder': current, 'status': 'TRANSFER_EXECUTED_PENDING_VERIFICATION'}
    if current['status'] != 'AUTHORIZED':
        raise bank.BankError('银行尚未授权或授权已失效，不能执行转账。', 409)
    try:
        result = await bank.execute_transfer(oid, bearer, state['transferExecuteRequestId'])
    except bank.BankError:
        result = _checked_order(state, await bank.get_order(oid, bearer))
        if result['status'] != 'SUCCESS':
            raise
    result = _checked_order(state, result)
    if result['status'] != 'SUCCESS':
        raise bank.BankError('银行尚未确认转账成功；请查询订单状态，勿重复提交。', 409)
    return {'transferOrder': result, 'status': 'TRANSFER_EXECUTED_PENDING_VERIFICATION'}


async def transfer_verify_success_node(state: dict, runtime) -> dict:
    order = _checked_order(state, await bank.get_order(
        str(state['transferOrder']['orderId']), runtime.context['authorization']), 'SUCCESS')
    return {'transferOrder': order, 'status': 'COMPLETED',
            'details': '银行已确认模拟转账成功。'}


async def transfer_cancel_node(state: dict, runtime) -> dict:
    bearer = runtime.context['authorization']
    oid = str(state['transferOrder']['orderId'])
    current = _checked_order(state, await bank.get_order(oid, bearer))
    if current['status'] == 'CANCELLED':
        return {'transferOrder': current, 'status': 'TRANSFER_CANCELLED_PENDING_VERIFICATION'}
    if current['status'] not in ('PENDING_APPROVAL', 'AUTHORIZED'):
        raise bank.BankError('转账订单不允许取消，请核查银行状态。', 409)
    try:
        result = await bank.cancel_transfer(oid, bearer, state['transferCancelRequestId'])
    except bank.BankError:
        result = _checked_order(state, await bank.get_order(oid, bearer))
        if result['status'] != 'CANCELLED':
            raise
    result = _checked_order(state, result, 'CANCELLED')
    return {'transferOrder': result, 'status': 'TRANSFER_CANCELLED_PENDING_VERIFICATION'}


async def transfer_verify_cancelled_node(state: dict, runtime) -> dict:
    order = _checked_order(state, await bank.get_order(
        str(state['transferOrder']['orderId']), runtime.context['authorization']), 'CANCELLED')
    return {'transferOrder': order, 'status': 'REJECTED',
            'details': '用户已拒绝，银行已关闭该转账订单，未执行扣款。'}
