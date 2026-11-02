-- Run after testing Agent / Java tools in Day 5.
USE bankpilot;
SELECT tool_name, http_status, COUNT(*) AS calls
FROM agent_tool_events GROUP BY tool_name, http_status ORDER BY tool_name, http_status;
SELECT id, user_id, request_id, tool_name, http_status, created_at
FROM agent_tool_events ORDER BY id DESC LIMIT 20;
-- Must remain unchanged by READ tools and prepare_transfer (until explicit Day4 authorization+execution):
SELECT id, user_id, balance FROM accounts ORDER BY id;
SELECT id, request_id, risk_level, status FROM transfer_orders ORDER BY id DESC LIMIT 20;
SELECT COUNT(*) AS successful_transfer_orders FROM transfer_orders WHERE status='SUCCESS';
