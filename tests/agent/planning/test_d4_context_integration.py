from datetime import date
from uuid import uuid4

from app.context.models import PlannerContext
from app.graph.task_planner import (
    build_planner_messages,
    contextual_month_from_history,
    validate_plan,
)


def make_context():
    return PlannerContext(
        conversationId=str(uuid4()),
        current_message="那10月呢？",
        recent_messages=[
            {
                "role": "USER",
                "content": "分析2026年9月收支",
            },
            {
                "role": "ASSISTANT",
                "content": "已经完成2026年9月收支分析。",
            },
        ],
    )


def test_planner_messages_include_history_before_current_message():
    context = make_context()

    messages = build_planner_messages(
        "你是银行任务规划器。",
        "那10月呢？",
        context,
    )

    assert [item["role"] for item in messages] == [
        "system", "user", "assistant", "user"
    ]
    assert messages[-1]["content"] == "那10月呢？"
    assert messages[1]["content"] == "分析2026年9月收支"


def test_contextual_month_inherits_year_but_not_target_month():
    context = make_context()

    assert contextual_month_from_history(
        "那10月呢？",
        context,
        date(2026, 11, 19),
    ) == "2026-10"


def test_monthly_plan_accepts_validated_contextual_month():
    plan = validate_plan(
        {"tasks": [{"type": "monthly_analytics", "month": "2026-10"}]},
        today=date(2026, 11, 19),
        message="那10月呢？",
        contextual_month="2026-10",
    )

    assert plan.status == "ready"
    assert plan.tasks[0].month == "2026-10"


def test_monthly_plan_without_context_still_requires_clarification():
    plan = validate_plan(
        {"tasks": [{"type": "monthly_analytics", "month": "2026-10"}]},
        today=date(2026, 11, 19),
        message="那10月呢？",
    )

    assert plan.status == "needs_clarification"


def test_ambiguous_month_reference_does_not_inherit_year():
    context = PlannerContext(
        conversationId=str(uuid4()),
        current_message="那10月呢？",
        recent_messages=[
            {
                "role": "USER",
                "content": "请比较2025年9月和2026年9月",
            },
        ],
    )

    assert contextual_month_from_history(
        "那10月呢？",
        context,
        date(2026, 11, 19),
    ) is None
