package com.bankpilot.demo;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

/**
 * D5: authoritative ownership and lifecycle registry for LangGraph threads.
 * Required migration: database/13_workflow_session_persistence.sql.
 * Graph checkpoints live in SQLite, not in this table. No banking writes,
 * approval credentials, bearer tokens or graph payloads are persisted here.
 */
@Service
public class WorkflowSessionService {
    private static final int MAX_PAGE = 100;
    private static final int SESSION_TTL_MINUTES = 30;
    private static final Set<String> STATUSES = Set.of(
            "RUNNING", "WAITING", "COMPLETED", "REJECTED", "ENDED", "NOT_CONFIRMED");
    private static final Set<String> TERMINAL = Set.of(
            "COMPLETED", "REJECTED", "ENDED", "NOT_CONFIRMED");
    private static final String COLUMNS = "thread_id, conversation_id, source_request_id, "
            + "status, created_at, expires_at";

    private final JdbcTemplate jdbc;
    private final ConversationService conversations;
    private final String agentInternalKey;

    public WorkflowSessionService(JdbcTemplate jdbc, ConversationService conversations,
            @Value("${BANKPILOT_AGENT_INTERNAL_KEY:}") String agentInternalKey) {
        this.jdbc = jdbc;
        this.conversations = conversations;
        this.agentInternalKey = agentInternalKey;
    }

    /** Exact D5 wire contract, timestamps are UTC ISO-8601 strings. */
    public record SessionView(String threadId, String conversationId,
                              String sourceRequestId, String status,
                              String createdAt, String expiresAt) { }

    public record SessionList(List<SessionView> items) { }

    private record SessionRow(String threadId, String conversationId,
                              String sourceRequestId, String status,
                              LocalDateTime createdAt, LocalDateTime expiresAt) {
        SessionView view() {
            return new SessionView(threadId, conversationId, sourceRequestId,
                    status, utc(createdAt), utc(expiresAt));
        }
    }

    private static final RowMapper<SessionRow> MAPPER = (rs, i) -> new SessionRow(
            rs.getString("thread_id"), rs.getString("conversation_id"),
            rs.getString("source_request_id"), rs.getString("status"),
            rs.getObject("created_at", LocalDateTime.class),
            rs.getObject("expires_at", LocalDateTime.class));

