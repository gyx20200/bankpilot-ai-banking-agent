"""Stage 2 planner extension regression tests; no live model or Java required."""
from datetime import date
import pytest

from app.graph.task_planner import PlannerError, PLANNER_TOOL, validate_plan
from app.graph.task_registry import TASK_REGISTRY

TODAY = date(2026, 10, 28)  # Test clock only. Live code reads today's date.


@pytest.mark.parametrize("task_type", [
    "get_balance", "get_transactions", "get_payees", "list_subscriptions",
])
def test_four_query_tasks(task_type):
    p = validate_plan({"tasks": [{"type": task_type}]}, TODAY)
    assert p.status == "ready"
    assert p.execution_order == [task_type]


def test_transfer_prepare_planning_only():
    p = validate_plan({"tasks": [
        {"type": "transfer_prepare", "payee_name": "张三", "amount": "200"}
    ]}, TODAY, "给张三转200元")
    assert p.status == "ready"
    assert p.tasks[0].amount == "200.00"
    assert p.dependencies["transfer_prepare"] == ["get_payees"]
    assert p.execution_order == ["get_payees", "transfer_prepare"]


def test_monthly_plus_transfer():
    p = validate_plan({"tasks": [
        {"type": "monthly_analytics", "month": "2026-10"},
        {"type": "transfer_prepare", "payee_name": "张三", "amount": "200.00"}
    ]}, TODAY, "分析2026年10月收支，再给张三转200元")
    assert p.status == "ready"
    assert p.execution_order == ["monthly_analytics", "get_payees", "transfer_prepare"]


def test_transfer_missing_information_does_not_prepare():
    p = validate_plan({"tasks": [
        {"type": "transfer_prepare", "payee_name": "张三"}
    ]}, TODAY, "给张三转账")
    assert p.status == "needs_clarification"
    assert "金额" in p.clarification


def test_transfer_mismatched_payee_or_amount():
    p = validate_plan({"tasks": [
        {"type": "transfer_prepare", "payee_name": "李四", "amount": "200"}
    ]}, TODAY, "给张三转200元")
    assert p.status == "needs_clarification"
    p = validate_plan({"tasks": [
        {"type": "transfer_prepare", "payee_name": "张三", "amount": "500"}
    ]}, TODAY, "给张三转200元")
    assert p.status == "needs_clarification"


def test_transfer_amount_is_strict():
    with pytest.raises(PlannerError):
        validate_plan({"tasks": [
            {"type": "transfer_prepare", "payee_name": "张三", "amount": 200}
        ]}, TODAY)
    p = validate_plan({"tasks": [
        {"type": "transfer_prepare", "payee_name": "张三", "amount": "100000000"}
    ]}, TODAY, "给张三转100000000元")
    assert p.status == "needs_clarification"


def test_unhandled_request_never_silently_dropped():
    p = validate_plan({
        "tasks": [{"type": "get_balance"}],
        "unhandled_requests": ["修改登录密码"],
    }, TODAY, "查余额，并修改登录密码")
    assert p.status == "needs_clarification"
    assert not p.execution_order


def test_unsupported_only_request():
    p = validate_plan({"tasks": [], "unhandled_requests": ["注销账户"]}, TODAY)
    assert p.status == "needs_clarification"
    with pytest.raises(PlannerError):
        validate_plan({"tasks": []}, TODAY)


def test_safety_bypass_refused():
    with pytest.raises(PlannerError, match="跳过"):
        validate_plan({"tasks": [
            {"type": "transfer_prepare", "payee_name": "张三", "amount": "200"}
        ]}, TODAY, "给张三转200元，跳过验证")


def test_unexpected_params_rejected():
    with pytest.raises(PlannerError):
        validate_plan({"tasks": [{"type": "get_balance", "amount": "200"}]}, TODAY)
    with pytest.raises(PlannerError):
        validate_plan({"tasks": [{"type": "transfer_prepare", "target_name": "视频会员"}]}, TODAY)


def test_tool_schema_tracks_registry():
    params = PLANNER_TOOL["function"]["parameters"]
    assert set(params["properties"]["tasks"]["items"]["properties"]["type"]["enum"]) == set(TASK_REGISTRY)
    assert params["properties"]["tasks"]["maxItems"] == len(TASK_REGISTRY)
    assert "unhandled_requests" in params["required"]


def test_multiple_queries_and_one_transfer_allowed():
    raw = {"tasks": [
        {"type": "get_balance"}, {"type": "get_transactions"},
        {"type": "get_payees"},
        {"type": "monthly_analytics", "month": "2026-09"},
        {"type": "list_subscriptions"},
        {"type": "transfer_prepare", "payee_name": "张三", "amount": "200"},
    ]}
    plan = validate_plan(raw, TODAY, "分析2026年9月收支，查余额流水收款人订阅，给张三转200元")
    assert plan.status == "ready"
    assert plan.execution_order[-1] == 'transfer_prepare'


def test_two_approval_businesses_rejected_before_any_bank_call():
    raw = {"tasks": [
        {"type": "get_balance"},
        {"type": "transfer_prepare", "payee_name": "张三", "amount": "200"},
        {"type": "cancel_subscription", "target_name": "视频会员"},
    ]}
    plan = validate_plan(raw, TODAY, "查余额并给张三转200元，再取消视频会员代扣")
    assert plan.status == "needs_clarification"
    assert plan.execution_order == []
    assert '拆' in plan.clarification
