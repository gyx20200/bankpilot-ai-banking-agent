package com.bankpilot.demo;

import java.math.BigDecimal;
import java.time.format.DateTimeFormatter;
import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/demo")
public class TransactionController {
    private static final DateTimeFormatter TIME_FORMAT = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");
    private final JdbcTemplate jdbc;

    public TransactionController(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public record TransactionView(long id, String direction, BigDecimal amount,
                                  String category, String merchantName,
                                  String description, String occurredAt) { }

    @GetMapping("/transactions")
    public List<TransactionView> listTransactions() {
        String sql = """
            SELECT t.id, t.direction, t.amount, t.category, t.merchant_name,
                   t.description, t.occurred_at
            FROM transactions t
            JOIN accounts a ON a.id = t.account_id
            WHERE a.user_id = ? AND a.status = 'ACTIVE'
            ORDER BY t.occurred_at DESC, t.id DESC
            LIMIT 100
            """;
        return jdbc.query(sql, (rs, rowNum) -> new TransactionView(
            rs.getLong("id"), rs.getString("direction"), rs.getBigDecimal("amount"),
            rs.getString("category"), rs.getString("merchant_name"),
            rs.getString("description"),
            rs.getTimestamp("occurred_at").toLocalDateTime().format(TIME_FORMAT)
        ), AuthenticatedUser.id());
    }
}
