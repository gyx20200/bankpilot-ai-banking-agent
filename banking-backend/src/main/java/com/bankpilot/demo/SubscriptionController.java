package com.bankpilot.demo;

import java.math.BigDecimal;
import java.sql.Date;
import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/demo")
public class SubscriptionController {
    private final JdbcTemplate jdbc;

    public SubscriptionController(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public record SubscriptionView(long id, String merchantName, BigDecimal amount,
                                   String billingCycle, String status, String nextPayDate) { }

    @GetMapping("/subscriptions")
    public List<SubscriptionView> listSubscriptions() {
        String sql = """
            SELECT id, merchant_name, amount, billing_cycle, status, next_pay_date
            FROM subscriptions
            WHERE user_id = ?
            ORDER BY id ASC
            LIMIT 100
            """;
        return jdbc.query(sql, (rs, rowNum) -> {
            Date date = rs.getDate("next_pay_date");
            return new SubscriptionView(
                rs.getLong("id"), rs.getString("merchant_name"),
                rs.getBigDecimal("amount"), rs.getString("billing_cycle"),
                rs.getString("status"), date == null ? null : date.toLocalDate().toString()
            );
        }, AuthenticatedUser.id());
    }
}
