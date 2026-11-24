import json
from pathlib import Path
from app.rag.faithfulness import verify_numeric_evidence

ROOT = Path(__file__).resolve().parents[3]


def test_gold_faithfulness_cases():
    cases = json.loads((ROOT / "knowledge" / "eval_d9_cases.json").read_text(encoding="utf-8"))["faithfulnessCases"]
    for case in cases:
        decision = verify_numeric_evidence(case["answer"], case["snippets"])
        assert decision.passed is case["expectedPassed"], (case["id"], decision)


def test_no_evidence_rejects_even_without_numbers():
    assert not verify_numeric_evidence("金融消费者需要谨慎", []).passed


def test_unsupported_number_lists_value():
    check = verify_numeric_evidence("额度提高到60万元。", ["额度为50万元。"])
    assert check.reason_code == "UNSUPPORTED_NUMERIC_FACT"
    assert "60" in check.unsupported_numbers
