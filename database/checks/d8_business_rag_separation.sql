-- D8 read-only sanity check. Change DB target if your local demo DB differs.
USE bankpilot_day7_test;
-- RAG rebuild / retrieval MUST NOT modify these account/transfer counts.
SELECT 'accounts' AS entity, COUNT(*) AS rows_count, COALESCE(SUM(balance),0) AS amount_total FROM accounts
UNION ALL SELECT 'transfer_orders', COUNT(*), COALESCE(SUM(amount),0) FROM transfer_orders
UNION ALL SELECT 'transactions', COUNT(*), COALESCE(SUM(amount),0) FROM transactions;
-- Knowledge corpus is checked-in public JSON; vectors live in agent-service/data/rag_chroma,
-- NOT in private banking data or ledger tables.
