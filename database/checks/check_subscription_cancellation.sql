-- Run in MySQL Workbench after executing a sample cancellation.
USE bankpilot;
SELECT id, user_id, subscription_id, request_id, workflow_id, status,
       authorized_at, executed_at, created_at
FROM subscription_cancel_orders ORDER BY id DESC LIMIT 20;
SELECT id, user_id, merchant_name, status, next_pay_date, cancelled_at
FROM subscriptions WHERE user_id=1 ORDER BY id;
SELECT order_id, action, result, created_at
FROM subscription_cancel_events ORDER BY id DESC LIMIT 30;
-- Check cancellation did NOT create a transfer or change a balance:
SELECT id, balance FROM accounts WHERE user_id=1 ORDER BY id;
