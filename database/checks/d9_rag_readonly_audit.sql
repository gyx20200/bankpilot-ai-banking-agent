-- BankPilot D9: read-only business state snapshots.
-- Run before AND after the test window, on the SAME database and while
-- no unrelated write work is running. Compare numbers manually.
-- Counts and balances are not full audit guarantees; use the D7 ledger audit too.
USE bankpilot_day7_test;

SELECT 'accounts' AS entity, COUNT(*) AS rows_count,
       COALESCE(SUM(balance), 0) AS amount_total FROM accounts
UNION ALL
SELECT 'transfer_orders', COUNT(*), COALESCE(SUM(amount), 0) FROM transfer_orders
UNION ALL
SELECT 'transactions', COUNT(*), COALESCE(SUM(amount), 0) FROM transactions;

SELECT status, COUNT(*) AS n
FROM transfer_orders GROUP BY status ORDER BY status;

SELECT status, COUNT(*) AS n
FROM agent_workflow_recovery_claims GROUP BY status ORDER BY status;

-- Check there is no unanticipated direct-to-bank RAG storage structure.
SHOW TABLES LIKE '%rag%';
