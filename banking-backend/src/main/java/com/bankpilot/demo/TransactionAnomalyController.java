package com.bankpilot.demo;

import java.math.BigDecimal;
import java.time.DateTimeException;
import java.time.Duration;
import java.time.LocalDateTime;
import java.time.YearMonth;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

/** D4: explainable demo rules, never a fraud verdict or a bank mutation. */
@RestController
@RequestMapping("/api/demo/analytics")
public class TransactionAnomalyController {
    private static final BigDecimal LARGE = new BigDecimal("1000.00");
    private static final Duration WINDOW = Duration.ofMinutes(10);
    private static final int MAX_SCAN = 10_000;
    private final JdbcTemplate jdbc;

    public TransactionAnomalyController(JdbcTemplate jdbc) { this.jdbc = jdbc; }

    record Tx(long id, long accountId, BigDecimal amount, String category,
              String merchantName, LocalDateTime occurredAt) {}
    private record Key(long accountId, String merchant, BigDecimal amount) {}
    public record Event(long transactionId, String ruleCode, BigDecimal amount,
                        String category, String merchantName, String occurredAt,
                        Long relatedTransactionId, String reason) {}
    public record AnomalyReport(String month, String currency, int scannedCount,
        int anomalyCount, List<Event> items, BigDecimal largeOutflowThreshold,
        long duplicateWindowMinutes, String source, String periodStart,
        String periodEndExclusive) {}

    @GetMapping("/anomalies")
    public AnomalyReport anomalies(@RequestParam String month) {
        long userId = AuthenticatedUser.id();
        if (month == null || !month.matches("[0-9]{4}-(0[1-9]|1[0-2])"))
            throw bad("month must be YYYY-MM");
        YearMonth period;
        try { period = YearMonth.parse(month); }
        catch (DateTimeException e) { throw bad("invalid month"); }
        LocalDateTime now = jdbc.queryForObject("SELECT CURRENT_TIMESTAMP", LocalDateTime.class);
        if (now == null) throw new IllegalStateException("Database clock unavailable");
        if (period.getYear()<1000 || period.isAfter(YearMonth.from(now)))
            throw bad("month is outside supported history");
        LocalDateTime start = period.atDay(1).atStartOfDay();
        LocalDateTime end = period.equals(YearMonth.from(now)) ? now
            : period.plusMonths(1).atDay(1).atStartOfDay();
        String sql = """
            SELECT t.id, t.account_id, t.amount, t.category, t.merchant_name, t.occurred_at
            FROM transactions t JOIN accounts a ON a.id=t.account_id
            WHERE a.user_id=? AND a.status='ACTIVE' AND t.direction='OUT'
              AND t.occurred_at>=? AND t.occurred_at<?
            ORDER BY t.occurred_at, t.id LIMIT ?
            """;
        List<Tx> rows = jdbc.query(sql, (rs,n) -> new Tx(rs.getLong("id"),
            rs.getLong("account_id"), rs.getBigDecimal("amount"), rs.getString("category"),
            rs.getString("merchant_name"), rs.getObject("occurred_at",LocalDateTime.class)),
            userId, start, end, MAX_SCAN+1);
        if (rows.size()>MAX_SCAN) throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_ENTITY,
            "Monthly scan exceeds 10000 outflows; analysis not completed");
        List<Event> events = detect(rows);
        return new AnomalyReport(month,"CNY",rows.size(),events.size(),events,LARGE,
            WINDOW.toMinutes(),"mysql",start.toString(),end.toString());
    }

    // Input is already filtered and sorted by (occurred_at,id). For each key,
    // the nearest preceding transaction suffices to detect a <=10 min pair.
    // Each later transaction emits at most one POSSIBLE_DUPLICATE event.
    static List<Event> detect(List<Tx> rows) {
        List<Event> events = new ArrayList<>();
        Map<Key,Tx> previous = new HashMap<>();
        for (Tx t : rows) {
            if (t.amount().compareTo(LARGE)>=0) events.add(event(t,"LARGE_OUTFLOW",null,
                "单笔支出达到模拟大额检测阈值1000元，建议核对用途。"));
            if (t.merchantName()==null || t.merchantName().isBlank()) continue;
            Key key = new Key(t.accountId(),t.merchantName().strip().toLowerCase(Locale.ROOT),
                t.amount().stripTrailingZeros());
            Tx prior = previous.put(key,t);
            if (prior!=null) {
                Duration diff=Duration.between(prior.occurredAt(),t.occurredAt());
                if (!diff.isNegative() && diff.compareTo(WINDOW)<=0) {
                    events.add(event(t,"POSSIBLE_DUPLICATE",prior.id(),
                        "同一账户、同一商户、相同金额的支出间隔不超过10分钟，建议核实。"));
                }
            }
        }
        return List.copyOf(events);
    }

    private static Event event(Tx t,String rule,Long related,String reason) {
        return new Event(t.id(),rule,t.amount(),t.category(),t.merchantName(),
            t.occurredAt().toString(),related,reason);
    }
    private static ResponseStatusException bad(String reason) {
        return new ResponseStatusException(HttpStatus.BAD_REQUEST, reason);
    }
}
