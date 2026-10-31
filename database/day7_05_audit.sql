USE bankpilot_day7_test;
CREATE TABLE business_audit_events (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    actor_user_id BIGINT NULL,
    business_type VARCHAR(32) NOT NULL,
    business_id VARCHAR(64) NULL,
    action VARCHAR(48) NOT NULL,
    result VARCHAR(32) NOT NULL,
    trace_id VARCHAR(64) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    INDEX idx_business_audit_actor(actor_user_id,created_at),
    INDEX idx_business_audit_entity(business_type,business_id),
    CONSTRAINT fk_business_audit_actor FOREIGN KEY(actor_user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