    public void requireTrustedAgent(String supplied) {
        byte[] expected = agentInternalKey == null ? new byte[0]
                : agentInternalKey.getBytes(StandardCharsets.UTF_8);
        if (expected.length < 32 || agentInternalKey.isBlank()) {
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,
                    "Agent workflow registry is not configured");
        }
        byte[] actual = supplied == null ? new byte[0]
                : supplied.getBytes(StandardCharsets.UTF_8);
        if (!MessageDigest.isEqual(expected, actual)) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN,
                    "Trusted Agent credentials required");
        }
    }

    /** First register in MySQL, then (and only then) Python may start the graph. */
    @Transactional
    public SessionView register(long userId, String rawThreadId, String conversationId,
                                String sourceRequestId, String userMessageContent) {
        String threadId = canonicalUuid(rawThreadId, "threadId");
        // Joins this transaction and locks the owned ACTIVE conversation.
        // Reuses the precise D3 requestId/content validation and masking rules.
        String id = conversations.requireWorkflowSource(userId, conversationId,
                sourceRequestId, userMessageContent);

        LocalDateTime now = nowUtc();
        LocalDateTime expires = now.plusMinutes(SESSION_TTL_MINUTES);
        try {
            jdbc.update("""
                    INSERT INTO agent_workflow_sessions
                      (thread_id, conversation_id, source_request_id, user_id,
                       status, created_at, expires_at)
                    VALUES (?, ?, ?, ?, 'RUNNING', ?, ?)
                    """, threadId, id, sourceRequestId, userId, now, expires);
        } catch (DuplicateKeyException ex) {
            // Do not treat retry as a successful registration: a 201 replay
            // could cause Python to launch the same banking action twice.
            throw conflict("Workflow already registered for this thread or user message; "
                    + "inspect the existing session instead of starting another");
        }
        return loadOwned(userId, threadId, false).view();
    }

    @Transactional(readOnly = true)
    public SessionView get(long userId, String rawThreadId) {
        String threadId = canonicalUuid(rawThreadId, "threadId");
        SessionRow row = loadOwned(userId, threadId, false);
        // D3 only exposes ACTIVE conversations; keep the same rule for D5.
        conversations.get(userId, row.conversationId());
        // Expired tasks remain readable. Python must compare expiresAt to UTC.
        return row.view();
    }

    @Transactional(readOnly = true)
    public SessionList list(long userId, String rawConversationId, int limit) {
        if (limit < 1 || limit > MAX_PAGE) {
            throw bad("limit must be 1..100");
        }
        String id = conversations.get(userId, rawConversationId).conversationId();
        List<SessionRow> rows = jdbc.query("SELECT " + COLUMNS + " " + """
                 FROM agent_workflow_sessions
                 WHERE conversation_id=? AND user_id=?
                 ORDER BY created_at DESC, thread_id DESC LIMIT ?
                """, MAPPER, id, userId, limit);
        return new SessionList(rows.stream().map(SessionRow::view).toList());
    }

    @Transactional
    public SessionView updateStatus(long userId, String rawThreadId, String status) {
        String threadId = canonicalUuid(rawThreadId, "threadId");
        if (status == null || !STATUSES.contains(status)) {
            throw bad("Invalid workflow lifecycle status");
        }
        // Serialize concurrent writes to this session row.
        SessionRow current = loadOwned(userId, threadId, true);
        conversations.get(userId, current.conversationId());

        // A repeated status write is a read-like no-op, even after expiry.
        if (current.status().equals(status)) {
            return current.view();
        }
        if (!nowUtc().isBefore(current.expiresAt())) {
            throw new ResponseStatusException(HttpStatus.GONE,
                    "Workflow session expired; inspect the original bank order");
        }
        if (!canTransition(current.status(), status)) {
            throw conflict("Invalid workflow lifecycle transition");
        }
        int changed = jdbc.update("""
                UPDATE agent_workflow_sessions SET status=?
                WHERE thread_id=? AND user_id=? AND status=?
                """, status, threadId, userId, current.status());
        if (changed != 1) {
            throw conflict("Workflow lifecycle changed concurrently");
        }
        return loadOwned(userId, threadId, false).view();
    }

    /** D5 freezes terminal/uncertain states; D6 adds verified reconciliation. */
    static boolean canTransition(String from, String to) {
        if (from == null || to == null || !STATUSES.contains(from) || !STATUSES.contains(to)) {
            return false;
        }
        if (from.equals(to)) return true;
        if (TERMINAL.contains(from)) return false;
        // Both RUNNING and WAITING may complete or end. A WAITING task can
        // return to RUNNING only at the trusted Agent's current-process boundary.
        // This registry alone never grants permission to resume a checkpoint.
        return from.equals("RUNNING") || from.equals("WAITING");
    }

    private SessionRow loadOwned(long userId, String threadId, boolean lock) {
        String sql = "SELECT " + COLUMNS + " FROM agent_workflow_sessions"
                + " WHERE thread_id=? AND user_id=?" + (lock ? " FOR UPDATE" : "");
        List<SessionRow> rows = jdbc.query(sql, MAPPER, threadId, userId);
        if (rows.isEmpty()) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND,
                    "Workflow session not found");
        }
        return rows.get(0);
    }

    private static String canonicalUuid(String value, String field) {
        if (value == null || value.length() != 36) throw bad("Invalid " + field);
        try {
            String canonical = UUID.fromString(value).toString();
            if (!canonical.equalsIgnoreCase(value)) throw bad("Invalid " + field);
            return canonical;
        } catch (IllegalArgumentException ex) {
            throw bad("Invalid " + field);
        }
    }

    private static LocalDateTime nowUtc() {
        return LocalDateTime.now(ZoneOffset.UTC).truncatedTo(ChronoUnit.MICROS);
    }

    private static String utc(LocalDateTime value) {
        return value.toInstant(ZoneOffset.UTC).toString();
    }

    private static ResponseStatusException bad(String reason) {
        return new ResponseStatusException(HttpStatus.BAD_REQUEST, reason);
    }

    private static ResponseStatusException conflict(String reason) {
        return new ResponseStatusException(HttpStatus.CONFLICT, reason);
    }
}
