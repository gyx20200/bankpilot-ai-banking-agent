CREATE TABLE users (
  id BIGINT PRIMARY KEY,
  display_name VARCHAR(80) NOT NULL
);
CREATE TABLE accounts (
  id BIGINT PRIMARY KEY,
  user_id BIGINT NOT NULL,
  account_no VARCHAR(32) NOT NULL UNIQUE,
  balance DECIMAL(18,2) NOT NULL,
  status VARCHAR(20) NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE TABLE transactions (
  id BIGINT PRIMARY KEY,
  account_id BIGINT NOT NULL,
  direction VARCHAR(10) NOT NULL,
  amount DECIMAL(18,2) NOT NULL,
  category VARCHAR(50) NOT NULL,
  merchant_name VARCHAR(100),
  description VARCHAR(255),
  occurred_at TIMESTAMP NOT NULL,
  FOREIGN KEY (account_id) REFERENCES accounts(id)
);
CREATE TABLE payees (
  id BIGINT PRIMARY KEY,
  user_id BIGINT NOT NULL,
  payee_name VARCHAR(100) NOT NULL,
  payee_account_id BIGINT NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id),
  FOREIGN KEY (payee_account_id) REFERENCES accounts(id)
);
CREATE TABLE subscriptions (
  id BIGINT PRIMARY KEY,
  user_id BIGINT NOT NULL,
  merchant_name VARCHAR(100) NOT NULL,
  amount DECIMAL(18,2) NOT NULL,
  billing_cycle VARCHAR(20) NOT NULL,
  status VARCHAR(20) NOT NULL,
  next_pay_date DATE
);
