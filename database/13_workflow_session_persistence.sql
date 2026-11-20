-- BankPilot 2.0 / D5. Execute once in the selected, backed-up test database.
-- If source_request_id or uk_workflow_source_request already exists, inspect
-- the existing definition rather than rerunning this migration.
ALTER TABLE agent_workflow_sessions
    ADD COLUMN source_request_id VARCHAR(64) NULL AFTER conversation_id,
    ADD UNIQUE KEY uk_workflow_source_request (conversation_id, source_request_id);
