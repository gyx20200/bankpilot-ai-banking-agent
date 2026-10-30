package com.bankpilot.demo;

import java.math.BigDecimal;
import java.sql.Statement;
import java.sql.Timestamp;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class TransferPrepareService {
    private static final BigDecimal LIMIT = new BigDecimal("1000.00");
    private static final BigDecimal MAX_AMOUNT = new BigDecimal("1000000.00");
    private static final ZoneId BUSINESS_ZONE = ZoneId.of("Asia/Shanghai");
    private final JdbcTemplate jdbc;

    record Sender(long accountId, BigDecimal balance) { }
    record Payee(long id, String name, long receiverAccountId, String accountMasked) { }

    public TransferPrepareService(JdbcTemplate jdbc) { this.jdbc = jdbc; }

    @Transactional
    public TransferPrepareController.OrderView prepare(long userId, TransferPrepareController.PrepareRequest req) {
        if (req == null || req.payeeId() == null || req.payeeId() <= 0) bad("payeeId is required");
        if (req.requestId() == null || !req.requestId().matches("[A-Za-z0-9_-]{8,64}")) bad("Invalid requestId");
        String remark = req.remark() == null ? "" : req.remark();
        if (remark.length() > 80) bad("Remark too long");
        BigDecimal amount = checkedAmount(req.amount());

        // Serialize same-user prepares, including risk accumulation and duplicate checks.
        var users = jdbc.query("SELECT id FROM users WHERE id = ? FOR UPDATE",
            (rs, rowNum) -> rs.getLong("id"), userId);
        if (users.isEmpty()) throw new ResponseStatusException(HttpStatus.NOT_FOUND, "User not found");

        var previous = jdbc.query("""
            SELECT o.id, o.payee_id, o.amount, o.remark, o.risk_level, o.status,
                   p.payee_name, a.account_no
            FROM transfer_orders o
            JOIN payees p ON p.id=o.payee_id
            JOIN accounts a ON a.id=o.receiver_account_id
            WHERE o.user_id=? AND o.request_id=?
            """, (rs, rowNum) -> new Existing(
                rs.getLong("id"), rs.getLong("payee_id"), rs.getBigDecimal("amount"),
                rs.getString("remark"), rs.getString("risk_level"), rs.getString("status"),
                rs.getString("payee_name"), AccountMasker.mask(rs.getString("account_no"))
            ), userId, req.requestId());
        if (!previous.isEmpty()) {
            var e = previous.get(0);
            if (e.payeeId() != req.payeeId() || e.amount().compareTo(amount) != 0 || !e.remark().equals(remark)) {
                throw new ResponseStatusException(HttpStatus.CONFLICT, "requestId already used with different parameters");
            }
            return new TransferPrepareController.OrderView(e.id(), e.name(), e.accountMasked(),
                e.amount(), e.riskLevel(), e.status(), e.remark());
        }

        var senders = jdbc.query("""
            SELECT id, balance FROM accounts
            WHERE user_id=? AND status='ACTIVE'
            ORDER BY id ASC LIMIT 1
            """, (rs, rowNum) -> new Sender(rs.getLong("id"), rs.getBigDecimal("balance")), userId);
        if (senders.isEmpty()) throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Sender account not found");
        var sender = senders.get(0);
        if (sender.balance().compareTo(amount) < 0) {
            throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_ENTITY, "Insufficient funds");
        }

        var payees = jdbc.query("""
            SELECT p.id, p.payee_name, p.payee_account_id, a.account_no
            FROM payees p JOIN accounts a ON a.id=p.payee_account_id
            WHERE p.id=? AND p.user_id=? AND a.status='ACTIVE'
            """, (rs, rowNum) -> new Payee(rs.getLong("id"), rs.getString("payee_name"),
                rs.getLong("payee_account_id"), AccountMasker.mask(rs.getString("account_no"))),
            req.payeeId(), userId);
        if (payees.isEmpty()) throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Payee not found for current user");
        var payee = payees.get(0);
        if (payee.receiverAccountId() == sender.accountId()) bad("Cannot transfer to self");

        LocalDate day = LocalDate.now(BUSINESS_ZONE);
        LocalDateTime start = day.atStartOfDay();
        LocalDateTime end = day.plusDays(1).atStartOfDay();
        BigDecimal used = jdbc.queryForObject("""
            SELECT COALESCE(SUM(amount),0) FROM transfer_orders
            WHERE user_id=? AND created_at>=? AND created_at<?
              AND status IN ('PENDING_APPROVAL','AUTHORIZED','EXECUTING','SUCCESS','UNKNOWN')
            """, BigDecimal.class, userId, Timestamp.valueOf(start), Timestamp.valueOf(end));
        String risk = (used == null ? BigDecimal.ZERO : used).add(amount).compareTo(LIMIT) > 0 ? "RED" : "YELLOW";
        LocalDateTime now = LocalDateTime.now(BUSINESS_ZONE);

        var key = new GeneratedKeyHolder();
        jdbc.update(con -> {
            var statement = con.prepareStatement("""
                INSERT INTO transfer_orders
                (user_id,sender_account_id,payee_id,receiver_account_id,amount,remark,
                 request_id,risk_level,status,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """, Statement.RETURN_GENERATED_KEYS);
            statement.setLong(1, userId);
            statement.setLong(2, sender.accountId());
            statement.setLong(3, payee.id());
            statement.setLong(4, payee.receiverAccountId());
            statement.setBigDecimal(5, amount);
            statement.setString(6, remark);
            statement.setString(7, req.requestId());
            statement.setString(8, risk);
            statement.setString(9, "PENDING_APPROVAL");
            statement.setTimestamp(10, Timestamp.valueOf(now));
            statement.setTimestamp(11, Timestamp.valueOf(now));
            return statement;
        }, key);
        if (key.getKey() == null) throw new IllegalStateException("Order generated ID is missing");
        jdbc.update("INSERT INTO audit_events(user_id,order_id,action,result,created_at) VALUES (?,?,?,?,?)",
            userId, key.getKey().longValue(), "TRANSFER_PREPARE", "PENDING_APPROVAL", Timestamp.valueOf(now));
        return new TransferPrepareController.OrderView(key.getKey().longValue(), payee.name(), payee.accountMasked(),
            amount, risk, "PENDING_APPROVAL", remark);
    }

    private record Existing(long id, long payeeId, BigDecimal amount, String remark,
                            String riskLevel, String status, String name, String accountMasked) { }

    private static BigDecimal checkedAmount(String raw) {
        if (raw == null || !raw.matches("(?:0|[1-9][0-9]{0,8})(?:\\.[0-9]{1,2})?")) {
            throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_ENTITY, "Invalid amount format");
        }
        BigDecimal value = new BigDecimal(raw);
        if (value.compareTo(BigDecimal.ZERO) <= 0 || value.compareTo(MAX_AMOUNT) > 0) {
            throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_ENTITY, "Amount out of demo range");
        }
        return value.setScale(2);
    }

    private static void bad(String reason) {
        throw new ResponseStatusException(HttpStatus.BAD_REQUEST, reason);
    }
}
