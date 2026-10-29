"""Offline tests: mocked LLM + bank; no model credits, Java, or transfer/cancel writes."""
import asyncio
from datetime import date

import pytest

from app import banking_client as bank
from app.graph import dynamic_read_workflow as flow
from app.graph.task_planner import validate_plan


TOKEN = "Bearer test-dynamic-reader"


def _mock_planner(monkeypatch, raw):
    async def fake_planner(message):
        return validate_plan(raw, today=date(2026, 10, 28), message=message)
    monkeypatch.setattr(flow, "plan_tasks", fake_planner)


def _mock_reads(monkeypatch):
    called = []

    async def balance(auth):
        assert auth == TOKEN
        called.append("get_balance")
        return {"balance": "100.00", "currency": "CNY"}

    async def transactions(auth):
        assert auth == TOKEN
        called.append("get_transactions")
        return []

    async def payees(auth):
        assert auth == TOKEN
        called.append("get_payees")
        return []

    async def subscriptions(auth):
        assert auth == TOKEN
        called.append("list_subscriptions")
        return [{"id": 1, "merchantName": "视频会员", "status": "ACTIVE"}]

    async def monthly(month, auth):
        assert auth == TOKEN
        called.append("monthly_analytics")
        return {"month": month, "totalIncome": "0.00", "totalExpense": "0.00",
                "netCashFlow": "0.00", "categories": [], "currency": "CNY"}

    # The actual handler dictionary was built at import time.  Replace it so
    # these fakes are invoked instead of a real HTTP banking client.
    monkeypatch.setitem(flow.READ_EXECUTORS, "balance", balance)
    monkeypatch.setitem(flow.READ_EXECUTORS, "transactions", transactions)
    monkeypatch.setitem(flow.READ_EXECUTORS, "payees", payees)
    monkeypatch.setitem(flow.READ_EXECUTORS, "subscriptions", subscriptions)
    monkeypatch.setattr(bank, "get_monthly_analytics", monthly)
    return called


def _run(message):
    return asyncio.run(flow.read_graph.ainvoke({"message": message},
                                               context={"authorization": TOKEN}))


@pytest.mark.parametrize("task_type,message", [
    ("get_balance", "查询我的余额"),
    ("get_transactions", "查询交易流水"),
    ("get_payees", "查询常用收款人"),
    ("monthly_analytics", "分析2026年9月收支"),
    ("list_subscriptions", "查询自动扣费"),
])
def test_one_read(monkeypatch, task_type, message):
    raw = {"tasks": [{"type": task_type, "month": "2026-09"} if task_type == "monthly_analytics"
                     else {"type": task_type}]}
    _mock_planner(monkeypatch, raw)
    calls = _mock_reads(monkeypatch)
    output = _run(message)
    assert output["status"] == "COMPLETED"
    assert set(output["results"]) == {task_type}
    assert calls == [task_type]
    if task_type == "monthly_analytics":
        assert output["results"][task_type]["data"]["month"] == "2026-09"


def test_two_parallel_reads(monkeypatch):
    raw = {"tasks": [
        {"type": "monthly_analytics", "month": "2026-09"},
        {"type": "list_subscriptions"},
    ]}
    _mock_planner(monkeypatch, raw)
    calls = _mock_reads(monkeypatch)
    output = _run("分析2026年9月收支，查自动扣费")
    assert output["status"] == "COMPLETED"
    assert set(output["results"]) == {"monthly_analytics", "list_subscriptions"}
    assert set(calls) == {"monthly_analytics", "list_subscriptions"}


def test_all_five_reads(monkeypatch):
    raw = {"tasks": [{"type": t} for t in (
        "get_balance", "get_transactions", "get_payees", "list_subscriptions")]
                    + [{"type": "monthly_analytics", "month": "2026-09"}]}
    _mock_planner(monkeypatch, raw)
    calls = _mock_reads(monkeypatch)
    result = _run("查余额、流水、收款人和订阅，再分析2026年9月收支")
    assert result["status"] == "COMPLETED"
    assert len(result["results"]) == 5
    assert len(calls) == 5


@pytest.mark.parametrize("raw,message", [
    ({"tasks": [{"type": "cancel_subscription", "target_name": "视频会员"}]}, "取消视频会员代扣"),
    ({"tasks": [{"type": "transfer_prepare", "payee_name": "张三", "amount": "200"}]}, "给张三转200元"),
    ({"tasks": [{"type": "get_balance"}, {"type": "cancel_subscription", "target_name": "视频会员"}]}, "查余额并取消视频会员代扣"),
])
def test_mutations_fail_closed(monkeypatch, raw, message):
    _mock_planner(monkeypatch, raw)
    calls = _mock_reads(monkeypatch)
    result = _run(message)
    assert result["status"] == "NOT_IMPLEMENTED_YET"
    assert result.get("results", {}) == {}
    assert calls == []


def test_missing_month_needs_clarification(monkeypatch):
    _mock_planner(monkeypatch, {"tasks": [{"type": "monthly_analytics"}]})
    calls = _mock_reads(monkeypatch)
    result = _run("分析我的消费")
    assert result["status"] == "NEEDS_CLARIFICATION"
    assert "月份" in result["details"]
    assert calls == []
