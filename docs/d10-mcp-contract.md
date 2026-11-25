# D10 MCP Read-Only Contract

Implementation: official Python MCP SDK v2, **stdio** transport, one isolated subprocess per tool call.
No additional network listener. `BANKPILOT_MCP_READ_MODE=on` explicitly activates it.

| Agent Task | MCP Tool | Arguments | Java / RAG source |
| --- | --- | --- | --- |
| get_balance | bank_get_balance | {} | GET /api/demo/balance |
| get_transactions | bank_get_transactions | {} | GET /api/demo/transactions |
| get_payees | bank_get_payees | {} | GET /api/demo/payees |
| list_subscriptions | bank_list_subscriptions | {} | GET /api/demo/subscriptions |
| monthly_analytics | bank_monthly_analytics | month: YYYY-MM | GET /api/demo/analytics/monthly |
| annual_analytics | bank_annual_analytics | year: YYYY | GET /api/demo/analytics/annual |
| transaction_anomalies | bank_transaction_anomalies | month: YYYY-MM | GET /api/demo/analytics/anomalies |
| knowledge_search | public_knowledge_search | query: str | D9 public RAG |

**Strict exclusions:** no transfer_prepare, authorize, execute, cancel, OTP, schedule, AA write, password, private database query, arbitrary endpoint or SQL execution tools.

Security: FastAPI obtains bearer from `Runtime.Context` and sends it via a child process environment only. It is never exposed in MCP tool schemas or planner output. Java verifies the original user bearer and account ownership. The stdio process must run locally under a trusted OS user. Do not expose this server as unauthenticated Streamable HTTP or allow arbitrary MCP hosts to launch it with bank tokens. Production requires a stronger per-request identity channel (OAuth/OBO/managed identity), process isolation and lifecycle management.

No automatic fallback to direct tools if MCP returns an error. Use `BANKPILOT_MCP_READ_MODE=off` *before startup* to run the old direct read path when needed for regression.

MCP errors and Trace output must never contain raw tokens, account details or OTP. MCP protocol errors and bank read failures are not permission grants.

D10 operational limits: per-call stdio startup overhead, RAG model reloading overhead, Windows environment/process constraints, one Uvicorn worker. Not a production-ready high-QPS bank integration.
