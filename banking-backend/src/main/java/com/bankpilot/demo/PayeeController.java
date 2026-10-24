package com.bankpilot.demo;

import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/demo")
public class PayeeController {
    private final JdbcTemplate jdbc;

    public PayeeController(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public record PayeeView(long id, String payeeName, String payeeAccountMasked) { }

    @GetMapping("/payees")
    public List<PayeeView> listPayees() {
        String sql = """
            SELECT p.id, p.payee_name, a.account_no
            FROM payees p
            JOIN accounts a ON a.id = p.payee_account_id
            WHERE p.user_id = ? AND a.status = 'ACTIVE'
            ORDER BY p.id ASC
            LIMIT 100
            """;
        return jdbc.query(sql, (rs, rowNum) -> new PayeeView(
            rs.getLong("id"), rs.getString("payee_name"),
            AccountMasker.mask(rs.getString("account_no"))
        ), DemoUser.ID);
    }
}
