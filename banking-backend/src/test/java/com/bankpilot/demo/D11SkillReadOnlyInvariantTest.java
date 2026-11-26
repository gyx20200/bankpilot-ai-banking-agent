package com.bankpilot.demo;

import static org.assertj.core.api.Assertions.assertThat;
import java.math.BigDecimal;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;

/** D11: Java remains authoritative; all three Skills are composite READS only. */
@JdbcTest
class D11SkillReadOnlyInvariantTest {
    @Autowired JdbcTemplate jdbc;

    private void asUser(long id) {
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(
                new BankPrincipal(id, "D11-test"), null, List.of()));
    }

    @BeforeEach void setup() { asUser(1L); }
    @AfterEach void clear() { SecurityContextHolder.clearContext(); }

    private long count(String table) {
        return jdbc.queryForObject("SELECT COUNT(*) FROM " + table, Long.class);
    }
    private BigDecimal totalBalance() {
        return jdbc.queryForObject("SELECT COALESCE(SUM(balance),0) FROM accounts", BigDecimal.class);
    }

    @Test void monthlySkillReadsCannotChangeOrdersOrBalances() {
        BigDecimal oldBalance = totalBalance();
        long oldOrders = count("transfer_orders");
        long oldTransactions = count("transactions");
        var report = new MonthlyAnalyticsController(jdbc).monthly("2026-10");
        var anomaly = new TransactionAnomalyController(jdbc).anomalies("2026-10");
        assertThat(report.source()).isEqualTo("mysql");
        assertThat(anomaly.source()).isEqualTo("mysql");
        assertThat(totalBalance()).isEqualByComparingTo(oldBalance);
        assertThat(count("transfer_orders")).isEqualTo(oldOrders);
        assertThat(count("transactions")).isEqualTo(oldTransactions);
    }

    @Test void subscriptionSkillStillScopesToAuthenticatedUser() {
        var controller = new SubscriptionController(jdbc);
        assertThat(controller.listSubscriptions())
            .extracting(SubscriptionController.SubscriptionView::merchantName)
            .contains("视频会员").doesNotContain("其他用户会员");
        asUser(2L);
        assertThat(controller.listSubscriptions())
            .extracting(SubscriptionController.SubscriptionView::merchantName)
            .contains("其他用户会员").doesNotContain("视频会员");
    }

    @Test void accountSnapshotReadsAreNonMutating() {
        long oldOrders = count("transfer_orders");
        long oldTransactions = count("transactions");
        BigDecimal oldBalance = totalBalance();
        jdbc.queryForObject("SELECT balance FROM accounts WHERE user_id=1 AND status='ACTIVE' ORDER BY id LIMIT 1",BigDecimal.class);
        jdbc.queryForList("SELECT id FROM transactions WHERE account_id IN (SELECT id FROM accounts WHERE user_id=1)");
        assertThat(count("transfer_orders")).isEqualTo(oldOrders);
        assertThat(count("transactions")).isEqualTo(oldTransactions);
        assertThat(totalBalance()).isEqualByComparingTo(oldBalance);
    }
}
