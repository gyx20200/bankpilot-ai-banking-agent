USE bankpilot_day7_test;
-- READ ONLY; choose Day7 test schema first. Never run init.sql to reset funds.
SELECT DATABASE() AS active_schema;
SELECT id,display_name,phone,status FROM users ORDER BY id;
SELECT u.id,u.display_name,a.id AS account_id,a.balance,a.status AS account_status
 FROM users u JOIN accounts a ON a.user_id=u.id ORDER BY u.id;
SELECT c.id,c.initiator_user_id,c.reason,c.status,c.requested_amount,
 (SELECT COALESCE(SUM(i.amount),0) FROM aa_collection_items i WHERE i.collection_id=c.id AND i.status='PAID') AS actually_received
 FROM aa_collections c ORDER BY c.id DESC LIMIT 20;
SELECT i.id,i.collection_id,i.payer_user_id,i.amount,i.status,i.transfer_order_id,t.status AS bank_status
 FROM aa_collection_items i LEFT JOIN transfer_orders t ON t.id=i.transfer_order_id ORDER BY i.id DESC LIMIT 20;
SELECT s.id,s.owner_user_id,s.status,s.scheduled_at_utc,s.transfer_order_id,t.status AS bank_status,s.last_error_code
 FROM scheduled_transfers s LEFT JOIN transfer_orders t ON t.id=s.transfer_order_id ORDER BY s.id DESC LIMIT 20;
SELECT t.id,t.user_id,t.amount,t.status,t.remark,
 (SELECT COUNT(*) FROM transactions tr WHERE tr.transfer_order_id=t.id) AS ledger_legs
 FROM transfer_orders t ORDER BY t.id DESC LIMIT 20;
