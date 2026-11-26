"""Offline quality gate. No Java, MySQL, DeepSeek, live MCP or bank tokens required."""
import asyncio
import copy
import pytest

from app.skills import runtime
from app.skills.catalog import SKILLS
from app.skills.d12_quality import SkillReportContractError, validate_skill_report, execute_checked_skill

DATA = {
    "monthly_analytics": {
        "month": "2026-10", "source": "mysql", "totalIncome": "3000.00",
        "totalExpense": "1200.00", "netCashFlow": "1800.00",
    },
    "transaction_anomalies": {
        "month": "2026-10", "source": "mysql", "anomalyCount": 2,
    },
    "get_balance": {"balance": "2200.00"},
    "get_transactions": [{"id": 1}],
    "list_subscriptions": [{"status": "ACTIVE"}, {"status": "INACTIVE"}],
}


def setup_mock(monkeypatch, *, failing=None):
    called = []
    monkeypatch.setattr(runtime, "read_mode", lambda: "on")
    monkeypatch.setattr(runtime, "activated_instructions", lambda _: "allowlisted")
    async def fake_mcp(task, bearer):
        assert bearer == "Bearer test-only-not-real"
        called.append(task["type"])
        if task["type"] == failing:
            from app.mcp.policy import MCPReadError
            raise MCPReadError("simulated bank failure")
        return copy.deepcopy(DATA[task["type"]])
    monkeypatch.setattr(runtime, "execute_mcp_read", fake_mcp)
    return called


@pytest.mark.parametrize("skill,params", [
    ("skill_monthly_finance_review", {"month": "2026-10"}),
    ("skill_account_snapshot", {}),
    ("skill_subscription_review", {}),
])
def test_three_skills_complete_with_exact_steps(monkeypatch, skill, params):
    called = setup_mock(monkeypatch)
    report = asyncio.run(execute_checked_skill(skill, params, "Bearer test-only-not-real"))
    assert report["readOnly"] is True
    assert report["dataOrigin"] == "JAVA_MYSQL_VIA_MCP"
    assert called == list(SKILLS[skill].steps)
    assert validate_skill_report(skill, report) is report


def test_future_month_rejected_without_calling_mcp(monkeypatch):
    called = setup_mock(monkeypatch)
    with pytest.raises(runtime.SkillError):
        asyncio.run(execute_checked_skill(
            "skill_monthly_finance_review", {"month": "2099-12"}, "Bearer test-only-not-real"))
    assert called == []


def test_unregistered_skill_rejected_without_calling_mcp(monkeypatch):
    called = setup_mock(monkeypatch)
    with pytest.raises(runtime.SkillError):
        asyncio.run(execute_checked_skill("skill_transfer_money", {}, "Bearer test-only-not-real"))
    assert called == []


def test_bank_failure_does_not_return_partial_success(monkeypatch):
    called = setup_mock(monkeypatch, failing="transaction_anomalies")
    with pytest.raises(runtime.SkillExecutionError):
        asyncio.run(execute_checked_skill(
            "skill_monthly_finance_review", {"month": "2026-10"}, "Bearer test-only-not-real"))
    assert called == ["monthly_analytics", "transaction_anomalies"]


def test_tampered_summary_blocked(monkeypatch):
    setup_mock(monkeypatch)
    result = asyncio.run(runtime.run_skill("skill_account_snapshot", {}, "Bearer test-only-not-real"))
    result["summary"] = "您的存款已翻倍"
    with pytest.raises(SkillReportContractError):
        validate_skill_report("skill_account_snapshot", result)


def test_tampered_step_blocked(monkeypatch):
    setup_mock(monkeypatch)
    result = asyncio.run(runtime.run_skill("skill_subscription_review", {}, "Bearer test-only-not-real"))
    result["steps"][0]["taskType"] = "transfer_execute"
    with pytest.raises(SkillReportContractError):
        validate_skill_report("skill_subscription_review", result)


def test_missing_bearer_rejected_before_mcp(monkeypatch):
    called = setup_mock(monkeypatch)
    with pytest.raises(runtime.SkillError):
        asyncio.run(execute_checked_skill("skill_account_snapshot", {}, ""))
    assert called == []


def test_audit_log_excludes_sensitive_data(monkeypatch, caplog):
    setup_mock(monkeypatch)
    with caplog.at_level("INFO", logger="bankpilot.d12.skill"):
        asyncio.run(execute_checked_skill("skill_account_snapshot", {}, "Bearer test-only-not-real"))
    msg = caplog.text
    assert "bankpilot_skill_d12" in msg
    for secret in ("test-only-not-real", "2200.00", '"balance"', '"id"'):
        assert secret not in msg
