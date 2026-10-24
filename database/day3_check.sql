USE bankpilot;
SELECT id, user_id, sender_account_id, payee_id, receiver_account_id,
       amount, risk_level, status, request_id, created_at
FROM transfer_orders ORDER BY id DESC LIMIT 20;
SELECT id, account_no, balance FROM accounts ORDER BY id;
SELECT COUNT(*) AS approval_count FROM approval_records;
-- During Day 3 ALL transfer_orders must be PENDING_APPROVAL, ALL approval_records should be empty.
SELECT status, COUNT(*) AS total FROM transfer_orders GROUP BY status;
