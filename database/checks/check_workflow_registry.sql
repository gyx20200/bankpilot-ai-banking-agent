-- Read-only health checks after running BOTH migrations.
USE bankpilot;
SHOW TABLES LIKE 'subscription_cancel%';
SHOW TABLES LIKE 'agent_workflow%';
SELECT workflow_id, user_id, created_at FROM agent_workflow_runs ORDER BY id DESC LIMIT 15;
SELECT r.workflow_id,t.task_type,t.month_value,t.merchant_name
FROM agent_workflow_runs r JOIN agent_workflow_tasks t ON t.run_id=r.id
ORDER BY r.id DESC,t.id LIMIT 30;
SELECT workflow_id, subscription_id, status, expires_at
FROM subscription_cancel_orders ORDER BY id DESC LIMIT 15;
SELECT id, merchant_name, status FROM subscriptions WHERE user_id=1 ORDER BY id;
