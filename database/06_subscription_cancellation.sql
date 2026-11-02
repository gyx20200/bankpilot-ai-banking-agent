-- Day6 incremental migration: existing BankPilot Day1-Day4 schema required.
-- Does not depend on the assistant's optional Day5 agent_tool_events table.
-- Execute ONCE in a LOCAL TEST DB as MySQL administrator. No existing tables modified.
USE bankpilot;

CREATE TABLE IF NOT EXISTS subscription_cancel_orders (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    subscription_id BIGINT NOT NULL,
    request_id VARCHAR(64) NOT NULL,
    workflow_id VARCHAR(64) NULL,
    merchant_name VARCHAR(100) NOT NULL,
    amount DECIMAL(18,2) NOT NULL,
    billing_cycle VARCHAR(20) NOT NULL,
    status VARCHAR(24) NOT NULL,
    expires_at DATETIME(6) NOT NULL,
    authorized_at DATETIME(6) NULL,
    executed_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    CONSTRAINT fk_sco_user FOREIGN KEY(user_id) REFERENCES users(id),
    CONSTRAINT fk_sco_subscription FOREIGN KEY(subscription_id) REFERENCES subscriptions(id),
    CONSTRAINT uk_sco_user_request UNIQUE(user_id, request_id),
    CONSTRAINT chk_sco_status CHECK(status IN ('PENDING_APPROVAL','AUTHORIZED','SUCCESS','CANCELLED')),
    KEY idx_sco_user_subscription(user_id, subscription_id, status),
    KEY idx_sco_user_workflow(user_id, workflow_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS subscription_cancel_events (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    action VARCHAR(30) NOT NULL,
    result VARCHAR(30) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    CONSTRAINT fk_sce_order FOREIGN KEY(order_id) REFERENCES subscription_cancel_orders(id),
    CONSTRAINT fk_sce_user FOREIGN KEY(user_id) REFERENCES users(id),
    KEY idx_sce_user_order(user_id, order_id, created_at)
) ENGINE=InnoDB;

-- Day4 application user already has SELECT on subscriptions; grant only required updates.
GRANT SELECT, INSERT ON bankpilot.subscription_cancel_orders TO 'bankpilot_app'@'localhost';
GRANT UPDATE (status,authorized_at,executed_at,updated_at) ON bankpilot.subscription_cancel_orders TO 'bankpilot_app'@'localhost';
GRANT SELECT, INSERT ON bankpilot.subscription_cancel_events TO 'bankpilot_app'@'localhost';
GRANT UPDATE (status,cancelled_at,next_pay_date) ON bankpilot.subscriptions TO 'bankpilot_app'@'localhost';

SELECT TABLE_NAME FROM information_schema.TABLES
WHERE TABLE_SCHEMA='bankpilot' AND TABLE_NAME IN ('subscription_cancel_orders','subscription_cancel_events');
