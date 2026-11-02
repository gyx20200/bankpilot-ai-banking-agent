-- DANGER: ONLY execute on a DEDICATED, disposable LOCAL BankPilot contest demo database.
-- DELETES all simulated transfer orders, approvals, matching transfer ledger and audit events.
-- RESETS both seeded fake account balances. Never use with real data, shared production DB.
USE bankpilot;
START TRANSACTION;
DELETE FROM audit_events;
DELETE FROM transactions WHERE transfer_order_id IS NOT NULL;
DELETE FROM approval_records;
DELETE FROM transfer_orders;
UPDATE accounts SET balance = 12580.50 WHERE id=1 AND account_no='DEMO-6688';
UPDATE accounts SET balance = 5000.00 WHERE id=2 AND account_no='DEMO-5291';
COMMIT;
SELECT id, account_no, balance FROM accounts ORDER BY id;
