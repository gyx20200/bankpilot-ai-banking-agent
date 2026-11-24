"""D9 conservative evidence gate.

This is a deterministic *numeric and unsafe-claim* guard, not proof of complete
semantic faithfulness. Human evaluation remains mandatory.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

NUMBERS = re.compile(r"(?<![A-Za-z0-9])\d+(?:\.\d+)?(?![A-Za-z0-9])")
ABSOLUTE_BANKPILOT_CLAIM = re.compile(
    r"BankPilot.{0,24}(?:已经投保|已参加存款保险|保证收益|保本保息|监管批准|具有银行牌照)",
    re.I,
)
URL = re.compile(r"https?://|www\.", re.I)


@dataclass(frozen=True)
class EvidenceDecision:
    passed: bool
    reason_code: str
    unsupported_numbers: tuple[str, ...] = ()


def verify_numeric_evidence(answer: str, snippets: list[str]) -> EvidenceDecision:
    if not isinstance(answer, str) or not answer.strip():
        return EvidenceDecision(False, "EMPTY_ANSWER")
    if not snippets or any(not isinstance(x, str) for x in snippets):
        return EvidenceDecision(False, "NO_EVIDENCE")
    if ABSOLUTE_BANKPILOT_CLAIM.search(answer):
        return EvidenceDecision(False, "UNVERIFIED_BANKPILOT_CLAIM")
    if URL.search(answer):
        # URLs must be appended by the server from approved metadata, not the LLM.
        return EvidenceDecision(False, "MODEL_GENERATED_URL")
    evidence_numbers = set(NUMBERS.findall("\n".join(snippets)))
    answer_numbers = set(NUMBERS.findall(answer))
    missing = tuple(sorted(answer_numbers - evidence_numbers))
    if missing:
        return EvidenceDecision(False, "UNSUPPORTED_NUMERIC_FACT", missing)
    return EvidenceDecision(True, "NUMERIC_CHECK_PASSED")
