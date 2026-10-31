package com.bankpilot.demo;

import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

import java.util.List;

@Service
public class Day7RecipientService {
    private final JdbcTemplate jdbc;
    public Day7RecipientService(JdbcTemplate jdbc) {this.jdbc = jdbc;}

    // candidateId = bank-verified registered user id; never an account number or LLM-generated payeeId.
    public record Candidate(long recipientId, String payeeName, String accountMasked) {}
    public record Confirmed(long id, String payeeName, String payeeAccountMasked) {}

    public List<Candidate> resolve(long me, Day7RecipientController.ResolveRequest body) {
        if (body == null || body.lookupType() == null || body.query() == null) bad("lookupType and query required");
        if ("NAME".equals(body.lookupType())) {
            if (body.query().isBlank() || body.query().length() > 80) bad("Invalid name");
            return query(me, "u.display_name=?", body.query().trim());
        }
        if ("PHONE".equals(body.lookupType())) {
            if (!body.query().matches("1[3-9][0-9]{9}")) bad("Complete 11-digit phone required");
            return query(me, "u.phone=?", body.query());
        }
        bad("lookupType must be NAME or PHONE");
        return List.of();
    }

    private List<Candidate> query(long me, String predicate, String value) {
        return jdbc.query("""
            SELECT u.id, u.display_name, a.account_no
            FROM users u JOIN accounts a ON a.user_id=u.id
            WHERE u.id<>? AND u.status='ACTIVE' AND a.status='ACTIVE' AND
            """ + predicate + " ORDER BY u.id LIMIT 30",
            (rs, n) -> new Candidate(rs.getLong(1), rs.getString(2), AccountMasker.mask(rs.getString(3))),
            me, value);
    }

    @Transactional
    public Confirmed confirm(long me, Day7RecipientController.ConfirmRequest body) {
        if (body == null || body.recipientId() == null || body.recipientId() <= 0 || body.recipientId() == me)
            bad("Invalid recipient selection");
        return ensurePayee(me, body.recipientId());
    }

    /** Used by AA payment preparation after authenticated payer explicitly requested payment. */
    @Transactional
    public Confirmed ensurePayee(long payer, long targetUser) {
        if (payer == targetUser) bad("Cannot pay yourself");
        var recipients = jdbc.query("""
            SELECT u.display_name, a.id, a.account_no FROM users u JOIN accounts a ON a.user_id=u.id
            WHERE u.id=? AND u.status='ACTIVE' AND a.status='ACTIVE'
            ORDER BY a.id LIMIT 2
            """, (rs, n) -> new Target(rs.getString(1), rs.getLong(2), rs.getString(3)), targetUser);
        if (recipients.size() != 1) throw new ResponseStatusException(HttpStatus.CONFLICT,
            "Recipient has no unique active account");
        Target target = recipients.get(0);
        jdbc.update("""
            INSERT INTO payees(user_id,payee_account_id,payee_name) VALUES (?,?,?)
            ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id)
            """, payer, target.accountId(), target.name());
        Long payeeId = jdbc.queryForObject("SELECT LAST_INSERT_ID()", Long.class);
        if (payeeId == null || payeeId <= 0) throw new IllegalStateException("Payee id not created");
        return new Confirmed(payeeId, target.name(), AccountMasker.mask(target.accountNo()));
    }
    private record Target(String name, long accountId, String accountNo) {}
    private static void bad(String reason) {throw new ResponseStatusException(HttpStatus.BAD_REQUEST, reason);}
}
