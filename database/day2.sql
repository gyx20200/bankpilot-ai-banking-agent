-- Day 2 migration and repeatable seed for the Day 1 BankPilot LOCAL demo.
-- PREREQUISITE: execute Day 1 database/init.sql once (users/accounts exist).
-- Run this as the MySQL admin user in Workbench, NEVER as the read-only app user.
USE bankpilot;

CREATE TABLE IF NOT EXISTS transactions (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    account_id BIGINT NOT NULL,
    direction VARCHAR(10) NOT NULL,
    amount DECIMAL(18,2) NOT NULL,
    category VARCHAR(50) NOT NULL,
    merchant_name VARCHAR(100),
    description VARCHAR(255),
    occurred_at DATETIME NOT NULL,
    CONSTRAINT fk_transactions_account FOREIGN KEY (account_id) REFERENCES accounts(id),
    CONSTRAINT chk_transactions_amount CHECK (amount > 0),
    CONSTRAINT chk_transactions_direction CHECK (direction IN ('IN','OUT')),
    INDEX idx_transactions_account_time (account_id, occurred_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS payees (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    payee_name VARCHAR(100) NOT NULL,
    payee_account_id BIGINT NOT NULL,
    CONSTRAINT fk_payees_user FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT fk_payees_account FOREIGN KEY (payee_account_id) REFERENCES accounts(id),
    UNIQUE KEY uk_payees_user_account (user_id, payee_account_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS subscriptions (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    merchant_name VARCHAR(100) NOT NULL,
    amount DECIMAL(18,2) NOT NULL,
    billing_cycle VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    next_pay_date DATE,
    cancelled_at DATETIME,
    CONSTRAINT fk_subscriptions_user FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT chk_subscriptions_amount CHECK (amount > 0),
    CONSTRAINT chk_subscriptions_status CHECK (status IN ('ACTIVE','CANCELLED')),
    CONSTRAINT chk_subscriptions_cycle CHECK (billing_cycle IN ('MONTHLY','YEARLY')),
    INDEX idx_subscriptions_user_status (user_id, status)
) ENGINE=InnoDB;

-- Seed data is idempotent for a fresh demo DB. It does NOT adjust accounts.balance.
-- Avoid rerunning Day 1 init.sql during a balance-change test (it may restore demo defaults).
START TRANSACTION;

INSERT INTO transactions (id,account_id,direction,amount,category,merchant_name,description,occurred_at)
VALUES
(1,1,'IN',8000.00,'工资','公司','十月工资','2026-10-03 09:00:00'),
(2,1,'OUT',35.00,'餐饮','美团外卖','午餐','2026-10-05 12:00:00'),
(3,1,'OUT',69.00,'购物','京东','生活用品','2026-10-06 19:00:00'),
(4,1,'OUT',25.00,'订阅','视频会员','会员自动扣费','2026-10-08 08:00:00'),
(5,1,'OUT',28.00,'餐饮','食堂','工作日午餐','2026-09-10 12:00:00'),
(6,1,'OUT',200.00,'购物','商场','服装消费','2026-09-20 16:00:00'),
(7,1,'OUT',15.00,'交通','地铁','地铁出行','2026-09-22 18:00:00')
ON DUPLICATE KEY UPDATE id=id;

INSERT INTO payees (id,user_id,payee_name,payee_account_id)
VALUES (1,1,'李四',2)
ON DUPLICATE KEY UPDATE id=id;

INSERT INTO subscriptions (id,user_id,merchant_name,amount,billing_cycle,status,next_pay_date)
VALUES
(1,1,'视频会员',25.00,'MONTHLY','ACTIVE','2026-11-08'),
(2,1,'音乐会员',15.00,'MONTHLY','ACTIVE','2026-11-12')
ON DUPLICATE KEY UPDATE id=id;

COMMIT;

SELECT 'transactions' AS table_name, COUNT(*) AS total FROM transactions
UNION ALL SELECT 'payees', COUNT(*) FROM payees
UNION ALL SELECT 'subscriptions', COUNT(*) FROM subscriptions;

SELECT a.account_no, a.balance FROM accounts a WHERE a.user_id=1;
