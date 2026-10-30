-- LOCAL DAY7 TEST DATABASE ONLY. Run as MySQL admin after restoring backup and migration.
-- Assumes bankpilot_app@localhost exists and has its own strong local password.
GRANT SELECT ON bankpilot_day7_test.* TO 'bankpilot_app'@'localhost';
GRANT UPDATE ON bankpilot_day7_test.users TO 'bankpilot_app'@'localhost';
GRANT UPDATE (balance) ON bankpilot_day7_test.accounts TO 'bankpilot_app'@'localhost';
GRANT INSERT ON bankpilot_day7_test.transactions TO 'bankpilot_app'@'localhost';
GRANT INSERT,UPDATE ON bankpilot_day7_test.payees TO 'bankpilot_app'@'localhost';
GRANT SELECT,INSERT,UPDATE ON bankpilot_day7_test.transfer_orders TO 'bankpilot_app'@'localhost';
GRANT SELECT,INSERT,UPDATE ON bankpilot_day7_test.approval_records TO 'bankpilot_app'@'localhost';
GRANT SELECT,INSERT ON bankpilot_day7_test.audit_events TO 'bankpilot_app'@'localhost';
GRANT SELECT,INSERT ON bankpilot_day7_test.agent_tool_events TO 'bankpilot_app'@'localhost';
GRANT SELECT,INSERT ON bankpilot_day7_test.agent_workflow_runs TO 'bankpilot_app'@'localhost';
GRANT SELECT,INSERT ON bankpilot_day7_test.agent_workflow_tasks TO 'bankpilot_app'@'localhost';
GRANT SELECT,INSERT,UPDATE ON bankpilot_day7_test.subscription_cancel_orders TO 'bankpilot_app'@'localhost';
GRANT SELECT,INSERT ON bankpilot_day7_test.subscription_cancel_events TO 'bankpilot_app'@'localhost';
GRANT UPDATE (status,cancelled_at,next_pay_date) ON bankpilot_day7_test.subscriptions TO 'bankpilot_app'@'localhost';
GRANT INSERT ON bankpilot_day7_test.users TO 'bankpilot_app'@'localhost';
GRANT INSERT ON bankpilot_day7_test.accounts TO 'bankpilot_app'@'localhost';
GRANT SELECT,INSERT,UPDATE ON bankpilot_day7_test.user_credentials TO 'bankpilot_app'@'localhost';
GRANT SELECT,UPDATE ON bankpilot_day7_test.day7_id_sequences TO 'bankpilot_app'@'localhost';
GRANT SELECT,INSERT,UPDATE ON bankpilot_day7_test.aa_collections TO 'bankpilot_app'@'localhost';
GRANT SELECT,INSERT,UPDATE ON bankpilot_day7_test.aa_collection_items TO 'bankpilot_app'@'localhost';
GRANT SELECT,INSERT,UPDATE ON bankpilot_day7_test.scheduled_transfers TO 'bankpilot_app'@'localhost';
GRANT SELECT,INSERT,UPDATE ON bankpilot_day7_test.scheduled_transfer_authorizations TO 'bankpilot_app'@'localhost';
GRANT SELECT,INSERT,UPDATE,DELETE ON bankpilot_day7_test.scheduled_otp_challenges TO 'bankpilot_app'@'localhost';
GRANT SELECT,INSERT ON bankpilot_day7_test.business_audit_events TO 'bankpilot_app'@'localhost';
