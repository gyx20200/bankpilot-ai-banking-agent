-- BankPilot Day 3 migration. Run Day1 and Day2 migrations BEFORE this file.
-- Execute as MySQL administrator in Workbench, not as bankpilot_app.
-- MySQL 8.0.16+ supports CHECK constraints.
USE bankpilot;

CREATE TABLE IF NOT EXISTS transfer_orders (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT NOT NULL,
  sender_account_id BIGINT NOT NULL,
  payee_id BIGINT NOT NULL,
  receiver_account_id BIGINT NOT NULL,
  amount DECIMAL(18,2) NOT NULL,
  remark VARCHAR(80) NOT NULL DEFAULT '',
  request_id VARCHAR(64) NOT NULL,
  risk_level VARCHAR(10) NOT NULL,
  status VARCHAR(24) NOT NULL DEFAULT 'PENDING_APPROVAL',
  created_at DATETIME(6) NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  CONSTRAINT fk_tfo_user FOREIGN KEY(user_id) REFERENCES users(id),
  CONSTRAINT fk_tfo_sender FOREIGN KEY(sender_account_id) REFERENCES accounts(id),
  CONSTRAINT fk_tfo_payee FOREIGN KEY(payee_id) REFERENCES payees(id),
  CONSTRAINT fk_tfo_receiver FOREIGN KEY(receiver_account_id) REFERENCES accounts(id),
  CONSTRAINT chk_tfo_amount CHECK(amount > 0),
  CONSTRAINT chk_tfo_risk CHECK(risk_level IN ('YELLOW','RED')),
  CONSTRAINT chk_tfo_status CHECK(status IN ('PENDING_APPROVAL','AUTHORIZED','EXECUTING','SUCCESS','FAILED','UNKNOWN','CANCELLED')),
  UNIQUE KEY uk_tfo_user_request (user_id, request_id),
  KEY idx_tfo_user_day (user_id, created_at, status)
) ENGINE=InnoDB;

-- Prepared for Day 4. Day 3 code never writes approval_records.
CREATE TABLE IF NOT EXISTS approval_records (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  order_id BIGINT NOT NULL,
  user_id BIGINT NOT NULL,
  auth_method VARCHAR(20) NOT NULL,
  approval_status VARCHAR(16) NOT NULL,
  created_at DATETIME(6) NOT NULL,
  expires_at DATETIME(6) NULL,
  CONSTRAINT fk_ar_order FOREIGN KEY(order_id) REFERENCES transfer_orders(id),
  CONSTRAINT fk_ar_user FOREIGN KEY(user_id) REFERENCES users(id),
  CONSTRAINT chk_ar_method CHECK(auth_method IN ('CONFIRM','DEMO_OTP')),
  CONSTRAINT chk_ar_status CHECK(approval_status IN ('PENDING','APPROVED','REJECTED','EXPIRED')),
  KEY idx_ar_order (order_id)
) ENGINE=InnoDB;

-- Day 1 app user had SELECT only. Grant the MINIMUM write privilege for Day 3.
-- Do not grant UPDATE/DELETE on accounts or transactions, and no blanket DML privileges.
GRANT SELECT, INSERT ON bankpilot.transfer_orders TO 'bankpilot_app'@'localhost';
GRANT SELECT ON bankpilot.approval_records TO 'bankpilot_app'@'localhost';

-- =====================================================
-- Day 3: Transfer preparation database permissions
-- =====================================================
-- TransferPrepareService uses:
-- SELECT id FROM users WHERE id = ? FOR UPDATE
--
-- MySQL 8.0 requires SELECT plus UPDATE, DELETE,
-- or LOCK TABLES privilege for locking reads.
--
-- The following grant is for the local demo application.
-- It must be executed by a database administrator.

GRANT UPDATE ON bankpilot.users TO 'bankpilot_app'@'localhost';


SELECT TABLE_NAME FROM information_schema.TABLES
WHERE TABLE_SCHEMA='bankpilot' AND TABLE_NAME IN ('transfer_orders','approval_records');
