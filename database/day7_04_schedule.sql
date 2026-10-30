-- Run ONCE against restored Day7 test DB only.
CREATE TABLE scheduled_transfers (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    owner_user_id BIGINT NOT NULL,
    sender_account_id BIGINT NOT NULL,
    receiver_account_id BIGINT NOT NULL,
    payee_id BIGINT NOT NULL,
    amount DECIMAL(18,2) NOT NULL,
    remark VARCHAR(80) NOT NULL DEFAULT '',
    request_id VARCHAR(64) NOT NULL,
    scope_hash CHAR(64) NOT NULL,
    scheduled_at_utc DATETIME(6) NOT NULL,
    display_timezone VARCHAR(64) NOT NULL DEFAULT 'Asia/Shanghai',
    status VARCHAR(24) NOT NULL DEFAULT 'PENDING_AUTH',
    transfer_order_id BIGINT NULL,
    last_error_code VARCHAR(64) NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    executed_at DATETIME(6) NULL,
    CONSTRAINT chk_sched_amount CHECK(amount>0),
    CONSTRAINT chk_sched_status CHECK(status IN ('PENDING_AUTH','SCHEDULED','PROCESSING','SUCCESS','FAILED','CANCELLED','MISSED','UNKNOWN')),
    UNIQUE KEY uk_sched_request(owner_user_id,request_id),
    UNIQUE KEY uk_sched_transfer(transfer_order_id),
    INDEX idx_sched_due(status,scheduled_at_utc),
    CONSTRAINT fk_sched_owner FOREIGN KEY(owner_user_id) REFERENCES users(id),
    CONSTRAINT fk_sched_sender FOREIGN KEY(sender_account_id) REFERENCES accounts(id),
    CONSTRAINT fk_sched_receiver FOREIGN KEY(receiver_account_id) REFERENCES accounts(id),
    CONSTRAINT fk_sched_payee FOREIGN KEY(payee_id) REFERENCES payees(id),
    CONSTRAINT fk_sched_transfer FOREIGN KEY(transfer_order_id) REFERENCES transfer_orders(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE scheduled_transfer_authorizations (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    schedule_id BIGINT NOT NULL UNIQUE,
    user_id BIGINT NOT NULL,
    auth_method VARCHAR(24) NOT NULL,
    covered_risk VARCHAR(10) NOT NULL,
    scope_hash CHAR(64) NOT NULL,
    authorized_at DATETIME(6) NOT NULL,
    valid_until DATETIME(6) NULL,
    revoked_at DATETIME(6) NULL,
    status VARCHAR(24) NOT NULL,
    CONSTRAINT chk_sched_auth_status CHECK(status IN ('ACTIVE','REVOKED','EXPIRED')),
    CONSTRAINT chk_sched_auth_risk CHECK(covered_risk IN ('YELLOW','RED')),
    CONSTRAINT fk_sched_auth_schedule FOREIGN KEY(schedule_id) REFERENCES scheduled_transfers(id),
    CONSTRAINT fk_sched_auth_user FOREIGN KEY(user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Independent 120-second challenge for RED schedule authorization.
CREATE TABLE scheduled_otp_challenges (
  schedule_id BIGINT NOT NULL PRIMARY KEY,
  user_id BIGINT NOT NULL,
  otp_salt CHAR(32) NOT NULL,
  otp_hash CHAR(64) NOT NULL,
  failed_attempts INT NOT NULL DEFAULT 0,
  expires_at DATETIME(6) NOT NULL,
  CONSTRAINT fk_sotp_schedule FOREIGN KEY(schedule_id) REFERENCES scheduled_transfers(id),
  CONSTRAINT fk_sotp_user FOREIGN KEY(user_id) REFERENCES users(id)
) ENGINE=InnoDB;
