package com.bankpilot.demo;

import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.UUID;
import java.util.regex.Pattern;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

/**
 * D6: durable, at-most-one recovery approval claim for a D5 workflow.
 *
 * Only a trusted FastAPI caller (controller checks BOTH user Bearer and internal
 * service key) may claim. Checkpoints and bank-order verification are done by
 * Python before claiming. Java serializes claims and tracks final outcomes.
 * A CLAIMED or NOT_CONFIRMED attempt is NEVER an invitation to auto-replay.
 */
@Service
public class WorkflowRecoveryService {
    private static final Pattern CHECKPOINT_ID = Pattern.compile("[A-Za-z0-9_-]{8,128}");
    private static final String FIELDS = "thread_id,user_id,action_id,checkpoint_id,approved,status,created_at,finalized_at";
    private final JdbcTemplate jdbc;
    private final WorkflowSessionService registry;

    public WorkflowRecoveryService(JdbcTemplate jdbc, WorkflowSessionService registry) {
        this.jdbc = jdbc;
        this.registry = registry;
    }

    public record ClaimView(String threadId, String actionId, String checkpointId,
                            boolean approved, String status, String createdAt,
                            String finalizedAt) { }

    private record ClaimRow(String threadId, long userId, String actionId,
                            String checkpointId, boolean approved, String status,
                            LocalDateTime createdAt, LocalDateTime finalizedAt) {
        ClaimView view() {
            return new ClaimView(threadId, actionId, checkpointId, approved, status,
                    utc(createdAt), finalizedAt == null ? null : utc(finalizedAt));
        }
    }

    private static final RowMapper<ClaimRow> MAPPER = (rs, i) -> new ClaimRow(
            rs.getString("thread_id"), rs.getLong("user_id"), rs.getString("action_id"),
            rs.getString("checkpoint_id"), rs.getBoolean("approved"), rs.getString("status"),
            rs.getObject("created_at", LocalDateTime.class),
            rs.getObject("finalized_at", LocalDateTime.class));

    private static String uuid(String value) {
        if (value == null || value.length() != 36) throw bad("Invalid UUID");
        try {
            String canonical = UUID.fromString(value).toString();
            if (!canonical.equalsIgnoreCase(value)) throw bad("Invalid UUID");
            return canonical;
        } catch (IllegalArgumentException exc) {
            throw bad("Invalid UUID");
        }
    }

    private static String checkpoint(String value) {
        if (value == null || !CHECKPOINT_ID.matcher(value).matches()) {
            throw bad("Invalid checkpoint ID");
        }
        return value;
    }

    private static LocalDateTime nowUtc() {
        return LocalDateTime.now(ZoneOffset.UTC).truncatedTo(ChronoUnit.MICROS);
    }

    private static String utc(LocalDateTime value) {
        return value.toInstant(ZoneOffset.UTC).toString();
    }

    private static ResponseStatusException bad(String message) {
        return new ResponseStatusException(HttpStatus.BAD_REQUEST, message);
    }

    private static ResponseStatusException conflict(String message) {
        return new ResponseStatusException(HttpStatus.CONFLICT, message);
    }

