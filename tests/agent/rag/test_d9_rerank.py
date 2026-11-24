from unittest.mock import Mock
import pytest
from app.rag import rerank


def _hits():
    return [{"sourceId": "A", "snippet": "甲条"},
            {"sourceId": "B", "snippet": "乙条"},
            {"sourceId": "C", "snippet": "丙条"}]


def test_rerank_orders_and_preserves_provenance(monkeypatch):
    model = Mock()
    model.predict.return_value = [0.1, 1.9, -0.4]
    monkeypatch.setattr(rerank, "_model", lambda: model)
    result = rerank.rerank_hits("甲乙条例如何适用？", _hits(), top_n=2)
    assert [h["sourceId"] for h in result] == ["B", "A"]
    assert "rerankScore" in result[0]
    assert result[0]["snippet"] == "乙条"


def test_invalid_scores_fail_closed(monkeypatch):
    model = Mock()
    model.predict.return_value = [float("nan"), 0.0, 0.2]
    monkeypatch.setattr(rerank, "_model", lambda: model)
    with pytest.raises(rerank.RerankUnavailable):
        rerank.rerank_hits("查询官方条文", _hits())


def test_invalid_mode_fails(monkeypatch):
    monkeypatch.setenv("BANKPILOT_RERANK_MODE", "maybe")
    with pytest.raises(rerank.RerankUnavailable):
        rerank.rerank_mode()
