-- BankPilot D7 / READ-ONLY consistency audit.
-- This script never inserts, updates, or deletes banking data.
-- Run in MySQL Workbench after the D7 test orders have reached terminal states.
USE bankpilot_day7_test;

-- 0. Enter the actual NEW D7 test order IDs. Do NOT reuse old failed/uncertain IDs.
SET @d7_rejected_order_id = NULL;
SET @d7_approved_order_id = NULL;
SELECT CASE WHEN @d7_rejected_order_id IS NULL OR @d7_approved_order_id IS NULL
            THEN 'SET_BOTH_ORDER_IDS_BEFORE_ACCEPTANCE' ELSE 'CONFIGURED' END AS d7_input_check;

-- 1. Transfer status and ledger rows for the two nominated orders.
-- Rejected => CANCELLED + zero ledger entries;
-- Approved => SUCCESS + exactly one OUT and one IN for the same amount.
SELECT o.id AS order_id, o.user_id, o.amount, o.risk_level, o.status,
       COUNT(t.id) AS ledger_entries,
       SUM(CASE WHEN t.direction='OUT' THEN 1 ELSE 0 END) AS out_entries,
       SUM(CASE WHEN t.direction='IN' THEN 1 ELSE 0 END) AS in_entries,
       COALESCE(SUM(CASE WHEN t.direction='OUT' THEN t.amount ELSE 0 END),0) AS debit_total,
       COALESCE(SUM(CASE WHEN t.direction='IN' THEN t.amount ELSE 0 END),0) AS credit_total,
       CASE
         WHEN o.id=@d7_rejected_order_id AND o.status='CANCELLED' AND COUNT(t.id)=0 THEN 'PASS'
         WHEN o.id=@d7_approved_order_id AND o.status='SUCCESS'
              AND COUNT(t.id)=2
              AND SUM(CASE WHEN t.direction='OUT' THEN 1 ELSE 0 END)=1
              AND SUM(CASE WHEN t.direction='IN' THEN 1 ELSE 0 END)=1
              AND COALESCE(SUM(CASE WHEN t.direction='OUT' THEN t.amount ELSE 0 END),0)=o.amount
              AND COALESCE(SUM(CASE WHEN t.direction='IN' THEN t.amount ELSE 0 END),0)=o.amount THEN 'PASS'
         ELSE 'FAIL_OR_NOT_FINALIZED'
       END AS d7_verdict
FROM transfer_orders o
LEFT JOIN transactions t ON t.transfer_order_id=o.id
WHERE o.id IN (@d7_rejected_order_id,@d7_approved_order_id)
GROUP BY o.id, o.user_id, o.amount, o.risk_level, o.status
ORDER BY o.id;

-- 2. Integrity scan of ALL transfer orders: every SUCCESS has exactly 2 entries,
--    any non-SUCCESS has zero booked entries. Empty result means no violations.
SELECT o.id AS order_id, o.status, o.amount,
       COUNT(t.id) AS entry_count,
       SUM(CASE WHEN t.direction='OUT' THEN 1 ELSE 0 END) AS out_count,
       SUM(CASE WHEN t.direction='IN' THEN 1 ELSE 0 END) AS in_count
FROM transfer_orders o
LEFT JOIN transactions t ON t.transfer_order_id=o.id
GROUP BY o.id, o.status, o.amount
HAVING (o.status='SUCCESS'
        AND (COUNT(t.id)<>2
             OR SUM(CASE WHEN t.direction='OUT' THEN 1 ELSE 0 END)<>1
             OR SUM(CASE WHEN t.direction='IN' THEN 1 ELSE 0 END)<>1
             OR COALESCE(SUM(CASE WHEN t.direction='OUT' THEN t.amount ELSE 0 END),0)<>o.amount
             OR COALESCE(SUM(CASE WHEN t.direction='IN' THEN t.amount ELSE 0 END),0)<>o.amount))
    OR (o.status<>'SUCCESS' AND COUNT(t.id)<>0);

-- 3. D6 claim registry vs D5 lifecycle consistency.
-- CLAIMED / NOT_CONFIRMED require manual reconciliation, never auto-replay.
SELECT c.thread_id, c.user_id, c.approved,
       c.status AS recovery_status, s.status AS workflow_status,
       CASE
         WHEN c.status IN ('COMPLETED','REJECTED') AND c.status=s.status THEN 'MATCH'
         WHEN c.status='CLAIMED' THEN 'IN_PROGRESS_OR_STALE_RECONCILE'
         WHEN c.status='NOT_CONFIRMED' AND s.status='NOT_CONFIRMED' THEN 'FROZEN_RECONCILE'
         ELSE 'REVIEW_MISMATCH'
       END AS d7_registry_verdict
FROM agent_workflow_recovery_claims c
JOIN agent_workflow_sessions s ON s.thread_id=c.thread_id
ORDER BY c.created_at DESC LIMIT 100;

-- 4. Unexpected duplicate references should return no rows (unique constraints also protect).
SELECT conversation_id, source_request_id, COUNT(*) AS duplicate_count
FROM agent_workflow_sessions
WHERE source_request_id IS NOT NULL
GROUP BY conversation_id, source_request_id
HAVING COUNT(*)>1;

-- 5. Conversation role counts, latest 20 sessions. Not all sessions require an equal number
--    of USER and ASSISTANT messages (failures and clarifications may differ).
SELECT c.id AS conversation_id, c.title,
       SUM(CASE WHEN m.role='USER' THEN 1 ELSE 0 END) AS user_messages,
       SUM(CASE WHEN m.role='ASSISTANT' THEN 1 ELSE 0 END) AS assistant_messages
FROM agent_conversations c
LEFT JOIN agent_messages m ON m.conversation_id=c.id
GROUP BY c.id, c.title
ORDER BY MAX(c.created_at) DESC LIMIT 20;

-- 6. Inspect balances for the current test user; compare with pre-test snapshots.
-- Replace NULL with your own authenticated test user's numeric user ID.
SET @d7_user_id = NULL;
SELECT id,user_id,balance,status FROM accounts
WHERE user_id=@d7_user_id ORDER BY id;
