package com.bankpilot.demo;

import java.math.BigDecimal;
import java.sql.Timestamp;
import java.time.DateTimeException;
import java.time.LocalDateTime;
import java.time.YearMonth;
import java.util.ArrayList;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

/** Deterministic SQL analytics; the LLM must never invent or sum banking amounts. */
@RestController
@RequestMapping("/api/demo/analytics")
public class MonthlyAnalyticsController {
    private final JdbcTemplate jdbc;

    public MonthlyAnalyticsController(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public record CategoryTotal(String name, BigDecimal amount, long count) { }
    public record MonthlyReport(String month, String currency, BigDecimal totalIncome,
                                BigDecimal totalExpense, BigDecimal netCashFlow,
                                List<CategoryTotal> categories, String source) { }

    @GetMapping("/monthly")
    public MonthlyReport monthly(@RequestParam String month) {
        if (month == null || !month.matches("[0-9]{4}-(0[1-9]|1[0-2])")) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "month must be YYYY-MM");
        }
        final YearMonth period;
        try {
            period = YearMonth.parse(month);
        } catch (DateTimeException exc) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "invalid month", exc);
        }
        LocalDateTime start = period.atDay(1).atStartOfDay();
        LocalDateTime end = period.plusMonths(1).atDay(1).atStartOfDay();

        String sql = """
            SELECT t.direction, t.category, SUM(t.amount) AS total_amount, COUNT(*) AS tx_count
            FROM transactions t JOIN accounts a ON a.id = t.account_id
            WHERE a.user_id = ? AND a.status = 'ACTIVE'
              AND t.occurred_at >= ? AND t.occurred_at < ?
            GROUP BY t.direction, t.category
            ORDER BY t.direction, t.category
            """;
        var rows = jdbc.query(sql, (rs, index) -> new Aggregated(
            rs.getString("direction"), rs.getString("category"),
            rs.getBigDecimal("total_amount"), rs.getLong("tx_count")
        ), AuthenticatedUser.id(), Timestamp.valueOf(start), Timestamp.valueOf(end));

        BigDecimal income = BigDecimal.ZERO.setScale(2);
        BigDecimal expense = BigDecimal.ZERO.setScale(2);
        List<CategoryTotal> categories = new ArrayList<>();
        for (var row : rows) {
            if ("IN".equals(row.direction())) {
                income = income.add(row.amount());
            } else if ("OUT".equals(row.direction())) {
                expense = expense.add(row.amount());
                categories.add(new CategoryTotal(row.category(), row.amount(), row.count()));
            }
        }
        return new MonthlyReport(month, "CNY", income, expense, income.subtract(expense),
            List.copyOf(categories), "mysql");
    }

    private record Aggregated(String direction, String category, BigDecimal amount, long count) { }
}
