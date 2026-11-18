
-- BankPilot 2.0 / D3
-- Execute ONLY on the chosen, backed-up test database.
-- No USE statement: select the database explicitly in mysql CLI.

CREATE TABLE IF NOT EXISTS agent_conversations (
    id CHAR(36) NOT NULL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    title VARCHAR(100) NOT NULL DEFAULT '新会话',
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,

    CONSTRAINT fk_conversation_user
      FOREIGN KEY (user_id) REFERENCES users(id),

    CONSTRAINT chk_conversation_status
      CHECK (status IN ('ACTIVE', 'ARCHIVED')),

    UNIQUE KEY uk_conversation_id_user (id, user_id),
    KEY idx_conversation_user_time
      (user_id, updated_at, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS agent_messages (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    conversation_id CHAR(36) NOT NULL,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    request_id VARCHAR(64) NULL,
    created_at DATETIME(6) NOT NULL,

    CONSTRAINT fk_message_conversation
      FOREIGN KEY (conversation_id)
      REFERENCES agent_conversations(id),

    CONSTRAINT chk_message_role
      CHECK (role IN ('USER', 'ASSISTANT')),

    UNIQUE KEY uk_message_request
      (conversation_id, request_id),

    KEY idx_message_conversation_id
      (conversation_id, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS agent_user_memories (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    memory_key VARCHAR(100) NOT NULL,
    memory_value TEXT NOT NULL,
    confirmed_at DATETIME(6) NOT NULL,
    expires_at DATETIME(6) NULL,

    CONSTRAINT fk_memory_user
      FOREIGN KEY (user_id) REFERENCES users(id),

    UNIQUE KEY uk_user_memory (user_id, memory_key),
    KEY idx_memory_user_expiry (user_id, expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS agent_workflow_sessions (
    thread_id VARCHAR(128) NOT NULL PRIMARY KEY,
    conversation_id CHAR(36) NOT NULL,
    user_id BIGINT NOT NULL,
    workflow_id VARCHAR(64) NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'RUNNING',
    created_at DATETIME(6) NOT NULL,
    expires_at DATETIME(6) NOT NULL,

    CONSTRAINT fk_workflow_conversation_owner
      FOREIGN KEY (conversation_id, user_id)
      REFERENCES agent_conversations(id, user_id),

    KEY idx_workflow_conversation
      (conversation_id, created_at),

    KEY idx_workflow_user_status
      (user_id, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
