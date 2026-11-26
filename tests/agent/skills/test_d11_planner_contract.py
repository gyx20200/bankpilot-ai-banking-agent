"""Runs with the complete D10 repo + LangGraph installed, after planner edits."""
from datetime import date
from app.graph.task_registry import TASK_REGISTRY,resolve_execution_order
from app.graph.task_planner import validate_plan, PlannerError
import pytest
from app.graph.dynamic_read_workflow import READ_TASK_TYPES


def test_all_skill_tasks_are_only_reads():
    skill_ids={'skill_monthly_finance_review','skill_account_snapshot','skill_subscription_review'}
    assert skill_ids.issubset(READ_TASK_TYPES)
    for skill in skill_ids:
        assert TASK_REGISTRY[skill].risk_level=='LOW'
        assert TASK_REGISTRY[skill].executor_key=='skill'
    assert resolve_execution_order(['skill_monthly_finance_review'])==['skill_monthly_finance_review']


def test_planner_accepts_explicit_month_skill():
    prompt='帮我做2026年10月财务体检，收支和异常一起分析'
    plan=validate_plan({'tasks':[{'type':'skill_monthly_finance_review','month':'2026-10'}]},today=date(2026,11,25),message=prompt)
    assert plan.status=='ready'
    assert plan.tasks[0].month=='2026-10'


def test_planner_rejects_invented_skill_month():
    plan=validate_plan({'tasks':[{'type':'skill_monthly_finance_review','month':'2026-09'}]},today=date(2026,11,25),message='帮我做2026年10月财务体检')
    assert plan.status=='needs_clarification'


def test_planner_rejects_future_skill_month():
    plan=validate_plan({'tasks':[{'type':'skill_monthly_finance_review','month':'2027-10'}]},today=date(2026,11,25),message='做2027年10月财务体检')
    assert plan.status=='needs_clarification'


def test_skill_not_a_bank_write_escalation():
    with pytest.raises(PlannerError):
        validate_plan({'tasks':[{'type':'skill_account_snapshot','amount':'200.00'}]},today=date(2026,11,25),message='账户概览，给李四转200元')



def test_skill_rejects_month_from_history_only():
    plan = validate_plan(
        {
            "tasks": [
                {
                    "type": "skill_monthly_finance_review",
                    "month": "2026-10",
                }
            ]
        },
        today=date(2026, 11, 25),
        message="帮我做10月财务体检",
        contextual_month="2026-10",
    )

    assert plan.status == "needs_clarification"


def test_skill_requires_month():
    plan = validate_plan(
        {
            "tasks": [
                {
                    "type": "skill_monthly_finance_review"
                }
            ]
        },
        today=date(2026, 11, 25),
        message="帮我做财务体检",
    )

    assert plan.status == "needs_clarification"
