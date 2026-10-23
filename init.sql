-- BankPilot Day 1: demo data ONLY. No real customers, credentials, or money.
CREATE DATABASE IF NOT EXISTS bankpilot CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE bankpilot;

CREATE TABLE IF NOT EXISTS users (
  id BIGINT PRIMARY KEY,
  display_name VARCHAR(80) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS accounts (
  id BIGINT PRIMARY KEY,
  user_id BIGINT NOT NULL,
  account_no VARCHAR(32) NOT NULL UNIQUE,
  balance DECIMAL(18,2) NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
  CONSTRAINT fk_accounts_user FOREIGN KEY (user_id) REFERENCES users(id),
  CONSTRAINT chk_accounts_balance CHECK (balance >= 0)
) ENGINE=InnoDB;

INSERT INTO users (id,display_name) VALUES
(1,'张小明'),(2,'李四')
ON DUPLICATE KEY UPDATE display_name=VALUES(display_name);

INSERT INTO accounts (id,user_id,account_no,balance,status) VALUES
(1,1,'DEMO-6688',12580.50,'ACTIVE'),
(2,2,'DEMO-5291',5000.00,'ACTIVE')
ON DUPLICATE KEY UPDATE user_id=VALUES(user_id),account_no=VALUES(account_no);

-- A local-only, read-only application user for the Day 1 demo.
-- Change the password in this file BEFORE executing it, then use the same value in DB_PASSWORD.
CREATE USER IF NOT EXISTS 'bankpilot_app'@'localhost' IDENTIFIED BY 'REPLACE_WITH_YOUR_LOCAL_PASSWORD';
GRANT SELECT ON bankpilot.* TO 'bankpilot_app'@'localhost';
-- If the app user already exists, CREATE USER IF NOT EXISTS will not change its password.
-- Change it explicitly with ALTER USER before proceeding if needed.

SELECT u.display_name, a.account_no, a.balance
FROM users u JOIN accounts a ON a.user_id=u.id;
