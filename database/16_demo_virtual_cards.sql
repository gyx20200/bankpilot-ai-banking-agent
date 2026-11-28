-- D14 simulation-only schema. BACKUP the isolated bankpilot_day7_test first.
-- Run with the intended test schema selected. Never use production data.
CREATE TABLE IF NOT EXISTS demo_virtual_cards (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT NOT NULL,
  account_id BIGINT NOT NULL,
  card_alias VARCHAR(32) NOT NULL UNIQUE,
  card_type VARCHAR(24) NOT NULL DEFAULT 'VIRTUAL_DEBIT',
  status VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
  daily_ceiling DECIMAL(18,2) NOT NULL DEFAULT 3000.00,
  single_tx_limit DECIMAL(18,2) NOT NULL DEFAULT 1000.00,
  online_enabled BOOLEAN NOT NULL DEFAULT TRUE,
  issued_at DATETIME(6) NOT NULL,
  CONSTRAINT fk_d14_card_user FOREIGN KEY (user_id) REFERENCES users(id),
  CONSTRAINT fk_d14_card_account FOREIGN KEY (account_id) REFERENCES accounts(id),
  CONSTRAINT ck_d14_card_status CHECK (status IN ('ACTIVE','LOCKED','LOST')),
  CONSTRAINT ck_d14_card_type CHECK (card_type = 'VIRTUAL_DEBIT'),
  CONSTRAINT ck_d14_ceiling CHECK (daily_ceiling > 0),
  CONSTRAINT ck_d14_single_limit CHECK (single_tx_limit > 0 AND single_tx_limit <= daily_ceiling),
  UNIQUE KEY uk_d14_one_demo_card_per_user (user_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS demo_card_applications (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT NOT NULL,
  account_id BIGINT NOT NULL,
  request_id VARCHAR(64) NOT NULL,
  card_type VARCHAR(24) NOT NULL DEFAULT 'VIRTUAL_DEBIT',
  status VARCHAR(24) NOT NULL DEFAULT 'PENDING_APPROVAL',
  card_id BIGINT NULL,
  created_at DATETIME(6) NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  CONSTRAINT fk_d14_app_user FOREIGN KEY (user_id) REFERENCES users(id),
  CONSTRAINT fk_d14_app_account FOREIGN KEY (account_id) REFERENCES accounts(id),
  CONSTRAINT fk_d14_app_card FOREIGN KEY (card_id) REFERENCES demo_virtual_cards(id),
  CONSTRAINT ck_d14_app_status CHECK (status IN ('PENDING_APPROVAL','ISSUED','CANCELLED')),
  CONSTRAINT ck_d14_app_type CHECK (card_type = 'VIRTUAL_DEBIT'),
  UNIQUE KEY uk_d14_app_request (user_id, request_id),
  KEY idx_d14_app_owner (user_id, id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS demo_card_limit_events (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT NOT NULL,
  card_id BIGINT NOT NULL,
  request_id VARCHAR(64) NOT NULL,
  old_single_limit DECIMAL(18,2) NOT NULL,
  new_single_limit DECIMAL(18,2) NOT NULL,
  disable_online BOOLEAN NOT NULL,
  created_at DATETIME(6) NOT NULL,
  CONSTRAINT fk_d14_limit_user FOREIGN KEY (user_id) REFERENCES users(id),
  CONSTRAINT fk_d14_limit_card FOREIGN KEY (card_id) REFERENCES demo_virtual_cards(id),
  UNIQUE KEY uk_d14_limit_request (user_id,request_id)
) ENGINE=InnoDB;

-- DBA: grant least privileges only within the isolated test schema, using actual app user/host.
-- GRANT SELECT, INSERT, UPDATE ON bankpilot_day7_test.demo_virtual_cards TO 'bankpilot_app'@'localhost';
-- GRANT SELECT, INSERT, UPDATE ON bankpilot_day7_test.demo_card_applications TO 'bankpilot_app'@'localhost';
-- GRANT SELECT, INSERT ON bankpilot_day7_test.demo_card_limit_events TO 'bankpilot_app'@'localhost';
-- Card settings do not authorize payments, affect transfer limits, or create real PAN/CVV.
