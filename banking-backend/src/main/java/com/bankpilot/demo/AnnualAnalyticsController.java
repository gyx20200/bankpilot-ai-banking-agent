package com.bankpilot.demo;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.time.YearMonth;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

/** D4: read-only annual ledger aggregation, scoped to the authenticated owner. */
@RestController
@RequestMapping("/api/demo/analytics")
public class AnnualAnalyticsController {
    private static final BigDecimal ZERO = new BigDecimal("0.00");
    private final JdbcTemplate jdbc;

    public AnnualAnalyticsController(JdbcTemplate jdbc) { this.jdbc = jdbc; }

    public record CategoryTotal(String name, BigDecimal amount, long count) {}
    public record MonthlyTotal(String month, BigDecimal totalIncome,
                               BigDecimal totalExpense) {}
    public record AnnualReport(String year, String currency, BigDecimal totalIncome,
        BigDecimal totalExpense, BigDecimal netCashFlow, List<CategoryTotal> categories,
        List<MonthlyTotal> monthlyBreakdown, String periodType, String source,
        String periodStart, String periodEndExclusive) {}
    private record Row(int month, String direction, String category,
                       BigDecimal amount, long count) {}
    private record CategorySum(BigDecimal amount, long count) {}

    @GetMapping("/annual")
    public AnnualReport annual(@RequestParam String year) {
        long userId = AuthenticatedUser.id();
        if (year == null || !year.matches("[0-9]{4}")) throw bad("year must be YYYY");
        int y = Integer.parseInt(year);
        // occurred_at is a local DATETIME in MySQL. Use the same DB session clock.
        LocalDateTime now = jdbc.queryForObject("SELECT CURRENT_TIMESTAMP", LocalDateTime.class);
        if (now == null) throw new IllegalStateException("Database clock unavailable");
        if (y < 1000 || y > now.getYear()) throw bad("year is outside supported history");
        LocalDateTime start = LocalDateTime.of(y, 1, 1, 0, 0);
        boolean ytd = y == now.getYear();
        LocalDateTime end = ytd ? now : start.plusYears(1);
        int monthCount = ytd ? now.getMonthValue() : 12;

        String sql = """
            SELECT MONTH(t.occurred_at) AS tx_month, t.direction, t.category,
                   SUM(t.amount) AS total_amount, COUNT(*) AS tx_count
            FROM transactions t JOIN accounts a ON a.id=t.account_id
            WHERE a.user_id=? AND a.status='ACTIVE'
              AND t.occurred_at>=? AND t.occurred_at<?
            GROUP BY MONTH(t.occurred_at), t.direction, t.category
            ORDER BY tx_month, t.direction, t.category
            """;
        List<Row> rows = jdbc.query(sql, (rs, n) -> new Row(rs.getInt("tx_month"),
            rs.getString("direction"), rs.getString("category"),
            rs.getBigDecimal("total_amount"), rs.getLong("tx_count")), userId, start, end);
        BigDecimal[] income = new BigDecimal[monthCount];
        BigDecimal[] expense = new BigDecimal[monthCount];
        java.util.Arrays.fill(income, ZERO);
        java.util.Arrays.fill(expense, ZERO);
        Map<String, CategorySum> categories = new TreeMap<>();
        for (Row r : rows) {
            int i = r.month() - 1;
            if ("IN".equals(r.direction())) income[i] = income[i].add(r.amount());
            else if ("OUT".equals(r.direction())) {
                expense[i] = expense[i].add(r.amount());
                categories.merge(r.category(), new CategorySum(r.amount(), r.count()),
                    (a, b) -> new CategorySum(a.amount().add(b.amount()), a.count()+b.count()));
            }
        }
        List<MonthlyTotal> monthly = new ArrayList<>();
        BigDecimal in = ZERO, out = ZERO;
        for (int i=0; i<monthCount; i++) {
            in = in.add(income[i]); out = out.add(expense[i]);
            monthly.add(new MonthlyTotal(YearMonth.of(y,i+1).toString(), income[i], expense[i]));
        }
        List<CategoryTotal> totals = categories.entrySet().stream()
            .map(e -> new CategoryTotal(e.getKey(), e.getValue().amount(), e.getValue().count()))
            .toList();
        return new AnnualReport(year, "CNY", in, out, in.subtract(out), totals,
            List.copyOf(monthly), ytd ? "YEAR_TO_DATE" : "FULL_YEAR", "mysql",
            start.toString(), end.toString());
    }

    private static ResponseStatusException bad(String reason) {
        return new ResponseStatusException(HttpStatus.BAD_REQUEST, reason);
    }
}
