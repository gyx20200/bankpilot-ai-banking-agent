
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.graph import dynamic_read_workflow as workflow


def test_skill_is_dispatched_to_skill_runner(monkeypatch):
    monkeypatch.setenv(
        "BANKPILOT_MCP_READ_MODE", "on"
    )

    report = {
        "skillId": "skill_monthly_finance_review",
        "status": "COMPLETED",
        "readOnly": True,
        "dataOrigin": "JAVA_MYSQL_VIA_MCP",
    }

    runner = AsyncMock(return_value=report)
    direct_mcp = AsyncMock()

    monkeypatch.setattr(
        workflow, "execute_checked_skill", runner
    )
    monkeypatch.setattr(
        workflow, "execute_mcp_read", direct_mcp
    )

    result = asyncio.run(
        workflow.execute_read(
            {
                "task": {
                    "type": "skill_monthly_finance_review",
                    "month": "2026-10",
                }
            },
            SimpleNamespace(
                context={
                    "authorization": "Bearer test-session"
                }
            ),
        )
    )

    runner.assert_awaited_once_with(
        "skill_monthly_finance_review",
        {"month": "2026-10"},
        "Bearer test-session",
    )

    direct_mcp.assert_not_called()

    assert result["results"][
               "skill_monthly_finance_review"
           ]["status"] == "SUCCESS"


def test_skill_failure_never_becomes_success(monkeypatch):
    runner = AsyncMock(
        side_effect=RuntimeError("Skill failed")
    )

    direct_mcp = AsyncMock()

    monkeypatch.setattr(
        workflow, "execute_checked_skill", runner
    )
    monkeypatch.setattr(
        workflow, "execute_mcp_read", direct_mcp
    )

    with pytest.raises(RuntimeError, match="Skill failed"):
        asyncio.run(
            workflow.execute_read(
                {
                    "task": {
                        "type": "skill_account_snapshot"
                    }
                },
                SimpleNamespace(
                    context={
                        "authorization": "Bearer test-session"
                    }
                ),
            )
        )

    direct_mcp.assert_not_called()
