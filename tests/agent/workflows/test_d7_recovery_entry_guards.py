"""D7: recovery-entry failure invariants. No HTTP, MySQL, or actual bank writes.

Run from the repository root: python -m pytest -q tests/agent/workflows/test_d7_recovery_entry_guards.py
"""
import asyncio
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app import d6_recovery_api as recovery


def context(*, requires_otp=False):
    return {
        "checkpointId": str(uuid4()),
        "orderId": "41",
        "accountMasked": "****17A4",
        "amount": "10.00",
        "requiresOtp": requires_otp,
    }


def request(safe, **updates):
    fields = dict(
        approved=True,
        expectedCheckpointId=safe["checkpointId"],
        expectedOrderId=safe["orderId"],
        expectedAccountMasked=safe["accountMasked"],
        expectedAmount=safe["amount"],
    )
    fields.update(updates)
    return recovery.ResumeRequest(**fields)


def protect(monkeypatch, safe):
    events = []

    async def preflight(*args):
        return object(), safe

    async def forbidden_claim(*args, **kwargs):
        events.append("CLAIM")
        raise AssertionError("claim must not be called")

    async def forbidden_graph(*args, **kwargs):
        events.append("GRAPH")
        raise AssertionError("graph must not be called")

    monkeypatch.setattr(recovery, "_preflight", preflight)
    monkeypatch.setattr(recovery, "create_claim", forbidden_claim)
    monkeypatch.setattr(recovery.wf, "_invoke_graph", forbidden_graph)
    monkeypatch.setattr(recovery.wf, "_locks", {})
    return events


@pytest.mark.parametrize("changed", [
    {"expectedCheckpointId": "00000000-0000-0000-0000-000000000000"},
    {"expectedOrderId": "9999"},
    {"expectedAccountMasked": "****0000"},
    {"expectedAmount": "11.00"},
])
def test_stale_or_tampered_confirmation_never_claims_or_runs(monkeypatch, changed):
    safe = context()
    events = protect(monkeypatch, safe)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(recovery.resume_recovered_transfer(
            uuid4(), request(safe, **changed), "Bearer test-token"))
    assert exc.value.status_code == 409
    assert events == []


def test_red_risk_without_fresh_otp_cannot_claim(monkeypatch):
    safe = context(requires_otp=True)
    events = protect(monkeypatch, safe)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(recovery.resume_recovered_transfer(
            uuid4(), request(safe), "Bearer test-token"))
    assert exc.value.status_code == 422
    assert events == []


def test_rejection_cannot_include_otp(monkeypatch):
    safe = context()
    events = protect(monkeypatch, safe)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(recovery.resume_recovered_transfer(
            uuid4(), request(safe, approved=False, otpCode="123456"), "Bearer test-token"))
    assert exc.value.status_code == 422
    assert events == []


@pytest.mark.parametrize("failure_status", [409, 503])
def test_claim_failure_never_executes_graph(monkeypatch, failure_status):
    safe = context()
    calls = []

    async def preflight(*args):
        return object(), safe

    async def unavailable_claim(*args, **kwargs):
        calls.append("CLAIM_FAILED")
        raise HTTPException(failure_status, "claim failed or result uncertain")

    async def forbidden_graph(*args, **kwargs):
        calls.append("GRAPH")
        raise AssertionError("graph must not be called")

    monkeypatch.setattr(recovery, "_preflight", preflight)
    monkeypatch.setattr(recovery, "create_claim", unavailable_claim)
    monkeypatch.setattr(recovery.wf, "_invoke_graph", forbidden_graph)
    monkeypatch.setattr(recovery.wf, "_locks", {})

    with pytest.raises(HTTPException) as exc:
        asyncio.run(recovery.resume_recovered_transfer(
            uuid4(), request(safe), "Bearer test-token"))
    assert exc.value.status_code == failure_status
    assert calls == ["CLAIM_FAILED"]


def test_after_claim_graph_error_marks_not_confirmed_without_retry(monkeypatch):
    safe = context()
    calls = []

    async def preflight(*args):
        return object(), safe

    async def success_claim(*args, **kwargs):
        calls.append("CLAIM")
        return {"status": "CLAIMED"}

    async def graph_crashes(*args, **kwargs):
        calls.append("GRAPH")
        raise RuntimeError("simulated network error after durable claim")

    async def finalize(thread, status, bearer):
        calls.append(("FINALIZE", status))
        return {"status": status}

    monkeypatch.setattr(recovery, "_preflight", preflight)
    monkeypatch.setattr(recovery, "create_claim", success_claim)
    monkeypatch.setattr(recovery, "finalize_claim", finalize)
    monkeypatch.setattr(recovery.wf, "_invoke_graph", graph_crashes)
    monkeypatch.setattr(recovery.wf, "_locks", {})

    with pytest.raises(HTTPException) as exc:
        asyncio.run(recovery.resume_recovered_transfer(
            uuid4(), request(safe), "Bearer test-token"))
    assert exc.value.status_code == 503
    assert calls == ["CLAIM", "GRAPH", ("FINALIZE", "NOT_CONFIRMED")]
