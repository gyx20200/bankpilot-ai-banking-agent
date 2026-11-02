USE bankpilot;
-- A: Do the 3 tables exist and contain seed rows?
SHOW TABLES;
SELECT 'transactions' AS table_name, COUNT(*) AS n FROM transactions
UNION ALL SELECT 'payees', COUNT(*) FROM payees
UNION ALL SELECT 'subscriptions', COUNT(*) FROM subscriptions;

-- B: Do all seed rows belong to user 1; are income / expenses consistent?
SELECT t.id, t.direction, t.amount, t.category, t.merchant_name, t.occurred_at
FROM transactions t JOIN accounts a ON t.account_id=a.id
WHERE a.user_id=1 ORDER BY t.occurred_at DESC, t.id DESC;

-- C: Does payee 1 point to the correct account?
SELECT p.id, p.payee_name, a.account_no FROM payees p
JOIN accounts a ON a.id=p.payee_account_id WHERE p.user_id=1;

-- D: Subscription list and current demo balance (history is a snapshot; it does not debit again)
SELECT id, merchant_name, amount, billing_cycle, status FROM subscriptions WHERE user_id=1;
SELECT a.user_id, a.account_no, a.balance FROM accounts a WHERE a.user_id=1;

-- E: Confirm app DB user is SELECT-only (run as root):
SHOW GRANTS FOR 'bankpilot_app'@'localhost';
