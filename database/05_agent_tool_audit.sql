-- BankPilot Day 5: Agent read/prepare TOOL CALL METADATA (no secrets, no model prompts).
-- Requires all Day1-Day4 migrations. Run once as MySQL administrator, in a disposable demo database.
USE bankpilot;

CREATE TABLE IF NOT EXISTS agent_tool_events (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    request_id VARCHAR(64) NOT NULL,
    tool_name VARCHAR(48) NOT NULL,
    http_method VARCHAR(8) NOT NULL,
    http_status SMALLINT UNSIGNED NOT NULL,
    created_at DATETIME(6) NOT NULL,
    CONSTRAINT fk_day5_tool_events_user FOREIGN KEY (user_id) REFERENCES users(id),
    KEY idx_day5_tool_events_user_time (user_id, created_at),
    KEY idx_day5_tool_events_request_id (request_id)
) ENGINE=InnoDB;

-- Minimal extra privileges; all Day4 transfer, approval and money permissions are unchanged.
GRANT SELECT, INSERT ON bankpilot.agent_tool_events TO 'bankpilot_app'@'localhost';

SELECT TABLE_NAME FROM information_schema.TABLES
WHERE TABLE_SCHEMA='bankpilot' AND TABLE_NAME='agent_tool_events';
