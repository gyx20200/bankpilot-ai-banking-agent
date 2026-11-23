"""Run after updating existing Task Planner/registry/graph per D8 guide."""
from datetime import date

from app.graph.task_planner import validate_plan
from app.graph.task_registry import TASK_REGISTRY
from app.graph.dynamic_read_workflow import READ_TASK_TYPES


def test_public_knowledge_is_registered_as_low_risk_read():
    spec = TASK_REGISTRY['knowledge_search']
    assert spec.risk_level == 'LOW'
    assert spec.required_params == ('query',)
    assert 'knowledge_search' in READ_TASK_TYPES


def test_public_question_accepted():
    q = '存款保险最高偿付限额是多少？'
    plan = validate_plan({'tasks': [{'type': 'knowledge_search', 'query': q}]},
                         today=date(2026, 11, 23), message=q)
    assert plan.status == 'ready'
    assert plan.tasks[0].query == q


def test_hallucinated_query_blocked():
    plan = validate_plan({'tasks': [{'type': 'knowledge_search', 'query': '个人信贷利率是多少？'}]},
                         today=date(2026, 11, 23), message='存款保险额度是多少？')
    assert plan.status == 'needs_clarification'


def test_public_answer_cannot_query_private_balance():
    plan = validate_plan({'tasks': [{'type': 'knowledge_search', 'query': '查询我的余额'}]},
                         today=date(2026, 11, 23), message='查询我的余额')
    assert plan.status == 'needs_clarification'
