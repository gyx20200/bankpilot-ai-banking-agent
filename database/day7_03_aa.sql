-- Execute once in a backed-up Day7 MySQL 8 demo database after day7_01_auth.sql.
CREATE TABLE aa_collections (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  initiator_user_id BIGINT NOT NULL,
  request_id VARCHAR(64) NOT NULL,
  request_fingerprint CHAR(64) NOT NULL,
  split_mode VARCHAR(24) NOT NULL,
  reason VARCHAR(80) NOT NULL DEFAULT '',
  total_amount DECIMAL(18,2) NOT NULL,
  self_amount DECIMAL(18,2) NOT NULL,
  requested_amount DECIMAL(18,2) NOT NULL,
  status VARCHAR(24) NOT NULL DEFAULT 'DRAFT',
  created_at DATETIME(6) NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  CONSTRAINT chk_aa_split CHECK(split_mode IN ('total_with_self','per_person')),
  CONSTRAINT chk_aa_status CHECK(status IN ('DRAFT','PUBLISHED','PARTIAL','COMPLETED','CANCELLED')),
  CONSTRAINT chk_aa_values CHECK(total_amount>0 AND self_amount>=0 AND requested_amount>0 AND total_amount=self_amount+requested_amount),
  UNIQUE KEY uk_aa_request(initiator_user_id,request_id),
  CONSTRAINT fk_aa_initiator FOREIGN KEY(initiator_user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE aa_collection_items (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  collection_id BIGINT NOT NULL,
  payer_user_id BIGINT NOT NULL,
  amount DECIMAL(18,2) NOT NULL,
  status VARCHAR(24) NOT NULL DEFAULT 'PENDING',
  transfer_order_id BIGINT NULL,
  paid_at DATETIME(6) NULL,
  created_at DATETIME(6) NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  CONSTRAINT chk_aai_amount CHECK(amount>0),
  CONSTRAINT chk_aai_status CHECK(status IN ('PENDING','PAYING','PAID','DECLINED','FAILED')),
  UNIQUE KEY uk_aa_payer(collection_id,payer_user_id),
  UNIQUE KEY uk_aa_transfer(transfer_order_id),
  KEY idx_aa_payer(payer_user_id,status),
  CONSTRAINT fk_aai_collection FOREIGN KEY(collection_id) REFERENCES aa_collections(id),
  CONSTRAINT fk_aai_payer FOREIGN KEY(payer_user_id) REFERENCES users(id),
  CONSTRAINT fk_aai_transfer FOREIGN KEY(transfer_order_id) REFERENCES transfer_orders(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
