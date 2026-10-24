package com.bankpilot.demo;

import java.math.BigDecimal;
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

    public BalanceController(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public record BalanceView(String userName, String accountNoMasked,
                              BigDecimal balance, String currency, String source) { }

    @GetMapping("/balance")
    public BalanceView balance() {
        String sql = """
            SELECT u.display_name, a.account_no, a.balance
            FROM accounts a JOIN users u ON u.id = a.user_id
            WHERE a.user_id = ? AND a.status = 'ACTIVE'
            ORDER BY a.id ASC LIMIT 1
            """;
        var result = jdbc.query(sql, (rs, rowNum) -> new BalanceView(
            rs.getString("display_name"),
            AccountMasker.mask(rs.getString("account_no")),
            rs.getBigDecimal("balance"), "CNY", "mysql"
        ), AuthenticatedUser.id());
        if (result.isEmpty()) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Demo account is missing");
        }
        return result.get(0);
    }
}
