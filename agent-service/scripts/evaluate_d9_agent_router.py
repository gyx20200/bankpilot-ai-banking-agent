"""Live model-only Agent routing evaluation; charges API tokens, NO Java calls.

The planner is only asked to output TaskPlan; never invoke LangGraph or bank writes.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent-service"))
from app.graph.task_planner import plan_tasks


async def main() -> None:
    cases = json.loads((ROOT / "knowledge" / "eval_d9_cases.json").read_text(encoding="utf-8"))["routeCases"]
    passed = 0
    results = []
    for row in cases:
        try:
            plan = await plan_tasks(row["message"])
            actual = sorted(t.type for t in plan.tasks) if plan.status == "ready" else []
            expected = sorted(row["expectedTaskTypes"])
            ok = plan.status == "ready" and actual == expected
        except Exception as exc:
            actual, ok = ["ERROR:" + type(exc).__name__], False
        passed += int(ok)
        results.append({"caseId": row["id"], "pass": ok, "actualTaskTypes": actual})
        print("PASS" if ok else "FAIL", row["id"], actual)
    report = {"passed": passed, "total": len(cases), "accuracy": round(passed / len(cases), 4), "cases": results}
    output = ROOT / "agent-service" / "data" / "evaluation" / "d9_agent_routing.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("REPORT", json.dumps({k: report[k] for k in ("passed", "total", "accuracy")}, ensure_ascii=False))
    print("WRITTEN", output)


if __name__ == "__main__":
    asyncio.run(main())
