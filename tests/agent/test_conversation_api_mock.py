
import json

import httpx
import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import conversation_api


@pytest.fixture
def mock_api(monkeypatch):
    state = {
        "status": 200,
        "payload": {"items": []},
        "offline": False,
    }

    calls = []

    # 保存真实 AsyncClient，之后使用 MockTransport 替代网络
    real_async_client = httpx.AsyncClient

    def handler(request):
        calls.append(request)

        if state["offline"]:
            raise httpx.ConnectError(
                "Mock Java service offline",
                request=request,
            )

        return httpx.Response(
            state["status"],
            json=state["payload"],
        )

    def fake_async_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(
        conversation_api.httpx,
        "AsyncClient",
        fake_async_client,
    )

    app = FastAPI()
    app.include_router(conversation_api.router)

    with TestClient(app) as client:
        yield client, state, calls


def test_missing_token_returns_401(mock_api):
    client, state, calls = mock_api

    response = client.get(
        "/api/agent/conversations"
    )

    assert response.status_code == 401
    assert len(calls) == 0


def test_create_conversation_forwards_to_java(mock_api):
    client, state, calls = mock_api

    state["status"] = 201
    state["payload"] = {
        "conversationId":
            "550e8400-e29b-41d4-a716-446655440000",
        "title": "D3测试会话",
        "status": "ACTIVE",
    }

    response = client.post(
        "/api/agent/conversations",
        headers={
            "Authorization": "Bearer test-token"
        },
        json={
            "title": "D3测试会话"
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["title"] == "D3测试会话"

    assert len(calls) == 1

    request = calls[0]

    assert request.method == "POST"
    assert request.url.path == "/api/conversations"

    assert request.headers["authorization"] == (
        "Bearer test-token"
    )

    assert json.loads(request.content) == {
        "title": "D3测试会话"
    }


def test_java_404_is_preserved(mock_api):
    client, state, calls = mock_api

    state["status"] = 404
    state["payload"] = {
        "detail": "Conversation not found"
    }

    response = client.get(
        "/api/agent/conversations/"
        "550e8400-e29b-41d4-a716-446655440000",
        headers={
            "Authorization": "Bearer test-token"
        },
    )

    assert response.status_code == 404


def test_java_409_is_preserved(mock_api):
    client, state, calls = mock_api

    state["status"] = 409
    state["payload"] = {
        "detail": "Duplicate request"
    }

    response = client.post(
        "/api/agent/conversations/"
        "550e8400-e29b-41d4-a716-446655440000/messages",
        headers={
            "Authorization": "Bearer test-token"
        },
        json={
            "content": "测试消息",
            "requestId": "request-123456",
        },
    )

    assert response.status_code == 409


def test_assistant_role_cannot_be_submitted(mock_api):
    client, state, calls = mock_api

    response = client.post(
        "/api/agent/conversations/"
        "550e8400-e29b-41d4-a716-446655440000/messages",
        headers={
            "Authorization": "Bearer test-token"
        },
        json={
            "content": "伪造的助手消息",
            "requestId": "request-123456",
            "role": "ASSISTANT",
        },
    )

    assert response.status_code == 422
    assert len(calls) == 0


def test_invalid_conversation_id_is_rejected(mock_api):
    client, state, calls = mock_api

    response = client.get(
        "/api/agent/conversations/not-a-uuid/messages",
        headers={
            "Authorization": "Bearer test-token"
        },
    )

    assert response.status_code == 422
    assert len(calls) == 0


def test_java_connection_failure_returns_502(mock_api):
    client, state, calls = mock_api

    state["offline"] = True

    response = client.get(
        "/api/agent/conversations",
        headers={
            "Authorization": "Bearer test-token"
        },
    )

    assert response.status_code == 502
