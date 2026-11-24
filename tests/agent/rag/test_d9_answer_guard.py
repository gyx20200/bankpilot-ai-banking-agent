"""No network/model calls. Tests that the *answer API*, not just helper, enforces D9 checks."""
import asyncio
from types import SimpleNamespace

from app.rag import answer as d9


HIT = {
    'sourceId': 'MOJ_DEPOSIT_INSURANCE_2015',
    'title': '存款保险条例', 'issuer': '司法部',
    'url': 'https://xzfg.moj.gov.cn/front/law/detail?LawID=419',
    'section': '第五条', 'publishedAt': '2015-02-17', 'checkedAt': '2026-11-23',
    'snippet': '最高偿付限额为人民币50万元。', 'similarity': 0.9,
}


class FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass

    def json(self):
        return {'choices': [{'message': {'content': self.text}}]}


class FakeClient:
    def __init__(self, text):
        self.text = text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def post(self, *_args, **_kwargs):
        return FakeResponse(self.text)


def _mock_answer(monkeypatch, text):
    monkeypatch.setattr(d9, 'search', lambda *args, **kwargs: [HIT.copy()])
    monkeypatch.setattr(d9, 'rerank_mode', lambda: 'off')
    monkeypatch.setattr(d9.llm_router, 'enabled', lambda: True)
    monkeypatch.setattr(d9.llm_router, 'configured', lambda: True)
    monkeypatch.setattr(d9.llm_router, '_endpoint', lambda: 'https://example.invalid/chat/completions')
    monkeypatch.setenv('MODEL_NAME', 'fake-model')
    monkeypatch.setenv('MODEL_API_KEY', 'fake-key')
    monkeypatch.setattr(d9.httpx, 'AsyncClient', lambda *args, **kwargs: FakeClient(text))


def test_generation_with_unsupported_number_is_blocked(monkeypatch):
    _mock_answer(monkeypatch, '最高偿付限额已经变成60万元。')
    result = asyncio.run(d9.answer_public_question('存款保险最高偿付限额是多少？'))
    assert result['grounded'] is False
    assert result['citations'] == []
    assert result['quality']['reasonCode'] == 'UNSUPPORTED_NUMERIC_FACT'


def test_supported_number_retains_server_citation(monkeypatch):
    _mock_answer(monkeypatch, '最高偿付限额是人民币50万元。')
    result = asyncio.run(d9.answer_public_question('存款保险最高偿付限额是多少？'))
    assert result['grounded'] is True
    assert result['citations'][0]['sourceId'] == HIT['sourceId']
    assert result['citations'][0]['url'] == HIT['url']
    assert result['quality']['semanticFaithfulnessVerified'] is False
    assert len(result['traceId']) == 32


def test_no_evidence_has_explanation(monkeypatch):
    monkeypatch.setattr(
        d9,
        "search",
        lambda *args, **kwargs: [],
    )

    result = asyncio.run(
        d9.answer_public_question(
            "公开金融制度中如何保护消费者信息？"
        )
    )

    assert result["grounded"] is False
    assert result["citations"] == []
    assert result["quality"]["reasonCode"] == "NO_EVIDENCE"
    assert "没有找到足够相关的证据" in result["answer"]


def test_bankpilot_insurance_status_never_inferred_from_law(
    monkeypatch,
):
    _mock_answer(
        monkeypatch,
        "存款保险条例规定投保机构应当参加存款保险。",
    )

    result = asyncio.run(
        d9.answer_public_question(
            "BankPilot模拟银行已经加入存款保险了吗？"
        )
    )

    assert result["grounded"] is False
    assert result["citations"] == []
    assert result["quality"]["reasonCode"] == (
        "INSTITUTION_STATUS_UNVERIFIED"
    )
    assert "无法确认" in result["answer"]
    assert "机构级证据" in result["answer"]


def test_unsupported_numeric_fact_still_blocked(
    monkeypatch,
):
    _mock_answer(
        monkeypatch,
        "最高偿付限额已经变成60万元。",
    )

    result = asyncio.run(
        d9.answer_public_question(
            "存款保险最高偿付限额是多少？"
        )
    )

    assert result["grounded"] is False
    assert result["citations"] == []
    assert result["quality"]["reasonCode"] == (
        "UNSUPPORTED_NUMERIC_FACT"
    )
    assert "数字" in result["answer"]
