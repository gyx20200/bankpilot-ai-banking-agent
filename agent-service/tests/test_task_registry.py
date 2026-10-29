"""Offline tests for task registration; no bank service or model key required."""

import pytest
from app.graph.task_registry import TASK_REGISTRY, TaskSpec, resolve_execution_order


def test_all_existing_business_tasks_are_registered():
    assert set(TASK_REGISTRY) == {
        "get_balance", "get_transactions", "get_payees",
        "monthly_analytics", "list_subscriptions", "transfer_prepare",
        "cancel_subscription",
    }


def test_legacy_llm_tool_names_are_mapped_correctly():
    assert TASK_REGISTRY["monthly_analytics"].legacy_tool == "get_monthly_analytics"
    assert TASK_REGISTRY["list_subscriptions"].legacy_tool == "get_subscriptions"
    assert TASK_REGISTRY["transfer_prepare"].legacy_tool == "prepare_transfer"
    assert TASK_REGISTRY["cancel_subscription"].legacy_tool is None


def test_task_parameters_and_risks():
    assert TASK_REGISTRY["monthly_analytics"].required_params == ("month",)
    assert TASK_REGISTRY["cancel_subscription"].required_params == ("target_name",)
    assert TASK_REGISTRY["transfer_prepare"].required_params == ("payee_name", "amount")
    assert TASK_REGISTRY["get_balance"].risk_level == "LOW"
    assert TASK_REGISTRY["cancel_subscription"].risk_level == "MEDIUM"
    assert TASK_REGISTRY["transfer_prepare"].risk_level == "HIGH"


def test_all_dependencies_are_registered():
    for task, spec in TASK_REGISTRY.items():
        assert spec.executor_key, task
        assert all(dep in TASK_REGISTRY for dep in spec.depends_on), task
        assert spec.risk_level in ("LOW", "MEDIUM", "HIGH")


@pytest.mark.parametrize("requested,expected", [
    (["monthly_analytics"], ["monthly_analytics"]),
    (["list_subscriptions"], ["list_subscriptions"]),
    (["cancel_subscription"], ["list_subscriptions", "cancel_subscription"]),
    (["monthly_analytics", "list_subscriptions"], ["monthly_analytics", "list_subscriptions"]),
    (["monthly_analytics", "cancel_subscription"], ["monthly_analytics", "list_subscriptions", "cancel_subscription"]),
    (["list_subscriptions", "cancel_subscription"], ["list_subscriptions", "cancel_subscription"]),
    (["monthly_analytics", "list_subscriptions", "cancel_subscription"], ["monthly_analytics", "list_subscriptions", "cancel_subscription"]),
])
def test_seven_day6_combinations_with_automatic_dependencies(requested, expected):
    assert resolve_execution_order(requested) == expected


def test_transfer_dependency_reuses_existing_payees_task():
    assert resolve_execution_order(["transfer_prepare"]) == ["get_payees", "transfer_prepare"]
    assert resolve_execution_order(["monthly_analytics", "transfer_prepare"]) == [
        "monthly_analytics", "get_payees", "transfer_prepare"
    ]


def test_duplicate_dependencies_are_deduplicated():
    assert resolve_execution_order(["get_payees", "transfer_prepare", "get_payees"]) == [
        "get_payees", "transfer_prepare"
    ]


def test_unknown_task_is_rejected():
    with pytest.raises(ValueError, match="未注册任务"):
        resolve_execution_order(["execute_transfer"])


def test_registry_blocks_cyclic_dependencies(monkeypatch):
    monkeypatch.setitem(TASK_REGISTRY, "cycle_a", TaskSpec("测试", "a", depends_on=("cycle_b",)))
    monkeypatch.setitem(TASK_REGISTRY, "cycle_b", TaskSpec("测试", "b", depends_on=("cycle_a",)))
    with pytest.raises(ValueError, match="循环"):
        resolve_execution_order(["cycle_a"])
