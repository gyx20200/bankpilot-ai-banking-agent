-- Day4 upgrade for an EXISTING Day3 BankPilot LOCAL-DEMO database.
-- Run ONCE as a MySQL administrator in MySQL Workbench, after backing up.
-- Requires Day1+Day2+Day3 migrations. Do not use with real financial data.
USE bankpilot;

-- One verified challenge/confirmation per order for this minimal workflow.
ALTER TABLE approval_records
  ADD COLUMN otp_salt CHAR(32) NULL,
  ADD COLUMN otp_hash CHAR(64) NULL,
  ADD COLUMN failed_attempts INT NOT NULL DEFAULT 0,
  ADD COLUMN authorized_at DATETIME(6) NULL,
  ADD UNIQUE KEY uk_approval_order (order_id),
  ADD CONSTRAINT chk_ar_attempts CHECK (failed_attempts BETWEEN 0 AND 5);

-- Correlate BOTH credit/debit entries to one transfer; old Day2 records stay NULL.
ALTER TABLE transactions
  ADD COLUMN transfer_order_id BIGINT NULL,
  ADD CONSTRAINT fk_tx_transfer_order FOREIGN KEY(transfer_order_id) REFERENCES transfer_orders(id),
  ADD UNIQUE KEY uk_tx_order_direction (transfer_order_id, direction);

CREATE TABLE IF NOT EXISTS audit_events (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT NOT NULL,
  order_id BIGINT NULL,
  action VARCHAR(32) NOT NULL,
  result VARCHAR(32) NOT NULL,
  created_at DATETIME(6) NOT NULL,
  CONSTRAINT fk_audit_user FOREIGN KEY(user_id) REFERENCES users(id),
  CONSTRAINT fk_audit_order FOREIGN KEY(order_id) REFERENCES transfer_orders(id),
  INDEX idx_audit_user_order (user_id, order_id, created_at)
) ENGINE=InnoDB;

-- Day3 app account had INSERT only on orders and read-only on other tables.
-- Grant only the permissions needed for the Day4 simulated account operation.
GRANT UPDATE (status, risk_level, updated_at) ON bankpilot.transfer_orders TO 'bankpilot_app'@'localhost';
GRANT SELECT, INSERT, UPDATE ON bankpilot.approval_records TO 'bankpilot_app'@'localhost';
GRANT UPDATE (balance) ON bankpilot.accounts TO 'bankpilot_app'@'localhost';
GRANT INSERT ON bankpilot.transactions TO 'bankpilot_app'@'localhost';
GRANT SELECT, INSERT ON bankpilot.audit_events TO 'bankpilot_app'@'localhost';

-- Confirm fields/tables after migration.
SELECT TABLE_NAME, COLUMN_NAME FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA='bankpilot' AND (
 (TABLE_NAME='approval_records' AND COLUMN_NAME IN ('otp_hash','otp_salt','failed_attempts','authorized_at')) OR
 (TABLE_NAME='transactions' AND COLUMN_NAME='transfer_order_id') OR
 TABLE_NAME='audit_events'
) ORDER BY TABLE_NAME, ORDINAL_POSITION;
