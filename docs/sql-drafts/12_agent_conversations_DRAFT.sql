
-- D2 DESIGN DRAFT — DO NOT EXECUTE ON LIVE DATABASE
-- Target: bankpilot_day7_test
-- Review user ownership, retention and workflow lifecycle before D3.

CREATE TABLE IF NOT EXISTS agent_conversations (
    id CHAR(36) NOT NULL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    title VARCHAR(100) NOT NULL DEFAULT '新会话',
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),

    CONSTRAINT fk_agent_conversation_user
        FOREIGN KEY (user_id) REFERENCES users(id),

    CONSTRAINT chk_agent_conversation_status
        CHECK (status IN ('ACTIVE', 'ARCHIVED')),

    INDEX idx_agent_conversation_user_time
        (user_id, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE IF NOT EXISTS agent_messages (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    conversation_id CHAR(36) NOT NULL,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),

    CONSTRAINT fk_agent_message_conversation
        FOREIGN KEY (conversation_id)
        REFERENCES agent_conversations(id),

    CONSTRAINT chk_agent_message_role
        CHECK (role IN ('USER', 'ASSISTANT')),

    INDEX idx_agent_message_conversation_id
        (conversation_id, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
