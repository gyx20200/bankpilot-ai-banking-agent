-- D13 SIMULATED investment MVP. Select the target TEST schema explicitly before running.
-- Do NOT run against production or after changing accounts with the Day1 reset script.
-- Example: mysql ... bankpilot_day7_test < database/15_investments_demo.sql
CREATE TABLE IF NOT EXISTS investment_products (
 id BIGINT PRIMARY KEY,
 code VARCHAR(32) NOT NULL UNIQUE,
 name VARCHAR(100) NOT NULL UNIQUE,
 risk_level INT NOT NULL,
 nav DECIMAL(18,2) NOT NULL,
 active BOOLEAN NOT NULL DEFAULT TRUE,
 description VARCHAR(255) NOT NULL,
 CONSTRAINT ck_d13_product_risk CHECK (risk_level BETWEEN 1 AND 3),
 CONSTRAINT ck_d13_product_nav CHECK (nav > 0)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS investment_profiles (
 user_id BIGINT PRIMARY KEY,
 risk_level INT NOT NULL,
 assessed_at DATETIME(6) NOT NULL,
 CONSTRAINT fk_d13_profile_user FOREIGN KEY(user_id) REFERENCES users(id),
 CONSTRAINT ck_d13_profile_risk CHECK (risk_level BETWEEN 1 AND 3)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS investment_positions (
 user_id BIGINT NOT NULL,
 product_id BIGINT NOT NULL,
 units DECIMAL(18,2) NOT NULL DEFAULT 0,
 cost_basis DECIMAL(18,2) NOT NULL DEFAULT 0,
 PRIMARY KEY(user_id,product_id),
 CONSTRAINT fk_d13_position_user FOREIGN KEY(user_id) REFERENCES users(id),
 CONSTRAINT fk_d13_position_product FOREIGN KEY(product_id) REFERENCES investment_products(id),
 CONSTRAINT ck_d13_position_units CHECK (units >= 0),
 CONSTRAINT ck_d13_position_cost CHECK (cost_basis >= 0)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS investment_orders (
 id BIGINT PRIMARY KEY AUTO_INCREMENT,
 user_id BIGINT NOT NULL,
 account_id BIGINT NOT NULL,
 product_id BIGINT NOT NULL,
 action VARCHAR(10) NOT NULL,
 units DECIMAL(18,2) NOT NULL,
 nav_snapshot DECIMAL(18,2) NOT NULL,
 amount DECIMAL(18,2) NOT NULL,
 risk_snapshot INT NOT NULL,
 request_id VARCHAR(64) NOT NULL,
 status VARCHAR(24) NOT NULL DEFAULT 'PENDING_APPROVAL',
 created_at DATETIME(6) NOT NULL,
 updated_at DATETIME(6) NOT NULL,
 CONSTRAINT fk_d13_order_user FOREIGN KEY(user_id) REFERENCES users(id),
 CONSTRAINT fk_d13_order_account FOREIGN KEY(account_id) REFERENCES accounts(id),
 CONSTRAINT fk_d13_order_product FOREIGN KEY(product_id) REFERENCES investment_products(id),
 CONSTRAINT ck_d13_order_action CHECK(action IN ('BUY','REDEEM')),
 CONSTRAINT ck_d13_order_status CHECK(status IN ('PENDING_APPROVAL','SUCCESS','CANCELLED','FAILED','EXPIRED')),
 CONSTRAINT ck_d13_order_units CHECK(units > 0),
 CONSTRAINT ck_d13_order_amount CHECK(amount > 0),
 UNIQUE KEY uk_d13_order_idempotency (user_id,request_id),
 INDEX idx_d13_user_orders(user_id,created_at)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS investment_ledger (
 id BIGINT PRIMARY KEY AUTO_INCREMENT,
 order_id BIGINT NOT NULL UNIQUE,
 user_id BIGINT NOT NULL,
 account_id BIGINT NOT NULL,
 product_id BIGINT NOT NULL,
 action VARCHAR(10) NOT NULL,
 cash_delta DECIMAL(18,2) NOT NULL,
 units_delta DECIMAL(18,2) NOT NULL,
 created_at DATETIME(6) NOT NULL,
 CONSTRAINT fk_d13_ledger_order FOREIGN KEY(order_id) REFERENCES investment_orders(id),
 CONSTRAINT fk_d13_ledger_user FOREIGN KEY(user_id) REFERENCES users(id),
 CONSTRAINT fk_d13_ledger_account FOREIGN KEY(account_id) REFERENCES accounts(id),
 CONSTRAINT fk_d13_ledger_product FOREIGN KEY(product_id) REFERENCES investment_products(id)
) ENGINE=InnoDB;
-- Fixed illustrative NAV, no simulated yield, guarantees or live pricing.
INSERT INTO investment_products(id,code,name,risk_level,nav,active,description)
VALUES
 (101,'BP-DEMO-R1','稳健模拟理财',1,100.00,TRUE,'R1低风险示例，固定演示净值，不代表收益保证'),
 (102,'BP-DEMO-R2','均衡模拟理财',2,80.00,TRUE,'R2中风险示例，可能亏损；本系统不模拟实际市场'),
 (103,'BP-DEMO-R3','成长模拟理财',3,50.00,TRUE,'R3高风险示例，可能亏损；非真实金融产品')
ON DUPLICATE KEY UPDATE id=id;
-- Grant minimum privileges on the selected TEST SCHEMA manually as DBA:
-- GRANT SELECT ON bankpilot_day7_test.investment_products TO 'bankpilot_app'@'localhost';
-- GRANT SELECT, INSERT, UPDATE ON bankpilot_day7_test.investment_profiles TO 'bankpilot_app'@'localhost';
-- GRANT SELECT, INSERT, UPDATE ON bankpilot_day7_test.investment_positions TO 'bankpilot_app'@'localhost';
-- GRANT SELECT, INSERT, UPDATE ON bankpilot_day7_test.investment_orders TO 'bankpilot_app'@'localhost';
-- GRANT SELECT, INSERT ON bankpilot_day7_test.investment_ledger TO 'bankpilot_app'@'localhost';
-- Existing account UPDATE(balance) and users SELECT/UPDATE privileges are reused.
