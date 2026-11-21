-- BankPilot V2 / D6: one durable approval-recovery claim per workflow thread.
-- Backup the selected demo database before applying this migration ONCE.
-- Do not put OTPs, bearer tokens, credentials, or raw graph state in this table.
CREATE TABLE IF NOT EXISTS agent_workflow_recovery_claims (
    thread_id VARCHAR(128) NOT NULL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    action_id CHAR(36) NOT NULL,
    checkpoint_id VARCHAR(128) NOT NULL,
    approved BOOLEAN NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'CLAIMED',
    created_at DATETIME(6) NOT NULL,
    finalized_at DATETIME(6) NULL,
    CONSTRAINT fk_recovery_workflow FOREIGN KEY (thread_id)
        REFERENCES agent_workflow_sessions(thread_id),
    CONSTRAINT uk_recovery_action UNIQUE (action_id),
    CONSTRAINT chk_recovery_status CHECK
        (status IN ('CLAIMED','COMPLETED','REJECTED','NOT_CONFIRMED')),
    KEY idx_recovery_owner (user_id,created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
