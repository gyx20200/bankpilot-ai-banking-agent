"""Checks prompt-date injection without making any paid model API calls."""
import asyncio
import json
from datetime import date

import httpx
from app import llm_router


def test_date_examples_and_cross_year():
    prompt = llm_router.build_system_prompt(date(2026, 10, 28))
    assert '2026-10-28' in prompt
    assert '今年7月' in prompt and '2026-07' in prompt
    assert '2025-07' in prompt
    assert '2026-09' in prompt
    assert '不得猜测年份' in prompt

    january = llm_router.build_system_prompt(date(2027, 1, 2))
    assert '2026-12' in january  # Previous month across calendar years


def test_one_model_call_with_current_date_in_system_message(monkeypatch):
    monkeypatch.setenv('MODEL_MODE', 'compatible')
    monkeypatch.setenv('MODEL_API_KEY', 'fake-test-key')
    monkeypatch.setenv('MODEL_NAME', 'fake-model')
    monkeypatch.setenv('MODEL_BASE_URL', 'https://example.org/v1')
    original_prompt_builder = llm_router.build_system_prompt
    monkeypatch.setattr(llm_router, 'build_system_prompt',
                        lambda: original_prompt_builder(date(2026, 10, 28)))
    captured = []
    original_async_client = httpx.AsyncClient

    def responder(request):
        body = json.loads(request.content)
        captured.append(body)
        return httpx.Response(200, json={
            'choices': [{'message': {'tool_calls': [{
                'id': 'call-1', 'type': 'function',
                'function': {'name': 'get_monthly_analytics',
                             'arguments': '{"month":"2026-07"}'}
            }]}}]
        })

    def fake_client(*args, **kwargs):
        kwargs['transport'] = httpx.MockTransport(responder)
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(llm_router.httpx, 'AsyncClient', fake_client)
    result = asyncio.run(llm_router.choose_tool('分析今年7月收支'))
    assert result.name == 'get_monthly_analytics'
    assert result.arguments == {'month': '2026-07'}
    assert len(captured) == 1
    assert '2026-10-28' in captured[0]['messages'][0]['content']
    assert captured[0]['messages'][1]['content'] == '分析今年7月收支'
    assert 'get_current_date' not in json.dumps(captured[0], ensure_ascii=False)
    assert 'execute_transfer' not in json.dumps(captured[0], ensure_ascii=False)
