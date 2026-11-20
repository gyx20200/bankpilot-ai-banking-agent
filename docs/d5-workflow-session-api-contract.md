# BankPilot D5 Java Workflow Session Registry

Baseline: main `46a4d23`. Spring Boot 3.5.7 / Java 21 / MySQL 8.

## Installation

- Add `WorkflowSessionController.java` and `WorkflowSessionService.java`.
- Replace `ConversationService.java` with the included D4-compatible file (only adds `requireWorkflowSource`), or manually merge that one helper if your local file has changed.
- Back up `bankpilot_day7_test`. Run `database/13_workflow_session_persistence.sql` once, only if its column and index have not already been created. Check privileges on `agent_workflow_sessions` (SELECT, INSERT, UPDATE).
- Optional new test: `WorkflowSessionServiceTest.java`. It builds independent H2 tables and uses Spring transaction proxies; it does not require changing the shared H2 schema.

## Authentication

Every route requires a fresh valid user Bearer token and `X-Bankpilot-Agent-Key`, matching `BANKPILOT_AGENT_INTERNAL_KEY` (at least 32 UTF-8 bytes, nonblank). User identity is derived from `AuthenticatedUser.id()`. Never send the internal key to Vue. Use a trusted Java endpoint; do not follow redirects with credentials.

## Routes

| Method | Path | Success |
| --- | --- | --- |
| POST | `/api/workflow-sessions` | 201, SessionView |
| GET | `/api/workflow-sessions/{threadId}` | 200, SessionView |
| GET | `/api/workflow-sessions?conversationId={uuid}&limit=20` | 200, `{"items":[SessionView,...]}` |
| PATCH | `/api/workflow-sessions/{threadId}/status` | 200, SessionView |

Register JSON (only these fields accepted):

```json
{"threadId":"1dbbd0d0-2a66-4db7-a117-1dbf3e2e4444","conversationId":"e1c7118d-3946-45c8-a69e-708bb51728e8","sourceRequestId":"user-12345678","userMessageContent":"查询我的余额"}
```

Thread/conversation IDs are UUIDs, returned in canonical form. Source request ID follows D3 `[A-Za-z0-9_-]{8,64}`. The source must be a stored USER message in the caller's ACTIVE conversation and match the normalized/redacted D3 user content. Registration occurs before Graph invocation. Duplicate source or duplicate thread returns 409, including a retry with the same thread ID. Do not invoke or create a new Graph on a conflict, timeout or any unconfirmed registration. Query the existing session list and match the source request ID instead; do not automatically resume an in-progress or missing-checkpoint session.

SessionView example (all timestamps are UTC; actual times set server-side):

```json
{"threadId":"1dbbd0d0-2a66-4db7-a117-1dbf3e2e4444","conversationId":"e1c7118d-3946-45c8-a69e-708bb51728e8","sourceRequestId":"user-12345678","status":"RUNNING","createdAt":"2026-11-20T04:00:00Z","expiresAt":"2026-11-20T04:30:00Z"}
```

List is newest-first and limited to 1..100 (default 20). No pagination cursor in D5. Legacy rows may contain null sourceRequestId; do not treat them as newly registered D5 workflows. Only ACTIVE owned conversations are exposed. Expired sessions remain readable; compare expiresAt to current UTC. A same-status PATCH is a no-op and does not refresh expiration; any state-changing PATCH after expiration returns 410.

Status JSON: `{"status":"WAITING"}`. Allowed: RUNNING, WAITING, COMPLETED, REJECTED, ENDED, NOT_CONFIRMED. RUNNING/WAITING may transition to any allowed state; COMPLETED/REJECTED/ENDED/NOT_CONFIRMED accept only same-state no-op writes in D5. D6 must explicitly define verified reconciliation of uncertain outcomes. The registry does not grant permission to resume, authorize or execute. A pending or completed Graph checkpoint must be compared with actual bank order status. Do not automatically invoke the Graph on recovery reads.

## Error codes

400 malformed UUID, body, request ID, limit or status; 401 login required; 403 invalid service key; 404 missing/inaccessible session or ACTIVE conversation; 409 mismatched source, duplicate registration, invalid lifecycle transition; 410 expired state-changing update; 422 detected sensitive credentials (D3 guard); 503 service key not configured.

## Verification

From repository root:

```powershell
mvn -f .\banking-backend\pom.xml "-Dtest=WorkflowSessionServiceTest" test
mvn -f .\banking-backend\pom.xml test
```

Run real MySQL/API integration separately. Registry-only Java calls do not create checkpoints; Python must register, invoke the persistent graph, and update status. In D5, restored threads are read-only; current-process approval paths still require existing bank controls. No bearer, OTP, secret, full Graph state, or raw user-content copy is stored in the registry.
