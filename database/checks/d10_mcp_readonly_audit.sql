-- D10 read-only baseline. Run before and after using BankPilot MCP read tools.
-- Use the SAME database, and pause other writes during the comparison.
USE bankpilot_day7_test;
SELECT 'accounts' AS entity, COUNT(*) AS rows_count,
       COALESCE(SUM(balance),0) AS amount_total FROM accounts
UNION ALL
SELECT 'transactions', COUNT(*), COALESCE(SUM(amount),0) FROM transactions
UNION ALL
SELECT 'transfer_orders', COUNT(*), COALESCE(SUM(amount),0) FROM transfer_orders
UNION ALL
SELECT 'approval_records', COUNT(*), 0 FROM approval_records;
-- Security of the bank account is enforced by Spring Security, NOT by MCP.
-- Note: MCP read calls can add non-business audit/trace rows; those are excluded here.