    private ClaimRow owned(long userId, String thread, boolean lock) {
        String sql = "SELECT " + FIELDS + " FROM agent_workflow_recovery_claims "
                + "WHERE thread_id=? AND user_id=?" + (lock ? " FOR UPDATE" : "");
        List<ClaimRow> found = jdbc.query(sql, MAPPER, thread, userId);
        if (found.isEmpty()) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Recovery claim not found");
        }
        return found.get(0);
    }

    /** Java ownership lookup also checks that the originating conversation is ACTIVE. */
    @Transactional(readOnly = true)
    public ClaimView get(long userId, String rawThreadId) {
        String thread = uuid(rawThreadId);
        registry.get(userId, thread);
        return owned(userId, thread, false).view();
    }

    /** Atomically allow at most ONE post-restart approval/rejection for a thread. */
    @Transactional
    public ClaimView claim(long userId, String rawThreadId, String rawActionId,
                           String rawCheckpointId, boolean approved) {
        String thread = uuid(rawThreadId);
        String actionId = uuid(rawActionId);
        String checkpointId = checkpoint(rawCheckpointId);

        var session = registry.get(userId, thread);
        if (!"WAITING".equals(session.status())) {
            throw conflict("Workflow is not waiting for human confirmation");
        }
        if (session.sourceRequestId() == null || session.sourceRequestId().isBlank()) {
            throw conflict("Legacy workflow source is not verified");
        }
        LocalDateTime now = nowUtc();
        if (!Instant.parse(session.expiresAt()).isAfter(now.toInstant(ZoneOffset.UTC))) {
            throw new ResponseStatusException(HttpStatus.GONE, "Workflow approval has expired");
        }

        // Serialize all recovery claims against the D5 session row in MySQL.
        List<String> waiting = jdbc.queryForList("""
                SELECT thread_id FROM agent_workflow_sessions
                WHERE thread_id=? AND user_id=? AND status='WAITING' AND expires_at > ?
                FOR UPDATE
                """, String.class, thread, userId, now);
        if (waiting.isEmpty()) {
            throw conflict("Workflow changed while starting recovery");
        }
        try {
            jdbc.update("""
                    INSERT INTO agent_workflow_recovery_claims
                      (thread_id,user_id,action_id,checkpoint_id,approved,status,created_at)
                    VALUES (?,?,?,?,?,'CLAIMED',?)
                    """, thread, userId, actionId, checkpointId, approved, now);
        } catch (DuplicateKeyException exc) {
            // Do not return a successful replay. Python must NOT invoke Graph twice.
            throw conflict("Recovery already claimed. Inspect the original order; do not retry");
        }
        return owned(userId, thread, false).view();
    }

    /**
     * Record only a VERIFIED business outcome, or NOT_CONFIRMED if uncertain.
     * This single MySQL transaction updates both the claim and D5 lifecycle.
     * Even an expired workflow can finalize an action already claimed earlier.
     */
    @Transactional
    public ClaimView finalizeClaim(long userId, String rawThreadId, String status) {
        String thread = uuid(rawThreadId);
        if (!List.of("COMPLETED", "REJECTED", "NOT_CONFIRMED").contains(status)) {
            throw bad("Invalid final recovery status");
        }
        registry.get(userId, thread);
        // Match claim() lock ordering: workflow session first, recovery claim second.
        jdbc.queryForList("SELECT thread_id FROM agent_workflow_sessions "
                + "WHERE thread_id=? AND user_id=? FOR UPDATE", String.class, thread, userId);
        ClaimRow current = owned(userId, thread, true);
        if (status.equals(current.status())) return current.view();
        if (!"CLAIMED".equals(current.status())) {
            throw conflict("Recovery claim is already finalized; do not change outcome");
        }
        if (current.approved() && "REJECTED".equals(status)
                || !current.approved() && "COMPLETED".equals(status)) {
            throw conflict("Recovered outcome conflicts with recorded human decision");
        }
        int updatedSession = jdbc.update("""
                UPDATE agent_workflow_sessions SET status=?
                WHERE thread_id=? AND user_id=? AND status IN ('RUNNING','WAITING')
                """, status, thread, userId);
        if (updatedSession != 1) {
            throw conflict("Workflow lifecycle is inconsistent with recovery claim");
        }
        int updatedClaim = jdbc.update("""
                UPDATE agent_workflow_recovery_claims SET status=?,finalized_at=?
                WHERE thread_id=? AND user_id=? AND status='CLAIMED'
                """, status, nowUtc(), thread, userId);
        if (updatedClaim != 1) throw conflict("Recovery outcome changed concurrently");
        return owned(userId, thread, false).view();
    }
}
