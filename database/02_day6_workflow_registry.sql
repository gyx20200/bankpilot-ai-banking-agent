-- Day6 Unified ADDITIONAL migration, applied after 01_day6_cancellation.sql.
-- Stores only a validated workflow PLAN and business relationships, not LLM prompts,
-- banking credentials, tool results or a LangGraph checkpoint.
USE bankpilot;

CREATE TABLE IF NOT EXISTS agent_workflow_runs (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    workflow_id VARCHAR(64) NOT NULL,
    plan_hash CHAR(64) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    CONSTRAINT fk_awr_user FOREIGN KEY(user_id) REFERENCES users(id),
    CONSTRAINT uk_awr_user_workflow UNIQUE(user_id,workflow_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS agent_workflow_tasks (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    run_id BIGINT NOT NULL,
    task_type VARCHAR(32) NOT NULL,
    month_value CHAR(7) NULL,
    merchant_name VARCHAR(100) NULL,
    CONSTRAINT fk_awt_run FOREIGN KEY(run_id) REFERENCES agent_workflow_runs(id),
    CONSTRAINT uk_awt_run_type UNIQUE(run_id,task_type),
    CONSTRAINT chk_awt_task CHECK(task_type IN ('monthly_analytics','list_subscriptions','cancel_subscription')),
    KEY idx_awt_run(run_id)
) ENGINE=InnoDB;

GRANT SELECT, INSERT ON bankpilot.agent_workflow_runs TO 'bankpilot_app'@'localhost';
GRANT SELECT, INSERT ON bankpilot.agent_workflow_tasks TO 'bankpilot_app'@'localhost';
-- No UPDATE or DELETE: immutable plans, safe retry via a new workflow_id.

SELECT TABLE_NAME FROM information_schema.TABLES
WHERE TABLE_SCHEMA='bankpilot'
  AND TABLE_NAME IN ('agent_workflow_runs','agent_workflow_tasks');
