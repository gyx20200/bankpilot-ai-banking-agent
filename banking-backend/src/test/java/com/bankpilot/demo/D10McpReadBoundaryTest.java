package com.bankpilot.demo;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;
import java.math.BigDecimal;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.server.ResponseStatusException;

/** MCP is an adapter: Java remains the authoritative, user-scoped read boundary. */
@JdbcTest
class D10McpReadBoundaryTest {
    @Autowired JdbcTemplate jdbc;

    private void asUser(long id) {
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(new BankPrincipal(id,"d10-demo"), null, List.of()));
    }
    @BeforeEach void login() { asUser(1L); }
    @AfterEach void logout() { SecurityContextHolder.clearContext(); }

    private BigDecimal totalBalance() {
        return jdbc.queryForObject("SELECT SUM(balance) FROM accounts", BigDecimal.class);
    }
    private Integer txCount() {
        return jdbc.queryForObject("SELECT COUNT(*) FROM transactions", Integer.class);
    }
    private Integer orderCount() {
        return jdbc.queryForObject("SELECT COUNT(*) FROM transfer_orders", Integer.class);
    }

    @Test void analyticReadsDoNotChangeAccountsOrdersOrLedger() {
        BigDecimal beforeBalance=totalBalance();
        int beforeTx=txCount();
        int beforeOrders=orderCount();
        new MonthlyAnalyticsController(jdbc).monthly("2026-10");
        new AnnualAnalyticsController(jdbc).annual("2020");
        new TransactionAnomalyController(jdbc).anomalies("2020-10");
        assertThat(totalBalance()).isEqualByComparingTo(beforeBalance);
        assertThat(txCount()).isEqualTo(beforeTx);
        assertThat(orderCount()).isEqualTo(beforeOrders);
    }

    
@Test
void annualQueriesRemainScopedToSignedInUser() {
    var controller = new AnnualAnalyticsController(jdbc);

    // Find one active account owned by each test user.
    Long account1 = jdbc.queryForObject(
        """
        SELECT id FROM accounts
        WHERE user_id = ? AND status = 'ACTIVE'
        ORDER BY id LIMIT 1
        """,
        Long.class,
        1L
    );

    Long account2 = jdbc.queryForObject(
        """
        SELECT id FROM accounts
        WHERE user_id = ? AND status = 'ACTIVE'
        ORDER BY id LIMIT 1
        """,
        Long.class,
        2L
    );

    assertThat(account1).isNotEqualTo(account2);

    // Record each user's initial annual expense.
    asUser(1L);
    BigDecimal before1 = controller.annual("2020").totalExpense();

    asUser(2L);
    BigDecimal before2 = controller.annual("2020").totalExpense();

    // Add an expense to user 1 only.
    jdbc.update(
        """
        INSERT INTO transactions
            (account_id, direction, amount, category, occurred_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        account1,
        "OUT",
        new BigDecimal("123.45"),
        "D10_TEST",
        java.time.LocalDateTime.parse("2020-06-15T12:00:00")
    );

    // User 1 must see the new expense.
    asUser(1L);
    var first = controller.annual("2020");

    assertThat(first.source()).isEqualTo("mysql");
    assertThat(first.totalExpense())
        .isEqualByComparingTo(
            before1.add(new BigDecimal("123.45"))
        );

    // User 2 must not see user 1's expense.
    asUser(2L);
    var second = controller.annual("2020");

    assertThat(second.source()).isEqualTo("mysql");
    assertThat(second.totalExpense())
        .isEqualByComparingTo(before2);

    // Add a different expense to user 2 only.
    jdbc.update(
        """
        INSERT INTO transactions
            (account_id, direction, amount, category, occurred_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        account2,
        "OUT",
        new BigDecimal("678.90"),
        "D10_TEST",
        java.time.LocalDateTime.parse("2020-07-15T12:00:00")
    );

    // User 2 must see their own additional expense.
    asUser(2L);
    var secondAfter = controller.annual("2020");

    assertThat(secondAfter.totalExpense())
        .isEqualByComparingTo(
            before2.add(new BigDecimal("678.90"))
        );

    // User 1's result must remain unchanged.
    asUser(1L);
    var firstAfter = controller.annual("2020");

    assertThat(firstAfter.totalExpense())
        .isEqualByComparingTo(
            before1.add(new BigDecimal("123.45"))
        );
}


    @Test void missingAuthenticationIsDeniedByExistingJavaController() {
        SecurityContextHolder.clearContext();
        var err=assertThrows(ResponseStatusException.class, () -> new MonthlyAnalyticsController(jdbc).monthly("2026-10"));
        assertThat(err.getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
    }
}
