-- D11: read-only before/after snapshot; run twice in Workbench as the same user.
-- Disable simulated background scheduled payouts while performing controlled checks.
USE bankpilot_day7_test;
SELECT 'accounts' AS item,COUNT(*) AS records,COALESCE(SUM(balance),0) AS amount_total FROM accounts
UNION ALL SELECT 'transactions',COUNT(*),COALESCE(SUM(amount),0) FROM transactions
UNION ALL SELECT 'transfer_orders',COUNT(*),COALESCE(SUM(amount),0) FROM transfer_orders
UNION ALL SELECT 'approval_records',COUNT(*),0 FROM approval_records
UNION ALL SELECT 'agent_workflow_recovery_claims',COUNT(*),0 FROM agent_workflow_recovery_claims;

-- For diagnostics only: no user data outside this controlled local demo.
SELECT id,user_id,amount,risk_level,status,created_at
FROM transfer_orders ORDER BY id DESC LIMIT 10;
-- Skills must never insert into transfer_orders or approval_records, or update account balances.
