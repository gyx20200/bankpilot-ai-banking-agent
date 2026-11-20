package com.bankpilot.demo;

import java.nio.charset.StandardCharsets;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.Base64;
import java.util.Collections;
import java.util.List;
import java.util.UUID;
import java.util.regex.Pattern;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

/**
 * MySQL-backed conversations, scoped to the authenticated Java user.
 *
 * Required D3 tables: agent_conversations and agent_messages.
 * Required agent_messages columns: id, conversation_id, role, content,
 * request_id, created_at. Required unique index: (conversation_id, request_id).
 *
 * All persisted DATETIME(6) values are UTC wall-clock values and are
 * serialized to ISO-8601 Z. No bank order, OTP or graph checkpoint is stored here.
 */
@Service
public class ConversationService {
    private static final int MAX_PAGE = 100;
    private static final int MAX_TITLE = 100;
    private static final int MAX_MESSAGE = 2000;
    private static final Pattern REQUEST_ID = Pattern.compile("[A-Za-z0-9_-]{8,64}");
    private static final Pattern BEARER_SECRET = Pattern.compile(
            "(?i)\\bBearer\\s+[^\\s]{8,}");
    private static final Pattern EXPLICIT_SECRET = Pattern.compile(
            "(?iu)(?:password|passwd|pwd|access[_-]?token|token|otp|验证码|密码)"
            + "\\s*(?:[:：=]|是|为)\\s*[^\\s，,。;；]{4,}");
    // Redact obvious identifiers before persisting the message.
    private static final Pattern MOBILE = Pattern.compile("(?<!\\d)1[3-9]\\d{9}(?!\\d)");
    private static final Pattern LONG_ACCOUNT = Pattern.compile("(?<!\\d)\\d{16,19}(?!\\d)");

    private final JdbcTemplate jdbc;

    public ConversationService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public record ConversationView(
            String conversationId, String title, String status,
            String createdAt, String updatedAt) { }

    public record ConversationList(List<ConversationView> items, String nextCursor) { }

    public record MessageView(
            long messageId, String role, String content, String createdAt) { }

    public record MessageList(String conversationId,
                              List<MessageView> items, Long nextBeforeId) { }

    public record WriteResult(MessageView message, boolean created) { }

    private record ConversationRow(String id, String title, String status,
                                   LocalDateTime createdAt, LocalDateTime updatedAt) {
        ConversationView view() {
            return new ConversationView(id, title, status, utc(createdAt), utc(updatedAt));
        }
    }

    private record MessageRow(long id, String role, String content, LocalDateTime createdAt) {
        MessageView view() {
            return new MessageView(id, role, content, utc(createdAt));
        }
    }

    private record Cursor(LocalDateTime updatedAt, String conversationId) { }

    private static final RowMapper<ConversationRow> CONVERSATION_MAPPER = (rs, number) ->
            new ConversationRow(rs.getString("id"), rs.getString("title"),
                    rs.getString("status"), dt(rs, "created_at"), dt(rs, "updated_at"));

    private static final RowMapper<MessageRow> MESSAGE_MAPPER = (rs, number) ->
            new MessageRow(rs.getLong("id"), rs.getString("role"),
                    rs.getString("content"), dt(rs, "created_at"));

    private static LocalDateTime dt(ResultSet rs, String field) throws SQLException {
        return rs.getObject(field, LocalDateTime.class);
    }

    private static String utc(LocalDateTime value) {
        return value.atOffset(ZoneOffset.UTC).toString();
    }

    private static LocalDateTime nowUtc() {
        return LocalDateTime.now(ZoneOffset.UTC);
    }

    private static ResponseStatusException bad(String reason) {
        return new ResponseStatusException(HttpStatus.BAD_REQUEST, reason);
    }

    private static ResponseStatusException notFound() {
        return new ResponseStatusException(HttpStatus.NOT_FOUND,
                "Conversation not found");
    }

