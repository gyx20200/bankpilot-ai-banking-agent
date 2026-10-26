-- Day4 read-only verification. Run in MySQL Workbench after tests.
USE bankpilot;
SELECT id, user_id, sender_account_id, receiver_account_id, amount,
       risk_level, status, created_at FROM transfer_orders ORDER BY id DESC LIMIT 20;
SELECT a.id, a.user_id, a.balance, a.status FROM accounts a ORDER BY a.id;
SELECT id, account_id, transfer_order_id, direction, amount, category, occurred_at
FROM transactions ORDER BY id DESC LIMIT 20;
SELECT id, order_id, user_id, auth_method, approval_status,
       failed_attempts, created_at, expires_at FROM approval_records ORDER BY id DESC LIMIT 20;
SELECT id, user_id, order_id, action, result, created_at
FROM audit_events ORDER BY id DESC LIMIT 50;
-- For every successful transfer, there must be 2 entries: OUT + IN.
SELECT o.id AS order_id, o.status, o.amount,
       COUNT(t.id) AS transfer_entries,
       SUM(CASE WHEN t.direction='OUT' THEN 1 ELSE 0 END) AS out_entries,
       SUM(CASE WHEN t.direction='IN' THEN 1 ELSE 0 END) AS in_entries
FROM transfer_orders o LEFT JOIN transactions t ON t.transfer_order_id=o.id
GROUP BY o.id, o.status, o.amount ORDER BY o.id DESC;
