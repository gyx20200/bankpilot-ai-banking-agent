"""LLM time normalization contract, using a fake DeepSeek HTTP response."""
import asyncio
import json
import re
from datetime import datetime

import httpx

from app.graph.schedule_time import CN
from app.graph import task_planner as planner


def test_submit_task_plan_schema_includes_both_time_fields():
    variants = planner.PLANNER_TOOL['function']['parameters']['properties']['tasks']['items']['anyOf']
    schedule = next(v for v in variants if v['properties']['type']['enum'] == ['schedule_transfer'])
    assert 'time_expression' in schedule['properties']
    assert 'execute_at' in schedule['properties']
    assert 'time_expression' not in next(v for v in variants if v['properties']['type']['enum'] == ['transfer_prepare'])['properties']


def test_live_planner_contract_uses_precise_current_time_and_llm_iso(monkeypatch):
    requests = []
    real_async_client = httpx.AsyncClient
    user_text = '2026年11月30日21.37给李四转500元，备注生活费'
    llm_plan = {
        'tasks': [{'type': 'schedule_transfer', 'payee_name': '李四', 'amount': '500',
                   'remark': '生活费', 'time_expression': '2026年11月30日21.37',
                   'execute_at': '2026-11-30T21:37:00+08:00'}],
        'unhandled_requests': [],
    }

    def handler(request):
        sent = json.loads(request.content)
        requests.append(sent)
        response = {'choices': [{'message': {'tool_calls': [{'function': {
            'name': 'submit_task_plan', 'arguments': json.dumps(llm_plan, ensure_ascii=False)
        }}]}}]}
        return httpx.Response(200, json=response)

    def fake_async_client(*args, **kwargs):
        kwargs['transport'] = httpx.MockTransport(handler)
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(planner.llm_router, 'enabled', lambda: True)
    monkeypatch.setattr(planner.llm_router, 'configured', lambda: True)
    monkeypatch.setattr(planner.llm_router, '_endpoint', lambda: 'https://llm.invalid/chat')
    monkeypatch.setenv('MODEL_NAME', 'deepseek-chat')
    monkeypatch.setenv('MODEL_API_KEY', 'test-secret')
    monkeypatch.setattr(planner.httpx, 'AsyncClient', fake_async_client)

    result = asyncio.run(planner.plan_tasks(user_text))
    assert result.status == 'ready'
    assert result.tasks[0].execute_at == '2026-11-30T21:37:00+08:00'
    assert result.tasks[0].time_expression == '2026年11月30日21.37'
    assert result.tasks[0].remark == '生活费'
    assert len(requests) == 1
    system = requests[0]['messages'][0]['content']
    assert re.search(r'当前准确北京时间：\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+08:00', system)
    assert 'time_expression' in system
    assert 'execute_at' in system
