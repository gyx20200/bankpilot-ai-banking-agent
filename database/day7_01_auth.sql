USE bankpilot_day7_test;
-- BankPilot Day 7: run against a BACKED-UP Day 6 database, with the correct DB selected.
-- No USE statement: SELECT DATABASE() before running. MySQL 8, local demo only.
ALTER TABLE users ADD COLUMN phone VARCHAR(20) NULL;
ALTER TABLE users ADD COLUMN phone_verified TINYINT(1) NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE';
CREATE UNIQUE INDEX uk_day7_users_phone ON users(phone);
CREATE TABLE user_credentials (
  user_id BIGINT NOT NULL PRIMARY KEY,
  username VARCHAR(64) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  password_updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  failed_login_count INT NOT NULL DEFAULT 0,
  locked_until DATETIME(6) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  CONSTRAINT fk_day7_cred_user FOREIGN KEY(user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- Day6 users.id and accounts.id are NOT AUTO_INCREMENT and referenced by foreign keys.
-- SERIALIZED sequence rows avoid unsafe MAX(id)+1 allocation under concurrent registration.
CREATE TABLE day7_id_sequences (
  entity VARCHAR(24) NOT NULL PRIMARY KEY,
  next_id BIGINT NOT NULL
) ENGINE=InnoDB;
INSERT INTO day7_id_sequences(entity,next_id) SELECT 'users',COALESCE(MAX(id),0)+1 FROM users;
INSERT INTO day7_id_sequences(entity,next_id) SELECT 'accounts',COALESCE(MAX(id),0)+1 FROM accounts;
-- Day6 demo-login remains for compatibility (localhost only); registration is real demo-user login.
