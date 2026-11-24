"""D8 source integrity + query safety tests; no LLM, Chroma or network required."""
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'knowledge'))
sys.path.insert(0, str(ROOT / 'agent-service'))

from validate_sources import validate_sources, SourceValidationError
from app.rag.policy import validate_public_query, ensure_verbatim_query, KnowledgeRejected


def test_official_corpus_checked_and_separated():
    sources = validate_sources(ROOT / 'knowledge' / 'approved_sources.json')
    assert len(sources) >= 3
    assert all(source['scope'] == 'PUBLIC_OFFICIAL' for source in sources)
    assert all(source['url'].startswith('https://') for source in sources)


def test_reject_unknown_sources(tmp_path):
    sources = json.loads((ROOT / 'knowledge' / 'approved_sources.json').read_text(encoding='utf-8'))
    sources[0]['url'] = 'https://malicious.bankpilot.test/rules'
    p = tmp_path / 'sources.json'
    p.write_text(json.dumps(sources, ensure_ascii=False), encoding='utf-8')
    with pytest.raises(SourceValidationError):
        validate_sources(p)


@pytest.mark.parametrize('question', [
    '查询我的余额', '查一下我的交易流水', '帮我给李四转账10元',
    '我的信用报告在哪里', '帮我取消订阅',
])
def test_private_business_not_public_knowledge(question):
    with pytest.raises(KnowledgeRejected):
        validate_public_query(question)


def test_valid_public_question_and_verbatim_clause():
    q = '存款保险最高偿付限额是多少？'
    assert validate_public_query(q) == q
    ensure_verbatim_query(q, q)
    ensure_verbatim_query(q, '查询余额，并且' + q)


def test_reject_model_hallucinated_question():
    with pytest.raises(KnowledgeRejected):
        ensure_verbatim_query('个人账户余额有多少？', '存款保险最高偿付限额是多少？')