    private static String uuid(String value) {
        if (value == null || value.length() != 36) throw bad("Invalid conversationId");
        try {
            String canonical = UUID.fromString(value).toString();
            if (!canonical.equalsIgnoreCase(value)) throw bad("Invalid conversationId");
            return canonical;
        } catch (IllegalArgumentException ex) {
            throw bad("Invalid conversationId");
        }
    }

    private static int pageSize(int value) {
        if (value < 1 || value > MAX_PAGE) throw bad("limit must be 1..100");
        return value;
    }

    private static String title(String value) {
        if (value == null || value.isBlank()) return "新会话";
        String cleaned = value.strip();
        if (cleaned.length() > MAX_TITLE || hasDisallowedControl(cleaned)) {
            throw bad("Invalid conversation title");
        }
        if (BEARER_SECRET.matcher(cleaned).find() || EXPLICIT_SECRET.matcher(cleaned).find()
                || MOBILE.matcher(cleaned).find() || LONG_ACCOUNT.matcher(cleaned).find()) {
            throw bad("Conversation title contains sensitive data");
        }
        return cleaned;
    }

    private static boolean hasDisallowedControl(String content) {
        for (int i = 0; i < content.length(); i++) {
            char ch = content.charAt(i);
            if (Character.isISOControl(ch) && ch != '\n' && ch != '\r' && ch != '\t') {
                return true;
            }
        }
        return false;
    }

