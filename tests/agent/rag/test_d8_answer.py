"""Answer guard tests run without loading embedding models or network."""
import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'agent-service'))
from app.rag.answer import answer_public_question


def test_no_evidence_returns_explicit_unknown():
    with patch('app.rag.answer.search', return_value=[]):
        result = asyncio.run(answer_public_question('存款保险是不是保障所有投资产品？'))
    assert result['grounded'] is False
    assert result['citations'] == []
    assert result['dataOrigin'] == 'PUBLIC_OFFICIAL'
    assert '无法' in result['answer']
