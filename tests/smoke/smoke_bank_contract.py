"""Day 5 smoke test for a disposable LOCAL BankPilot demo database.

Uses the real Java service. Optional --agent uses Python FastAPI / DeepSeek router.
Never performs authorize or execute; tests only bank READ tools and prepare_transfer.
"""
import argparse
from datetime import datetime
from decimal import Decimal
import json
import os
import sys
import urllib.error
import urllib.request
import uuid


def http(method, url, *, token=None, data=None, trace_id=None, timeout=15):
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    if trace_id:
        headers["X-Agent-Request-Id"] = trace_id
    body = json.dumps(data, ensure_ascii=False).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, method=method, headers=headers, data=body)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            raw = res.read().decode("utf-8")
            return res.status, json.loads(raw) if raw else None, dict(res.headers)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = {"detail": "Non-JSON error response"}
        return exc.code, payload, dict(exc.headers)


def check(label, expression):
    if not expression:
        raise AssertionError("FAILED: " + label)
    print("PASS:", label)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--java", default="http://127.0.0.1:8080")
    parser.add_argument("--agent", action="store_true", help="also run end-to-end FastAPI Agent probes")
    parser.add_argument("--agent-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    base = args.java.rstrip("/")
    password = os.getenv("DEMO_LOGIN_PASSWORD")
    if not password:
        raise SystemExit("Set DEMO_LOGIN_PASSWORD in this terminal (test-only; do not print/share it).")

    status, health, _ = http("GET", base + "/api/demo/health")
    check("Java health", status == 200 and health.get("status") == "ok")

    status, _, _ = http("GET", base + "/api/demo/balance")
    check("Unauthenticated balance forbidden", status == 401)

    status, login, _ = http("POST", base + "/api/auth/demo-login",
                            data={"username": "demo", "password": password})
    check("Java demo login succeeds", status == 200 and isinstance(login.get("token"), str))
    token = login["token"]
    trace_id = "day5-" + uuid.uuid4().hex

    results = {}
    paths = {
        "get_balance": "/api/demo/balance",
        "get_transactions": "/api/demo/transactions",
        "get_payees": "/api/demo/payees",
        "get_subscriptions": "/api/demo/subscriptions",
    }
    for name, path in paths.items():
        status, data, headers = http("GET", base + path, token=token, trace_id=trace_id)
        check(name + " 200 + trace header", status == 200 and headers.get("X-Agent-Request-Id") == trace_id)
        results[name] = data
    check("Balance from DB", results["get_balance"].get("source") == "mysql")
    check("Transactions array", isinstance(results["get_transactions"], list))
    check("Payees array with masked account", bool(results["get_payees"]) and
          "****" in results["get_payees"][0].get("payeeAccountMasked", ""))
    check("Subscriptions array", isinstance(results["get_subscriptions"], list))

    status, report, _ = http("GET", base + "/api/demo/analytics/monthly?month=2026-10",
                             token=token, trace_id=trace_id)
    check("October SQL monthly analytics", status == 200 and report.get("source") == "mysql")
    check("Monthly report has deterministic totals", all(k in report for k in
          ("totalIncome", "totalExpense", "netCashFlow", "categories")))
    status, _, _ = http("GET", base + "/api/demo/analytics/monthly?month=2026-10%27%20OR%201%3D1",
                        token=token)
    check("Invalid month rejected, not interpolated into SQL", status == 400)

    balance_before = Decimal(str(results["get_balance"]["balance"]))
    req_id = "day5-smoke-" + uuid.uuid4().hex
    payee_id = int(results["get_payees"][0]["id"])
    payload = {"payeeId": payee_id, "amount": "1.00", "requestId": req_id, "remark": "Day5 smoke"}
    status, order, _ = http("POST", base + "/api/transfers/prepare", token=token, data=payload,
                            trace_id=trace_id)
    check("prepare_transfer only creates pending order", status in (200, 201) and
          order.get("status") == "PENDING_APPROVAL" and order.get("riskLevel") in ("RED", "YELLOW"))
    status2, duplicate, _ = http("POST", base + "/api/transfers/prepare", token=token,
                                  data=payload, trace_id=trace_id)
    check("Same requestId yields same order", status2 in (200, 201) and
          duplicate["orderId"] == order["orderId"])
    mismatch = dict(payload, amount="2.00")
    code, _, _ = http("POST", base + "/api/transfers/prepare", token=token, data=mismatch)
    check("Different parameters with same requestId rejected", code == 409)
    status, new_balance, _ = http("GET", base + "/api/demo/balance", token=token)
    check("Transfer preparation does not debit", status == 200 and
          Decimal(str(new_balance["balance"])) == balance_before)

    if args.agent:
        agent = args.agent_url.rstrip("/")
        status, mode, _ = http("GET", agent + "/api/agent/health")
        check("Agent service is healthy", status == 200 and mode.get("status") == "ok")
        print("Agent mode (not proof of a real DeepSeek call):", mode.get("mode", "unspecified"))
        tests = [("我的钱包还剩多少钱？", "balance", "get_balance"),
                 ("我最近消费了什么？", "transactions", "get_transactions"),
                 ("我保存了哪些收款人？", "payees", "get_payees"),
                 ("有哪些自动扣费？", "subscriptions", "get_subscriptions")]
        for text, expected, direct in tests:
            status, reply, _ = http("POST", agent + "/api/agent/chat", token=token,
                                    data={"message": text, "requestId": "d5-" + uuid.uuid4().hex},timeout=35)
            check("Agent routes: " + text, status == 200 and reply.get("intent") == expected and
                  reply.get("source") != "mock-api" and reply.get("data") is not None)
            if expected == "balance":
                check("Agent returned bank balance, not invented", Decimal(str(reply["data"]["balance"])) == balance_before)
        status, transfer, _ = http("POST", agent + "/api/agent/chat", token=token,
            data={"message": "帮我给李四打两百块", "requestId": "d5-" + uuid.uuid4().hex}, timeout=35)
        check("DeepSeek-style Chinese natural language creates pending order", status == 200 and
              transfer.get("intent") == "transfer" and transfer.get("action") == "prepared" and
              transfer.get("data", {}).get("status") == "PENDING_APPROVAL")
        status, after_agent, _ = http("GET", base + "/api/demo/balance", token=token)
        check("Agent prepare also does not debit", status == 200 and
              Decimal(str(after_agent["balance"])) == balance_before)
        print("NOTE: confirm DeepSeek API request + returned tool_calls in Python server logs (mask keys/prompts).")

    print("\nALL DAY5 API CONTRACT CHECKS PASSED (actual MySQL & app logs still require manual audit review).")


if __name__ == "__main__":
    try:
        main()
    except (AssertionError, urllib.error.URLError, KeyError, TypeError, ValueError) as exc:
        print("DAY5 CHECK FAILED:", exc, file=sys.stderr)
        sys.exit(1)
