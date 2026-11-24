import json
import pytest
from app.rag.trace import span


def test_trace_contains_no_prompt_or_secret(monkeypatch, tmp_path):
    path = tmp_path / "trace.jsonl"
    monkeypatch.setenv("BANKPILOT_RAG_TRACE_ENABLED", "true")
    monkeypatch.setenv("BANKPILOT_RAG_TRACE_PATH", str(path))
    with span("test-trace", "retrieval", retrievedCount=5,
              question="我的银行密码是123456", bearer="Bearer secret"):
        pass
    content = path.read_text(encoding="utf-8")
    event = json.loads(content)
    assert event["traceId"] == "test-trace"
    assert event["retrievedCount"] == 5
    assert event["status"] == "OK"
    assert "Bearer" not in content and "密码" not in content and "123456" not in content


def test_trace_error_does_not_log_exception_message(monkeypatch, tmp_path):
    path = tmp_path / "trace.jsonl"
    monkeypatch.setenv("BANKPILOT_RAG_TRACE_ENABLED", "true")
    monkeypatch.setenv("BANKPILOT_RAG_TRACE_PATH", str(path))
    with pytest.raises(RuntimeError):
        with span("t", "generation"):
            raise RuntimeError("secret token 123456")
    event = json.loads(path.read_text(encoding="utf-8"))
    assert event["status"] == "ERROR"
    assert event["errorType"] == "RuntimeError"
    assert "123456" not in path.read_text(encoding="utf-8")