    /**
     * D3 minimum sensitive-content guard. Tokens and OTP disclosures are rejected;
     * common phone/account number formats are masked before storage. This is NOT a
     * complete DLP engine; richer classification belongs in a later security task.
     */
    private static String safeMessage(String value) {
        if (value == null || value.isBlank()) throw bad("Message content is required");
        String clean = value.strip();
        if (clean.length() > MAX_MESSAGE || hasDisallowedControl(clean)) {
            throw bad("Invalid message content");
        }
        if (BEARER_SECRET.matcher(clean).find() || EXPLICIT_SECRET.matcher(clean).find()) {
            throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_ENTITY,
                    "Sensitive credentials cannot be stored in conversation history");
        }
        clean = MOBILE.matcher(clean).replaceAll("[手机号已脱敏]");
        return LONG_ACCOUNT.matcher(clean).replaceAll("[账号已脱敏]");
    }

    private static String requestId(String value) {
        if (value == null || !REQUEST_ID.matcher(value).matches()) {
            throw bad("requestId must contain 8..64 safe characters");
        }
        return value;
    }

    private static String cursorEncode(ConversationRow row) {
        String raw = row.updatedAt().toString() + "|" + row.id();
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(raw.getBytes(StandardCharsets.UTF_8));
    }

    private static Cursor cursorDecode(String value) {
        if (value == null || value.length() < 2 || value.length() > 256) {
            throw bad("Invalid cursor");
        }
        try {
            String raw = new String(Base64.getUrlDecoder().decode(value), StandardCharsets.UTF_8);
            int divider = raw.indexOf('|');
            if (divider <= 0 || divider == raw.length() - 1) throw bad("Invalid cursor");
            LocalDateTime date = LocalDateTime.parse(raw.substring(0, divider));
            String id = uuid(raw.substring(divider + 1));
            return new Cursor(date, id);
        } catch (IllegalArgumentException | DateTimeParseException ex) {
            throw bad("Invalid cursor");
        }
    }

    private void requireActive(long userId, String id, boolean lock) {
        String sql = "SELECT id FROM agent_conversations "
                + "WHERE id=? AND user_id=? AND status='ACTIVE'"
                + (lock ? " FOR UPDATE" : "");
        if (jdbc.query(sql, (rs, i) -> rs.getString(1), id, userId).isEmpty()) {
            throw notFound();
        }
    }

    private MessageRow findMessage(String conversationId, String idempotencyKey) {
        List<MessageRow> rows = jdbc.query("""
                SELECT id,role,content,created_at
                FROM agent_messages WHERE conversation_id=? AND request_id=?
                """, MESSAGE_MAPPER, conversationId, idempotencyKey);
        return rows.isEmpty() ? null : rows.get(0);
    }

    @Transactional
    public ConversationView create(long userId, String rawTitle) {
        String value = title(rawTitle);
        String id = UUID.randomUUID().toString();
        LocalDateTime now = nowUtc();
        Timestamp ts = Timestamp.valueOf(now);
        jdbc.update("""
                INSERT INTO agent_conversations
                  (id,user_id,title,status,created_at,updated_at)
                VALUES (?, ?, ?, 'ACTIVE', ?, ?)
                """, id, userId, value, ts, ts);
        return new ConversationRow(id, value, "ACTIVE", now, now).view();
    }

    @Transactional(readOnly = true)
    public ConversationList list(long userId, int requestedLimit, String opaqueCursor) {
        int limit = pageSize(requestedLimit);
        Cursor cursor = opaqueCursor == null || opaqueCursor.isBlank()
                ? null : cursorDecode(opaqueCursor);

        String sql = """
                SELECT id,title,status,created_at,updated_at
                FROM agent_conversations
                WHERE user_id=? AND status='ACTIVE'
                """ + (cursor == null ? "" :
                " AND (updated_at < ? OR (updated_at = ? AND id < ?))")
                + " ORDER BY updated_at DESC,id DESC LIMIT ?";
        List<Object> args = new ArrayList<>();
        args.add(userId);
        if (cursor != null) {
            Timestamp time = Timestamp.valueOf(cursor.updatedAt());
            args.add(time);
            args.add(time);
            args.add(cursor.conversationId());
        }
        args.add(limit + 1);
        List<ConversationRow> rows = jdbc.query(sql, CONVERSATION_MAPPER, args.toArray());
        boolean more = rows.size() > limit;
        if (more) rows = new ArrayList<>(rows.subList(0, limit));
        String next = more ? cursorEncode(rows.get(rows.size() - 1)) : null;
        return new ConversationList(rows.stream().map(ConversationRow::view).toList(), next);
    }

    @Transactional(readOnly = true)
    public ConversationView get(long userId, String conversationId) {
        String id = uuid(conversationId);
        List<ConversationRow> rows = jdbc.query("""
                SELECT id,title,status,created_at,updated_at
                FROM agent_conversations
                WHERE id=? AND user_id=? AND status='ACTIVE'
                """, CONVERSATION_MAPPER, id, userId);
        if (rows.isEmpty()) throw notFound();
        return rows.get(0).view();
    }

    @Transactional(readOnly = true)
    public MessageList messages(long userId, String conversationId,
                                int requestedLimit, Long beforeId) {
        String id = uuid(conversationId);
        int limit = pageSize(requestedLimit);
        if (beforeId != null && beforeId <= 0) throw bad("beforeId must be positive");
        requireActive(userId, id, false);

        String sql = """
                SELECT id,role,content,created_at FROM agent_messages
                WHERE conversation_id=?
                """ + (beforeId == null ? "" : " AND id < ?")
                + " ORDER BY id DESC LIMIT ?";
        List<MessageRow> rows = beforeId == null
                ? jdbc.query(sql, MESSAGE_MAPPER, id, limit + 1)
                : jdbc.query(sql, MESSAGE_MAPPER, id, beforeId, limit + 1);
        boolean more = rows.size() > limit;
        if (more) rows = new ArrayList<>(rows.subList(0, limit));
        Collections.reverse(rows);
        Long nextBeforeId = more ? rows.get(0).id() : null;
        return new MessageList(id, rows.stream().map(MessageRow::view).toList(), nextBeforeId);
    }

    /**
     * Write only the textual assistant reply derived by the trusted Agent.
     * The referenced USER request must exist in the SAME owned conversation.
     * A row lock makes same-key retries idempotent. No workflow is re-executed.
     */
    @Transactional
    public WriteResult appendAssistantMessage(long userId, String conversationId,
            String rawContent, String rawRequestId, String rawUserRequestId,
            String rawUserContent) {
        String id = uuid(conversationId);
        String key = requestId(rawRequestId);
        String sourceKey = requestId(rawUserRequestId);
        String content = safeMessage(rawContent);

        requireActive(userId, id, true);
        MessageRow original = findMessage(id, sourceKey);
        if (original == null || !"USER".equals(original.role())
                || !original.content().equals(safeMessage(rawUserContent))) {
            throw new ResponseStatusException(HttpStatus.CONFLICT,
                    "Referenced user message is absent or does not match the request");
        }
        MessageRow previous = findMessage(id, key);
        if (previous != null) {
            if (!"ASSISTANT".equals(previous.role())
                    || !content.equals(previous.content())) {
                throw new ResponseStatusException(HttpStatus.CONFLICT,
                        "requestId already used for different assistant content");
            }
            return new WriteResult(previous.view(), false);
        }
        LocalDateTime now = nowUtc();
        Timestamp ts = Timestamp.valueOf(now);
        jdbc.update("""
                INSERT INTO agent_messages
                  (conversation_id,role,content,request_id,created_at)
                VALUES (?,'ASSISTANT',?,?,?)
                """, id, content, key, ts);
        jdbc.update("""
                UPDATE agent_conversations SET updated_at=?
                WHERE id=? AND user_id=? AND status='ACTIVE'
                """, ts, id, userId);
        MessageRow created = findMessage(id, key);
        if (created == null) {
            throw new IllegalStateException("Stored assistant message cannot be read back");
        }
        return new WriteResult(created.view(), true);
    }

    /**
     * D5: verify the stored USER message before registering a workflow.
     * Must join the caller's transaction so the conversation row stays locked
     * until the workflow session INSERT succeeds or rolls back.
     * No new messages are written and no bank actions are performed here.
     */
    @Transactional(propagation = org.springframework.transaction.annotation.Propagation.MANDATORY)
    public String requireWorkflowSource(long userId, String conversationId,
                                        String rawRequestId, String rawContent) {
        String id = uuid(conversationId);
        String key = requestId(rawRequestId);
        String content = safeMessage(rawContent);
        requireActive(userId, id, true);
        MessageRow original = findMessage(id, key);
        if (original == null || !"USER".equals(original.role())
                || !content.equals(original.content())) {
            throw new ResponseStatusException(HttpStatus.CONFLICT,
                    "Referenced user message is absent or does not match the request");
        }
        return id;
    }

    @Transactional
    public WriteResult appendUserMessage(long userId, String conversationId,
                                         String rawContent, String rawRequestId) {
        String id = uuid(conversationId);
        String key = requestId(rawRequestId);
        String content = safeMessage(rawContent);

        // The conversation row is locked to serialize inserts of one requestId.
        // A concurrent retry cannot race the idempotency check.
        requireActive(userId, id, true);
        MessageRow previous = findMessage(id, key);
        if (previous != null) {
            if (!"USER".equals(previous.role()) || !content.equals(previous.content())) {
                throw new ResponseStatusException(HttpStatus.CONFLICT,
                        "requestId already used for different message content");
            }
            return new WriteResult(previous.view(), false);
        }

        LocalDateTime now = nowUtc();
        Timestamp ts = Timestamp.valueOf(now);
        jdbc.update("""
                INSERT INTO agent_messages
                  (conversation_id,role,content,request_id,created_at)
                VALUES (?,'USER',?,?,?)
                """, id, content, key, ts);
        jdbc.update("""
                UPDATE agent_conversations SET updated_at=?
                WHERE id=? AND user_id=? AND status='ACTIVE'
                """, ts, id, userId);
        MessageRow created = findMessage(id, key);
        if (created == null) throw new IllegalStateException("Stored message could not be read back");
        return new WriteResult(created.view(), true);
    }
}
