package com.bankpilot.demo;

import java.math.BigDecimal;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/demo")
public class BalanceController {
    private final JdbcTemplate jdbc;

    public BalanceController(JdbcTemplate jdbc) { this.jdbc = jdbc; }

    // WARNING: fixed demo identity. Read-only local development API, not production auth.
    @GetMapping("/balance")
    public Map<String, Object> balance() {
        var rows = jdbc.query("""
            SELECT u.display_name, a.account_no, a.balance
            FROM accounts a JOIN users u ON u.id = a.user_id
            WHERE a.user_id = ? AND a.status = 'ACTIVE'
            LIMIT 1
            """, (rs, rowNum) -> Map.<String, Object>of(
                "userName", rs.getString("display_name"),
                "accountNoMasked", "****" + rs.getString("account_no").substring(Math.max(0, rs.getString("account_no").length() - 4)),
                "balance", rs.getBigDecimal("balance"),
                "currency", "CNY",
                "source", "mysql"
            ), 1L);
        if (rows.isEmpty()) throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Demo account missing");
        return rows.get(0);
    }
}
