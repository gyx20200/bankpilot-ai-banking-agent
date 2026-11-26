"""D12 skill quality gate: deterministic report checks and privacy-safe audit.

Use in the existing D11 read-only graph. Never log bearer, model messages,
raw bank responses, user identifiers, or exception strings.
"""
from __future__ import annotations

import json
import logging
import time
from uuid import uuid4

from app.skills.catalog import SKILLS
from app.skills.runtime import run_skill, summarize

LOG = logging.getLogger("bankpilot.d12.skill")


class SkillReportContractError(ValueError):
    """A skill result violates the trusted server-side report contract."""


def validate_skill_report(skill_id: str, report: object) -> dict:
    """Validate only an authenticated D11 Skill report; no new bank access."""
    spec = SKILLS.get(skill_id)
    if spec is None:
        raise SkillReportContractError("unregistered skill")
    if not isinstance(report, dict):
        raise SkillReportContractError("report must be object")
    if (report.get("skillId") != skill_id or
        report.get("status") != "COMPLETED" or
        report.get("readOnly") is not True or
        report.get("dataOrigin") != "JAVA_MYSQL_VIA_MCP"):
        raise SkillReportContractError("report provenance/status mismatch")

    steps = report.get("steps")
    results = report.get("results")
    if not isinstance(steps, list) or not isinstance(results, dict):
        raise SkillReportContractError("missing structured results")
    if [s.get("taskType") if isinstance(s, dict) else None for s in steps] != list(spec.steps):
        raise SkillReportContractError("step order mismatch")
    if any(s.get("status") != "SUCCESS" or not isinstance(s.get("mcpTool"), str)
           or not s["mcpTool"].startswith(("bank_", "public_")) for s in steps):
        raise SkillReportContractError("unverified MCP step")
    if set(results) != set(spec.steps):
        raise SkillReportContractError("missing or unexpected bank result")

    # Recompute summary from verified structured results, not from model text.
    try:
        expected = summarize(skill_id, results)
    except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
        raise SkillReportContractError("invalid structured bank report") from exc
    if report.get("summary") != expected:
        raise SkillReportContractError("summary differs from bank results")
    return report


def _event(skill_id: str, status: str, elapsed_ms: int, code: str, event_id: str):
    # Allowlisted metadata only. Never pass request/response data to this function.
    payload = {
        "event": "bankpilot_skill_d12",
        "eventId": event_id,
        "skillId": skill_id if skill_id in SKILLS else "UNKNOWN",
        "status": status,
        "elapsedMs": elapsed_ms,
        "errorCode": code,
    }
    LOG.info("%s", json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


async def execute_checked_skill(skill_id: str, params: dict, bearer: str) -> dict:
    """Drop-in replacement for run_skill in dynamic_read_workflow.execute_read."""
    start = time.perf_counter()
    event_id = uuid4().hex[:16]
    try:
        result = await run_skill(skill_id, params, bearer)
        validate_skill_report(skill_id, result)
    except Exception as exc:
        # Exception text may contain account info: only record a class-based code.
        code = "CONTRACT_INVALID" if isinstance(exc, SkillReportContractError) else "SKILL_FAILED"
        _event(skill_id, "FAILED", int((time.perf_counter()-start)*1000), code, event_id)
        raise  # NEVER hide failures or silently fall back to direct bank calls.
    _event(skill_id, "COMPLETED", int((time.perf_counter()-start)*1000), "NONE", event_id)
    return result
